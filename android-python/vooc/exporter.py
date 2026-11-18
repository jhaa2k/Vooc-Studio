"""Video export: offline render of the scene + hardware/ffmpeg encoding.

Every frame is rendered by a hidden SceneView at an exact song time
(frame_index / fps) with a fixed time step, so the exported video is always in
sync with the audio, regardless of how fast the phone renders.

    plan_export()  resolution / fps / aspect / codec / bitrate + 4 GB size cap
    Exporter       drives rendering on the GL thread (Kivy Clock) and streams
                   frames to an encoder sink:
                     AndroidSink  - com.jhaa2k.vooc.VideoExporter (MediaCodec + MediaMuxer)
                     FFmpegSink   - desktop, ffmpeg via a pipe

Fallbacks: no HEVC encoder -> H.264 (Java side); size rejected by the encoder or
out of memory -> next lower resolution; projected file over 4 GB -> lower
bitrate, then lower resolution; size guard while writing stops cleanly at 4 GB.
"""
import math
import os
import queue
import re
import threading
import shutil
import subprocess
import time

import numpy as np

ON_ANDROID = "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ

RESOLUTIONS = ["SD 480p", "HD 720p", "FHD 1080p", "QHD 1440p", "4K 2160p", "Custom"]
SHORT_SIDE = {"SD 480p": 480, "HD 720p": 720, "FHD 1080p": 1080, "QHD 1440p": 1440, "4K 2160p": 2160}
BASE_MBPS = {"SD 480p": 2.5, "HD 720p": 5.0, "FHD 1080p": 10.0, "QHD 1440p": 20.0, "4K 2160p": 40.0}
FPS_OPTIONS = ["24", "25", "30", "50", "60"]
ASPECTS = {"16:9": (16, 9), "4:3": (4, 3), "21:10": (21, 10), "9:16": (9, 16), "1:1": (1, 1)}
# name -> (android mime, ffmpeg encoder, bitrate factor, container)
CODECS = {"H.264 (AVC)": ("video/avc", "libx264", 1.0, "mp4"),
          "H.265 (HEVC)": ("video/hevc", "libx265", 0.6, "mp4"),
          "VP9 (WebM)": ("video/x-vnd.on2.vp9", "libvpx-vp9", 0.65, "webm"),
          "AV1": ("video/av01", "libaom-av1", 0.5, "mp4")}
QUALITY = {"Small": 0.6, "Standard": 1.0, "High": 1.5}
PROFILES = {"Auto": 0, "Baseline": 1, "Main": 2, "High": 8}          # MediaCodecInfo.CodecProfileLevel.AVCProfile*
COLOR_MATRIX = {"BT.709": 1, "BT.601": 4}                             # MediaFormat.COLOR_STANDARD_*
B_FRAMES = ["0", "1", "2"]
KEYFRAMES = ["1", "2", "5", "10"]
NAME_TOKENS = ["{title}", "{artist}", "{template}", "{res}", "{fps}", "{codec}", "{date}", "{time}", "{n}"]
DEFAULT_PATTERN = "Vooc_{title}_{date}_{time}"
AUDIO_BPS = 192000
LIMIT_BYTES = 4 * 1024 ** 3 - 64 * 1024 ** 2      # FAT32 / MP4 safe cap with headroom
_AVAILABLE = {}


def encoder_available(codec):
    """Is there an encoder for this codec on the device (Android) / in ffmpeg (desktop)? Cached."""
    if codec in _AVAILABLE:
        return _AVAILABLE[codec]
    mime, ff = CODECS[codec][0], CODECS[codec][1]
    ok = codec == "H.264 (AVC)"
    try:
        if ON_ANDROID:
            from jnius import autoclass
            ok = bool(autoclass("com.jhaa2k.vooc.VideoExporter").hasEncoder(mime))
        else:
            exe = shutil.which("ffmpeg")
            if exe:
                out = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=10).stdout
                ok = (" " + ff + " ") in out or ok
    except Exception as exc:
        print("Vooc encoder check failed: %s" % exc)
    _AVAILABLE[codec] = ok
    return ok


def _clean(text):
    return "".join(ch if ch.isalnum() or ch in " -_." else "_" for ch in str(text or "")).strip()[:60]


