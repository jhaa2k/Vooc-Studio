"""Avee-style Waveform extras: Ring shape, layered trails, taper, fill / hatch.

Extends the WAVEFORM module (schema + renderer) without touching the original
Line/Filled/Dotted/Bars code path: with the default settings (Shape = Line,
Trails = 1, Taper = 0, Fill = Outline) the original renderer runs unchanged.

  Shape   Line | Ring           ring = waveform wrapped around a circle
  Fill    Outline | Solid | Hatch   fill between the base circle/line and the wave
  Layers  Trails, Trail Delay (frames), Trail Spacing, Trail Twist, Trail Fade
  Ring    Radius, Spin, Loop Blend (hides the seam), Hatch Step
"""
import math
from collections import OrderedDict as OD

import numpy as np

from ..model import hex_to_rgba
from ..property_schema import SCHEMA, dropdown, slider
from .geometry import thick_polyline
from .layers import RENDERERS
from .vector_layers import W, WaveformLayer


def _extend_schema():
    wf = SCHEMA["WAVEFORM"]["Waveform"]
    if "Layers" in wf:
        return
    st, par = wf["Style"], wf["Parameters"]
    st["Shape"] = dropdown(["Line", "Ring"], "Line", help="Ring wraps the waveform around a circle")
    st["Fill"] = dropdown(["Outline", "Solid", "Hatch"], "Outline",
                          help="Fill between the base line/circle and the wave")
    par["Taper"] = slider(0.0, 0, 1, help="Fade the line towards both ends (Line shape)")
    wf["Layers"] = OD([
        ("Trails", slider(1, 1, 12, step=1, help="Number of stacked copies of the wave")),
        ("Trail Delay (frames)", slider(3, 1, 12, step=1, help="How far back in time each copy is")),
        ("Trail Spacing", slider(0.0, 0, 0.3, help="Offset between copies (line: vertical, ring: radius)")),
        ("Trail Twist", slider(0.0, -30, 30, step=0.5, help="Ring: rotation per copy in degrees")),
        ("Trail Fade", slider(0.6, 0, 1, help="How much older copies fade and thin out")),
    ])
    wf["Ring"] = OD([
        ("Radius", slider(0.7, 0.1, 1, help="Base circle radius")),
        ("Spin (deg/s)", slider(0.0, -180, 180, step=1)),
        ("Loop Blend", slider(0.2, 0, 0.5, help="Smooths the start/end seam of the ring")),
        ("Hatch Step", slider(3, 1, 16, step=1, help="Spacing of hatch lines (points)")),
    ])


_extend_schema()


def _get(v, key, default):
    try:
        val = v[key]
    except Exception:
        return default
    return default if val is None else val


def _spokes(a, b, width):
    """Thin quads from points a[i] to b[i] (vectorised)."""
    d = b - a
    ln = np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-6)
    n = np.stack([-d[:, 1], d[:, 0]], 1) / ln * (width / 2.0)
    return np.stack([a - n, b - n, b + n, a + n], 1).astype(np.float32)