def output_name(pattern, meta=None, plan=None, template="", n=1, when=None):
    """Expand a naming pattern ({title} {artist} {template} {res} {fps} {codec} {date} {time} {n})."""
    when = time.localtime(when) if when else time.localtime()
    plan = plan or {}
    meta = meta or {}
    values = {"title": meta.get("title") or "video", "artist": meta.get("artist") or "",
              "template": template or "", "res": "%sx%s" % (plan.get("width", ""), plan.get("height", "")),
              "fps": str(plan.get("fps", "")), "codec": (plan.get("codec") or "").split(" ")[0],
              "date": time.strftime("%Y%m%d", when), "time": time.strftime("%H%M%S", when), "n": "%02d" % n}
    out = pattern or DEFAULT_PATTERN
    for k, v in values.items():
        out = out.replace("{%s}" % k, _clean(v))
    out = re.sub(r"[_ ]{2,}", "_", out).strip(" _-.")
    return out or "Vooc_video"


def frame_size(resolution, aspect, custom=None):
    if resolution == "Custom":
        w, h = custom or (1920, 1080)
        w = max(128, min(4096, int(w))) // 2 * 2
        h = max(128, min(4096, int(h))) // 2 * 2
        return w, h
    short = SHORT_SIDE[resolution]
    a, b = ASPECTS.get(aspect, (16, 9))
    if a >= b:
        h, w = short, short * a / float(b)
    else:
        w, h = short, short * b / float(a)
    w = int(round(w / 16.0)) * 16          # encoder friendly
    h = int(round(h / 2.0)) * 2
    return max(16, w), max(16, h)


def _nominal(resolution, custom):
    """Closest preset for bitrate purposes (custom sizes scale by pixel count)."""
    if resolution != "Custom":
        return resolution, 1.0
    w, h = frame_size("Custom", None, custom)
    px = w * h
    return "FHD 1080p", px / float(1920 * 1080)


def video_bitrate(resolution, fps, codec, quality="Standard", custom=None):
    nominal, scale = _nominal(resolution, custom)
    k = BASE_MBPS[nominal] * scale * (float(fps) / 30.0) ** 0.6 * CODECS[codec][2] * QUALITY.get(quality, 1.0)
    return int(max(0.3, k) * 1e6)


def plan_export(settings, duration, available=None):
    """settings: resolution, fps, aspect, codec, audio, quality, custom_w/h, bitrate_mbps (0 = auto),
    keyframe_s, bframes, profile, color, trim_start, trim_end (0 = song end), fade_in, fade_out.
    ``available(codec) -> bool`` checks encoders (unavailable codecs fall back to H.264)."""
    res = settings.get("resolution", "FHD 1080p")
    if res not in RESOLUTIONS:
        res = "FHD 1080p"
    fps = int(settings.get("fps", 30))
    aspect = settings.get("aspect", "16:9")
    codec = settings.get("codec", "H.264 (AVC)")
    if codec not in CODECS:
        codec = "H.264 (AVC)"
    quality = settings.get("quality", "Standard")
    audio = bool(settings.get("audio", True))
    custom = (settings.get("custom_w", 1920), settings.get("custom_h", 1080))
    notes = []
    if available is not None and codec != "H.264 (AVC)" and not available(codec):
        notes.append("%s encoder not available on this device, using H.264" % codec)
        codec = "H.264 (AVC)"
    song = max(0.5, float(duration or 0))
    start = max(0.0, min(song - 0.5, float(settings.get("trim_start", 0) or 0)))
    end = float(settings.get("trim_end", 0) or 0)
    end = song if end <= 0 or end > song else end
    if end - start < 0.5:
        end = min(song, start + 0.5)
    duration = end - start
    if start > 0 or end < song:
        notes.append("Trimmed to %s - %s" % (_fmt(start), _fmt(end)))
    fade_in = max(0.0, min(duration / 2, float(settings.get("fade_in", 0) or 0)))
    fade_out = max(0.0, min(duration / 2, float(settings.get("fade_out", 0) or 0)))
    abps = AUDIO_BPS if audio else 0
    manual = float(settings.get("bitrate_mbps", 0) or 0)
    order = [res] if res == "Custom" else RESOLUTIONS[:RESOLUTIONS.index(res) + 1][::-1]
    r = res
    for r in order:
        vb = int(manual * 1e6) if manual > 0 else video_bitrate(r, fps, codec, quality, custom)
        est = (vb + abps) * duration / 8.0 * 1.02
        if est <= LIMIT_BYTES:
            break
        # lower the bitrate (but not below 40% of nominal) before dropping resolution
        fit = int(LIMIT_BYTES * 8.0 / duration / 1.02 - abps)
        if fit >= vb * 0.4 or r == "Custom":
            notes.append("Bitrate lowered to %.1f Mbps to stay under 4 GB" % (fit / 1e6))
            vb = max(300000, fit)
            est = (vb + abps) * duration / 8.0 * 1.02
            break
        notes.append("%s would exceed 4 GB, trying a lower resolution" % r)
    else:
        vb = max(500000, int(LIMIT_BYTES * 8.0 / duration / 1.02 - abps))
        est = (vb + abps) * duration / 8.0 * 1.02
    if r != res:
        notes.append("Resolution reduced to %s" % r)
    w, h = frame_size(r, aspect, custom)
    container = CODECS[codec][3]
    if container == "webm" and audio:
        notes.append("WebM audio is Opus (re-encoded)")
    profile = settings.get("profile", "Auto")
    if codec != "H.264 (AVC)":
        profile = "Auto"                      # AVC profile ids do not apply to other codecs
    return {"resolution": r, "width": w, "height": h, "fps": fps, "aspect": aspect, "codec": codec,
            "mime": CODECS[codec][0], "ffmpeg_codec": CODECS[codec][1], "container": container,
            "ext": "." + container, "bitrate": int(vb), "audio": audio, "duration": duration,
            "start": start, "end": end, "fade_in": fade_in, "fade_out": fade_out,
            "frames": int(math.ceil(duration * fps)), "estimate_bytes": int(est),
            "keyframe_s": int(settings.get("keyframe_s", 1) or 1), "bframes": int(settings.get("bframes", 0) or 0),
            "profile": profile, "color": settings.get("color", "BT.709"), "custom": custom,
            "notes": notes}


def video_fade(plan, t):
    """0..1 brightness at clip time ``t`` (seconds from the trimmed start)."""
    g = 1.0
    if plan.get("fade_in", 0) > 0 and t < plan["fade_in"]:
        g = t / plan["fade_in"]
    rem = plan["duration"] - t
    if plan.get("fade_out", 0) > 0 and rem < plan["fade_out"]:
        g = min(g, rem / plan["fade_out"])
    return max(0.0, min(1.0, g))


def lower_resolution(plan):
    if plan["resolution"] == "Custom":
        p = dict(plan)
        w, h = int(plan["width"] * 0.75) // 2 * 2, int(plan["height"] * 0.75) // 2 * 2
        if min(w, h) < 128:
            return None
        p["width"], p["height"], p["custom"] = w, h, (w, h)
        p["notes"] = list(plan["notes"]) + ["Fell back to %dx%d" % (w, h)]
        return p
    i = RESOLUTIONS.index(plan["resolution"])
    if i == 0:
        return None
    r = RESOLUTIONS[i - 1]
    p = dict(plan)
    p["resolution"] = r
    p["width"], p["height"] = frame_size(r, plan["aspect"])
    p["bitrate"] = min(plan["bitrate"], video_bitrate(r, plan["fps"], plan["codec"]))
    p["notes"] = list(plan["notes"]) + ["Fell back to %s" % r]
    return p


# BT.601 / BT.709 limited-range RGB -> YUV, coefficients x256
_MATRIX = {"BT.601": ((66, 129, 25), (-38, -74, 112), (112, -94, -18)),
           "BT.709": ((47, 157, 16), (-26, -87, 112), (112, -102, -10))}