class WaveformPlusLayer(WaveformLayer):
    def build(self):
        super().build()
        self.hist = []
        self._phase = 0.0

    def _is_plain(self):
        v = self.values
        return (str(_get(v, W + "Style/Shape", "Line")) == "Line"
                and int(_get(v, W + "Layers/Trails", 1)) <= 1
                and float(_get(v, W + "Parameters/Taper", 0.0)) <= 0.0
                and str(_get(v, W + "Style/Fill", "Outline")) == "Outline")

    def render(self, frame):
        if self._is_plain():
            self.hist = []
            return super().render(frame)
        v = self.values
        w, h = frame.w * float(v[W + "Size/Width"]), frame.h * float(v[W + "Size/Height"])
        ring = str(_get(v, W + "Style/Shape", "Line")) == "Ring"
        if ring:  # ring diameter = Width x the short side of the frame (square box)
            w = h = min(frame.w, frame.h) * float(v[W + "Size/Width"])
        fill = str(_get(v, W + "Style/Fill", "Outline"))
        channel = v[W + "Style/Channel"]
        ch = "Left" if channel == "Stereo" else channel
        amp = float(v[W + "Parameters/Amplitude"])
        thick = max(1.0, float(v[W + "Parameters/Thickness (dp)"]) * frame.h / 720.0)
        alpha = float(v[W + "Parameters/Smoothing"])
        taper = float(_get(v, W + "Parameters/Taper", 0.0))
        trails = max(1, int(_get(v, W + "Layers/Trails", 1)))
        delay = max(1, int(_get(v, W + "Layers/Trail Delay (frames)", 3)))
        spacing = float(_get(v, W + "Layers/Trail Spacing", 0.0))
        twist = math.radians(float(_get(v, W + "Layers/Trail Twist", 0.0)))
        fade = float(_get(v, W + "Layers/Trail Fade", 0.6))
        c1, c2 = np.asarray(hex_to_rgba(v[W + "Color/Color From"]), np.float32), \
            np.asarray(hex_to_rgba(v[W + "Color/Color To"]), np.float32)
        cmode = v[W + "Color/Color Mode"]

        wave, _env = self._window(frame, ch)
        wave = np.clip(np.nan_to_num(wave) * amp, -1, 1)
        if self.smooth is None or self.smooth.get("key") != (0, len(wave)):
            self.smooth = {"key": (0, len(wave)), "v": wave.copy()}
        sm = self.smooth["v"]
        sm += (wave - sm) * (1.0 - alpha)
        wave = sm.copy()
        n = len(wave)
        if ring:
            blend = float(_get(v, W + "Ring/Loop Blend", 0.2))
            if blend > 0:
                win = np.sin(np.linspace(0, math.pi, n)) ** (1.0 / max(blend, 0.05) * 0.5)
                wave = win * wave + (1 - win) * np.roll(wave, n // 2)
        self.hist.append(wave)
        del self.hist[:-(trails * delay + 2)]

        u = np.linspace(0, 1, n)
        if cmode == "Solid":
            tcol = np.zeros(n)
        elif cmode == "By Amplitude":
            tcol = np.clip(np.abs(wave), 0, 1)
        else:
            tcol = (1 - np.abs(2 * u - 1)) if ring else u
        base_col = c1[None, :] + (c2 - c1)[None, :] * tcol[:, None]

        quads, colors = [], []
        if ring:
            self._phase += math.radians(float(_get(v, W + "Ring/Spin (deg/s)", 0.0))) * getattr(frame, "dt", 1 / 60.0)
            cx, cy = w / 2.0, h / 2.0
            r0 = min(w, h) / 2.0 * float(_get(v, W + "Ring/Radius", 0.7))
            step = max(1, int(_get(v, W + "Ring/Hatch Step", 3)))
        for k in range(trails):
            hw = self.hist[max(0, len(self.hist) - 1 - k * delay)]
            k_fade = 1.0 - fade * (k / float(trails)) if trails > 1 else 1.0
            col = base_col.copy()
            col[:, 3] *= k_fade
            tk = max(1.0, thick * (1.0 - 0.5 * fade * (k / float(trails))))
            if ring:
                ang = 2 * math.pi * u + self._phase + k * twist
                rk = r0 * (1.0 + k * spacing)
                rr = rk + hw * r0 * 0.45
                inner = np.stack([cx + np.cos(ang) * rk, cy + np.sin(ang) * rk], 1)
                outer = np.stack([cx + np.cos(ang) * rr, cy + np.sin(ang) * rr], 1)
                if fill == "Solid":
                    q = np.stack([inner[:-1], inner[1:], outer[1:], outer[:-1]], 1)
                    quads.append(q)
                    c = col[:-1].copy()
                    c[:, 3] *= 0.55
                    colors.append(np.repeat(c[:, None, :], 4, axis=1))
                elif fill == "Hatch":
                    idx = np.arange(0, n, step)
                    quads.append(_spokes(inner[idx], outer[idx], max(1.0, tk * 0.6)))
                    colors.append(np.repeat(col[idx][:, None, :], 4, axis=1))
                q = thick_polyline(outer, tk, closed=True)
                quads.append(q)
                cc = np.vstack([col, col[:1]])[:-1]
                colors.append(np.repeat(cc[:, None, :], 4, axis=1))
            else:
                xs = np.linspace(0, w, n)
                win = np.sin(np.pi * u) ** (taper * 3.0) if taper > 0 else 1.0
                mid = h / 2.0 + (k - (trails - 1) / 2.0) * spacing * h
                ys = mid + hw * win * (h / 2.0)
                pts = np.stack([xs, ys], 1)
                if fill == "Solid":
                    base = np.stack([xs, np.full(n, mid)], 1)
                    quads.append(np.stack([base[:-1], base[1:], pts[1:], pts[:-1]], 1))
                    c = col[:-1].copy()
                    c[:, 3] *= 0.55
                    colors.append(np.repeat(c[:, None, :], 4, axis=1))
                elif fill == "Hatch":
                    idx = np.arange(0, n, max(1, int(_get(v, W + "Ring/Hatch Step", 3))))
                    base = np.stack([xs[idx], np.full(len(idx), mid)], 1)
                    quads.append(_spokes(base, pts[idx], max(1.0, tk * 0.6)))
                    colors.append(np.repeat(col[idx][:, None, :], 4, axis=1))
                quads.append(thick_polyline(pts, tk))
                colors.append(np.repeat(col[:-1][:, None, :], 4, axis=1))
        q = np.concatenate(quads).astype(np.float32) if quads else np.zeros((0, 4, 2), np.float32)
        c = np.concatenate(colors) if colors else np.zeros((0, 4, 4), np.float32)
        self.batch.set(q, c)
        self.dots.set(np.zeros((0, 4, 2), np.float32), np.zeros((0, 4), np.float32))
        return w, h


RENDERERS["WAVEFORM"] = WaveformPlusLayer