def rgba_to_i420(pixels, w, h, flip=True, matrix="BT.601", gain=1.0):
    """Convert OpenGL RGBA to limited-range I420 using bounded row chunks.

    Processing the full 4K frame as several int32 RGB planes can temporarily
    allocate hundreds of MB on Android. Chunking keeps peak temporary memory
    small while preserving the same matrix, orientation and output layout.
    """
    w, h = int(w), int(h)
    if w <= 0 or h <= 0 or (w & 1) or (h & 1):
        raise ValueError("I420 dimensions must be positive even numbers")
    expected = w * h * 4
    if len(pixels) != expected:
        raise ValueError("RGBA frame has %d bytes; expected %d" % (len(pixels), expected))
    src = np.frombuffer(pixels, np.uint8).reshape(h, w, 4)
    if flip:
        src = src[::-1]
    out = np.empty(w * h * 3 // 2, np.uint8)
    y_out = out[:w * h].reshape(h, w)
    q = (w // 2) * (h // 2)
    u_out = out[w * h:w * h + q].reshape(h // 2, w // 2)
    v_out = out[w * h + q:].reshape(h // 2, w // 2)
    (yr, yg, yb), (ur, ug, ub), (vr, vg, vb) = _MATRIX.get(matrix, _MATRIX["BT.601"])
    k = int(max(0.0, min(1.0, float(gain))) * 256) if gain < 0.999 else 256
    rows_per_chunk = 64
    for y0 in range(0, h, rows_per_chunk):
        y1 = min(h, y0 + rows_per_chunk)
        # Keep chunk boundaries aligned to 2x2 chroma sampling.
        if (y1 - y0) & 1:
            y1 -= 1
        block = src[y0:y1]
        r = block[:, :, 0].astype(np.int32)
        g = block[:, :, 1].astype(np.int32)
        blue = block[:, :, 2].astype(np.int32)
        if k != 256:
            r = (r * k) >> 8
            g = (g * k) >> 8
            blue = (blue * k) >> 8
        yy = ((yr * r + yg * g + yb * blue + 128) >> 8) + 16
        y_out[y0:y1] = np.clip(yy, 0, 255).astype(np.uint8)
        r2 = (r[0::2, 0::2] + r[1::2, 0::2] + r[0::2, 1::2] + r[1::2, 1::2]) >> 2
        g2 = (g[0::2, 0::2] + g[1::2, 0::2] + g[0::2, 1::2] + g[1::2, 1::2]) >> 2
        b2 = (blue[0::2, 0::2] + blue[1::2, 0::2] + blue[0::2, 1::2] + blue[1::2, 1::2]) >> 2
        u = ((ur * r2 + ug * g2 + ub * b2 + 128) >> 8) + 128
        v = ((vr * r2 + vg * g2 + vb * b2 + 128) >> 8) + 128
        cy0, cy1 = y0 // 2, y1 // 2
        u_out[cy0:cy1] = np.clip(u, 0, 255).astype(np.uint8)
        v_out[cy0:cy1] = np.clip(v, 0, 255).astype(np.uint8)
    return out.tobytes()


# ---------------------------------------------------------------- sinks
class FFmpegSink:
    """Desktop encoder (also used by the tests)."""

    def __init__(self, plan, out_path, audio_path):
        self.plan, self.out_path = plan, out_path
        ff = shutil.which("ffmpeg")
        if not ff:
            raise RuntimeError("ffmpeg is not installed")
        w, h = plan["width"], plan["height"]
        cmd = [ff, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", "%dx%d" % (w, h),
               "-r", str(plan["fps"]), "-i", "-"]
        webm = plan.get("container") == "webm"
        if plan["audio"] and audio_path:
            start, dur = plan.get("start", 0.0), plan["duration"]
            cmd += ["-ss", "%.3f" % start, "-t", "%.3f" % dur, "-i", audio_path, "-map", "0:v", "-map", "1:a"]
            af = []
            if plan.get("fade_in"):
                af.append("afade=t=in:st=0:d=%.3f" % plan["fade_in"])
            if plan.get("fade_out"):
                af.append("afade=t=out:st=%.3f:d=%.3f" % (max(0, dur - plan["fade_out"]), plan["fade_out"]))
            if af:
                cmd += ["-af", ",".join(af)]
            cmd += ["-c:a", "libopus" if webm else "aac", "-b:a", "128k" if webm else "192k", "-shortest"]
        vf = "vflip"
        cmd += ["-vf", vf, "-c:v", plan["ffmpeg_codec"], "-b:v", str(plan["bitrate"]), "-pix_fmt", "yuv420p",
                "-g", str(max(1, plan.get("keyframe_s", 1)) * plan["fps"])]
        if plan["ffmpeg_codec"] in ("libx264", "libx265"):
            cmd += ["-bf", str(plan.get("bframes", 0))]
        if plan.get("profile", "Auto") != "Auto" and plan["ffmpeg_codec"] == "libx264":
            cmd += ["-profile:v", plan["profile"].lower()]
        if plan.get("color") == "BT.709":
            cmd += ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
        else:
            cmd += ["-colorspace", "smpte170m", "-color_primaries", "smpte170m", "-color_trc", "smpte170m"]
        if not webm:
            cmd += ["-movflags", "+faststart"]
        cmd += [out_path]
        self.gain = 1.0
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        self.error = ""
        self.limit_reached = False
        self.mime = plan["mime"]

    def ready(self):
        return True

    def write(self, rgba, w, h, pts_us, gain=1.0):
        try:
            if gain < 0.999:
                a = np.frombuffer(rgba, np.uint8).reshape(-1, 4).astype(np.uint16)
                a[:, :3] = (a[:, :3] * int(gain * 256)) >> 8
                rgba = a.astype(np.uint8).tobytes()
            self.proc.stdin.write(rgba)
            return True
        except Exception as exc:
            self.error = "ffmpeg: %s" % exc
            return False

    def bytes_written(self):
        try:
            return os.path.getsize(self.out_path)
        except OSError:
            return 0

    def finish(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        err = self.proc.stderr.read().decode("utf-8", "ignore")
        code = self.proc.wait()
        if code != 0:
            self.error = err.strip()[-300:] or ("ffmpeg exit %d" % code)
        return code == 0

    def cancel(self):
        try:
            self.proc.kill()
        except Exception:
            pass


class AndroidSink:
    def __init__(self, plan, out_path, audio_path):
        from jnius import autoclass
        VE = autoclass("com.jhaa2k.vooc.VideoExporter")
        self.plan = plan
        us = lambda sec: int(round(float(sec) * 1e6))
        end_us = us(plan["end"]) if plan.get("end") else 0
        self.java = VE(out_path, plan["width"], plan["height"], plan["fps"], plan["bitrate"], plan["mime"],
                       audio_path or "", bool(plan["audio"] and audio_path), LIMIT_BYTES,
                       int(plan.get("keyframe_s", 1)), int(plan.get("bframes", 0)),
                       PROFILES.get(plan.get("profile", "Auto"), 0), COLOR_MATRIX.get(plan.get("color"), 0),
                       1 if plan.get("container") == "webm" else 0, us(plan.get("start", 0)), end_us,
                       us(plan.get("fade_in", 0)), us(plan.get("fade_out", 0)))
        if not self.java.start():
            raise RuntimeError(self.java.getError() or "encoder failed to start")
        self.mime = self.java.getMime()
        self.error = ""

    @property
    def limit_reached(self):
        return bool(self.java.isLimitReached())

    def ready(self):
        return bool(self.java.isAudioReady())

    def write(self, rgba, w, h, pts_us, gain=1.0):
        ok = self.java.writeFrame(rgba_to_i420(rgba, w, h, matrix=self.plan.get("color", "BT.601"), gain=gain),
                                  int(pts_us))
        if not ok:
            self.error = self.java.getError()
        return ok

    def bytes_written(self):
        return int(self.java.getBytesWritten())

    def finish(self):
        ok = self.java.finish()
        if not ok:
            self.error = self.java.getError()
        audio_err = self.java.getAudioError()
        if audio_err:
            self.error = (self.error + " " + audio_err).strip()
        return ok

    def cancel(self):
        try:
            self.java.cancel()
            self.java.finish()
        except Exception:
            pass


def keep_screen_on(on):
    if not ON_ANDROID:
        return
    try:
        from android.runnable import run_on_ui_thread
        from jnius import autoclass

        @run_on_ui_thread
        def apply():
            act = autoclass("org.kivy.android.PythonActivity").mActivity
            win = act.getWindow()
            flag = 128                       # WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
            if on:
                win.addFlags(flag)
            else:
                win.clearFlags(flag)
        apply()
    except Exception as exc:
        print("Vooc keep screen on: %s" % exc)


def thermal_status():
    """PowerManager.getCurrentThermalStatus (API 29+): 0 none .. 6 shutdown. -1 when unknown."""
    if not ON_ANDROID:
        return 0
    try:
        from jnius import autoclass
        PA = autoclass("org.kivy.android.PythonActivity")
        ctx = PA.mActivity
        if autoclass("android.os.Build$VERSION").SDK_INT < 29:
            return 0
        pm = ctx.getSystemService(autoclass("android.content.Context").POWER_SERVICE)
        return int(pm.getCurrentThermalStatus())
    except Exception:
        return -1


class ExportNotifier:
    """Progress notification in the status bar (Android only; silently does nothing elsewhere)."""

    CHANNEL = "vooc_export"
    ID = 4711

    def __init__(self):
        self.ok = ON_ANDROID
        self._last = 0.0
        self._nm = None
        self._builder = None

    def _setup(self):
        from jnius import autoclass
        PA = autoclass("org.kivy.android.PythonActivity")
        Context = autoclass("android.content.Context")
        ctx = PA.mActivity
        self._nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE)
        Builder = autoclass("android.app.Notification$Builder")
        sdk = autoclass("android.os.Build$VERSION").SDK_INT
        if sdk >= 26:
            NC = autoclass("android.app.NotificationChannel")
            NM = autoclass("android.app.NotificationManager")
            self._nm.createNotificationChannel(NC(self.CHANNEL, "Video export", NM.IMPORTANCE_LOW))
            self._builder = Builder(ctx, self.CHANNEL)
        else:
            self._builder = Builder(ctx)
        icon = ctx.getApplicationInfo().icon
        self._builder.setSmallIcon(icon).setContentTitle("Exporting video").setOnlyAlertOnce(True).setOngoing(True)
        try:
            Intent = autoclass("android.content.Intent")
            PI = autoclass("android.app.PendingIntent")
            it = Intent(ctx, PA)
            it.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
            self._builder.setContentIntent(PI.getActivity(ctx, 0, it, 67108864))   # FLAG_IMMUTABLE
        except Exception:
            pass

    def update(self, frac, text):
        if not self.ok or time.monotonic() - self._last < 1.0:
            return
        self._last = time.monotonic()
        try:
            if self._builder is None:
                self._setup()
            self._builder.setProgress(1000, int(frac * 1000), False).setContentText(text)
            self._nm.notify(self.ID, self._builder.build())
        except Exception as exc:
            print("Vooc notification: %s" % exc)
            self.ok = False

    def done(self, ok, text):
        if not self.ok:
            return
        try:
            if self._builder is None:
                self._setup()
            self._builder.setOngoing(False).setProgress(0, 0, False).setAutoCancel(True)
            self._builder.setContentTitle("Export finished" if ok else "Export stopped").setContentText(text)
            self._nm.notify(self.ID, self._builder.build())
        except Exception as exc:
            print("Vooc notification: %s" % exc)


# ---------------------------------------------------------------- driver
class Exporter:
    """Runs on the Kivy main thread. Callbacks: on_progress(frac, text), on_done(ok, path, message)."""

    FRAME_BUDGET = 0.030      # seconds of rendering per Clock tick (keeps the UI responsive)

    def __init__(self, project, timeline, audio_path, metadata, settings, out_path,
                 on_progress=None, on_done=None, sink_factory=None):
        self.project, self.timeline, self.audio_path = project, timeline, audio_path
        self.metadata = dict(metadata or {})
        self.settings, self.out_path = dict(settings), out_path
        self.on_progress = on_progress or (lambda f, t: None)
        self.on_done = on_done or (lambda ok, p, m: None)
        self.sink_factory = sink_factory or (AndroidSink if ON_ANDROID else FFmpegSink)
        self.plan = None
        self.sink = None
        self.scene = None
        self.index = 0
        self.cancelled = False
        self.running = False
        self._event = None
        self._t0 = 0.0
        self.paused = False
        self._paused_at = 0.0
        self._budget = self.FRAME_BUDGET
        self._thermal_checked = 0.0
        self.notifier = ExportNotifier()
        # Rendering must stay on Kivy's GL thread, but pixel conversion and codec
        # writes run on a bounded worker queue so encoding never blocks UI frames.
        self._frame_queue = None
        self._frame_worker = None
        self._worker_error = ""
        self._limit_reached = False
        self._last_progress_ui = 0.0
        self._finishing = False

    # ---- setup with resolution fallback
    def start(self):
        from kivy.clock import Clock
        duration = getattr(self.timeline, "duration", 0.0) or 0.0
        if self.timeline is None or duration <= 0:
            self.on_done(False, None, "Load a track and wait for the analysis before exporting")
            return False
        if not getattr(self.timeline, "complete", True):
            self.on_done(False, None, "The track is still being analysed, try again in a moment")
            return False
        self.plan = plan_export(self.settings, duration, available=encoder_available)
        while True:
            try:
                self._build(self.plan)
                break
            except MemoryError:
                msg = "Out of memory at %s" % self.plan["resolution"]
            except Exception as exc:
                msg = str(exc)
            self._teardown()
            nxt = lower_resolution(self.plan)
            if nxt is None:
                self.on_done(False, None, "Export failed: " + msg)
                return False
            print("Vooc export: %s -> retry at %s" % (msg, nxt["resolution"]))
            self.plan = nxt
        self._frame_queue = queue.Queue(maxsize=1)  # one queued frame + one in-flight frame
        self._worker_error = ""
        self._limit_reached = False
        self._finishing = False
        self._frame_worker = threading.Thread(target=self._frame_writer, name="VoocFrameEncoder", daemon=False)
        self._frame_worker.start()
        keep_screen_on(True)
        self.running = True
        self._t0 = time.monotonic()
        self._event = Clock.schedule_interval(self._step, 0)
        return True

    def _build(self, plan):
        from copy import deepcopy
        from .audio.timeline_hub import TimelineHub
        from .engine.scene import SceneView
        from .model import ProjectModel
        project = ProjectModel.from_dict(deepcopy(self.project.to_dict()))
        audio = project.layer("AUDIOPROVIDER")
        audio.set("General/Routing/Audio Source", "File")
        comp = project.layer("COMPOSITION")
        comp.set("Render Settings/Output/Resolution Width", plan["width"])
        comp.set("Render Settings/Output/Resolution Height", plan["height"])
        self.t = 0.0
        hub = TimelineHub(audio, timeline=lambda: self.timeline, position=lambda: self.t,
                          playing=lambda: True,
                          duration=lambda: getattr(self.timeline, "duration", 0.0) or plan["duration"])
        hub.metadata.update(self.metadata)
        hub.fallback = False
        hub.fixed_dt = 1.0 / plan["fps"]
        self.scene = SceneView(project, hub, offline=True, size_override=(plan["width"], plan["height"]))
        self.scene.size = (plan["width"], plan["height"])
        self.scene.rebuild()
        self.t = plan.get("start", 0.0)
        self.scene.render_frame(self.t, 1.0 / plan["fps"])
        px = self.scene.pixels()
        if len(px) != plan["width"] * plan["height"] * 4:
            raise RuntimeError("GPU could not render %dx%d" % (plan["width"], plan["height"]))
        self.sink = self.sink_factory(plan, self.out_path, self.audio_path if plan["audio"] else None)

    def _frame_writer(self):
        """Encode submitted frames away from the UI thread; queue size bounds RAM use."""
        while True:
            item = self._frame_queue.get()
            try:
                if item is None:
                    return
                if self.cancelled or self._worker_error:
                    continue
                rgba, w, h, pts_us, gain = item
                if not self.sink.write(rgba, w, h, pts_us, gain):
                    self._worker_error = self.sink.error or "Encoder rejected a frame"
                elif self.sink.limit_reached:
                    self._limit_reached = True
            except BaseException as exc:
                self._worker_error = str(exc)[:240] or exc.__class__.__name__
            finally:
                self._frame_queue.task_done()

    def _progress(self, frac, text, force=False):
        now = time.monotonic()
        if not force and now - self._last_progress_ui < 0.10:
            return
        self._last_progress_ui = now
        self.on_progress(frac, text)
        self.notifier.update(frac, text)

    def _teardown(self):
        if self.scene is not None:
            self.scene.stop()
            self.scene.passes = []
            self.scene.renderers = {}
            self.scene.effects = {}
            self.scene = None

    def cancel(self):
        self.cancelled = True
        self.paused = False
        # Also start cleanup when the app is closing and Kivy's next Clock tick
        # may never arrive. This releases the non-daemon encoder worker cleanly.
        if self.running and not self._finishing:
            self._finish(False, "Export cancelled")

    def pause(self):
        if self.running and not self.paused:
            self.paused = True
            self._paused_at = time.monotonic()
            keep_screen_on(False)
            self.on_progress(self.index / float(max(1, self.plan["frames"])), "Paused")
            self.notifier.update(self.index / float(max(1, self.plan["frames"])), "Paused")

    def resume(self):
        if self.running and self.paused:
            self.paused = False
            self._t0 += time.monotonic() - self._paused_at      # paused time does not count for the ETA
            keep_screen_on(True)

    def _throttle(self):
        """Every few seconds read the thermal status and shrink the per-tick render budget when hot."""
        now = time.monotonic()
        if now - self._thermal_checked < 5.0:
            return
        self._thermal_checked = now
        level = thermal_status()
        self._budget = self.FRAME_BUDGET * {0: 1.0, 1: 1.0, 2: 0.6, 3: 0.35}.get(level, 0.2)
        self.hot = level >= 2

    def _step(self, _dt):
        # A renderer / GPU / encoder exception must stop this export cleanly,
        # not escape Kivy's Clock callback and terminate the app.
        try:
            plan = self.plan
            if self.cancelled:
                return self._finish(False, "Export cancelled")
            if self.paused:
                return
            if self._worker_error:
                return self._finish(False, "Encoding failed: " + self._worker_error)
            if self._limit_reached:
                return self._finish(True, "Stopped at the 4 GB file size limit")
            if not self.sink.ready():
                self._progress(0.0, "Preparing audio...")
                return
            self._throttle()
            deadline = time.monotonic() + self._budget
            dt = 1.0 / plan["fps"]
            start = plan.get("start", 0.0)
            while self.index < plan["frames"] and time.monotonic() < deadline:
                if self._frame_queue.full():
                    break
                clip_t = self.index * dt
                self.t = start + clip_t
                self.scene.render_frame(self.t, dt)
                gain = video_fade(plan, clip_t)
                pixels = self.scene.pixels()
                expected = plan["width"] * plan["height"] * 4
                if len(pixels) != expected:
                    raise RuntimeError("Rendered frame has an invalid pixel buffer")
                try:
                    self._frame_queue.put_nowait((pixels, plan["width"], plan["height"], int(clip_t * 1e6), gain))
                except queue.Full:
                    break
                self.index += 1
            frac = self.index / float(max(1, plan["frames"]))
            el = time.monotonic() - self._t0
            eta = el / frac - el if frac > 0.01 else 0
            text = "%d / %d frames  -  %s left" % (self.index, plan["frames"], _fmt(eta))
            if getattr(self, "hot", False):
                text += "  -  device hot, slowed down"
            self._progress(frac, text, force=self.index >= plan["frames"])
            if self.index >= plan["frames"]:
                return self._finish(True, "")
        except MemoryError:
            return self._finish(False, "Export stopped safely: not enough memory while rendering")
        except Exception as exc:
            print("Vooc export render error: %s" % exc)
            return self._finish(False, "Export stopped safely: " + str(exc)[:220])

    def _finish(self, ok, message):
        """Stop scheduling frames, then drain/close encoders on a worker thread."""
        if self._finishing:
            return False
        self._finishing = True
        if self._event is not None:
            self._event.cancel()
            self._event = None
        self.running = False
        self.paused = False
        keep_screen_on(False)

        def finalize():
            nonlocal ok, message
            sink_closed = False
            try:
                if self._frame_queue is not None:
                    # Sentinel is ordered after all submitted frames. On cancel the
                    # writer discards queued frames, then the sink is closed safely.
                    self._frame_queue.put(None)
                    self._frame_queue.join()
                if self._frame_worker is not None:
                    self._frame_worker.join()
                if self._worker_error:
                    ok = False
                    message = (message + " Encoding failed: " + self._worker_error).strip()
                if self.sink is not None:
                    if self.cancelled:
                        self.sink.cancel()
                        sink_closed = True
                        ok = False
                    else:
                        done = self.sink.finish()
                        sink_closed = True
                        if not done:
                            ok = False
                            message = (message + " " + (self.sink.error or "Encoder did not finish")).strip()
                        elif self.sink.error:
                            message = (message + " " + self.sink.error).strip()
            except BaseException as exc:
                ok = False
                message = (message + " Export cleanup failed: " + str(exc)[:180]).strip()
                print("Vooc export finalizer error: %s" % exc)
            finally:
                # If finish itself throws, make a best-effort abort so codec,
                # muxer and FFmpeg pipe resources are not left open.
                if self.sink is not None and not sink_closed:
                    try:
                        self.sink.cancel()
                    except Exception as cleanup_exc:
                        print("Vooc export abort cleanup failed: %s" % cleanup_exc)

            try:
                from kivy.clock import Clock
                Clock.schedule_once(lambda _dt: self._finish_ui(ok, message), 0)
            except Exception as exc:
                print("Vooc export UI completion scheduling failed: %s" % exc)

        threading.Thread(target=finalize, name="VoocExportFinalize", daemon=False).start()
        return False

    def _finish_ui(self, ok, message):
        """Final UI/GL cleanup; called on Kivy's main thread after the sink closes."""
        try:
            self._teardown()
        except Exception as exc:
            print("Vooc export scene cleanup error: %s" % exc)
            if ok:
                ok = False
                message = (message + " Scene cleanup failed: " + str(exc)[:140]).strip()

        # Never leave a truncated MP4/WebM that looks like a successful export.
        if not ok and os.path.exists(self.out_path):
            try:
                os.remove(self.out_path)
            except OSError as exc:
                print("Vooc partial export cleanup failed: %s" % exc)

        notes = "; ".join(self.plan.get("notes", [])) if self.plan else ""
        self.notifier.done(ok, os.path.basename(self.out_path) if ok else (message or "Export failed"))
        self.on_done(ok, self.out_path if ok else None, "; ".join(x for x in (message, notes) if x))
        return False


def _fmt(sec):
    sec = int(max(0, sec))
    return "%d:%02d" % (sec // 60, sec % 60)
