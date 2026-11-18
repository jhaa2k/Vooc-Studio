"""Android MediaSession bridge for notification shade and lock-screen controls."""
import threading


class AndroidMediaSession:
    """Expose Vooc playback as a native Android media session.

    Android owns the system UI (Quick Settings media player / lock-screen card).
    Transport callbacks are marshalled back onto Kivy's main thread.
    """

    def __init__(self, on_play, on_pause, on_next, on_previous, on_seek):
        self.controller = None
        self.listener = None
        try:
            from jnius import autoclass, PythonJavaClass, java_method
            from kivy.clock import Clock
            Controller = autoclass("com.jhaa2k.vooc.MediaSessionController")
            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            callbacks = {
                "play": on_play, "pause": on_pause, "next": on_next,
                "previous": on_previous, "seek": on_seek,
            }

            class Listener(PythonJavaClass):
                __javainterfaces__ = ["com/jhaa2k/vooc/MediaSessionController$Listener"]
                __javacontext__ = "app"

                def _dispatch(self, key, value=None):
                    callback = callbacks.get(key)
                    if callback is not None:
                        Clock.schedule_once(lambda _dt: callback(value) if value is not None else callback(), 0)

                @java_method("()V")
                def onPlay(self):
                    self._dispatch("play")

                @java_method("()V")
                def onPause(self):
                    self._dispatch("pause")

                @java_method("()V")
                def onNext(self):
                    self._dispatch("next")

                @java_method("()V")
                def onPrevious(self):
                    self._dispatch("previous")

                @java_method("(J)V")
                def onSeek(self, position_ms):
                    self._dispatch("seek", int(position_ms))

            self.listener = Listener()
            self.controller = Controller(activity, self.listener)
        except Exception as exc:
            print("Vooc Android media session unavailable: %s" % exc)

    def update(self, title, artist, album, art_path, position_ms, duration_ms, playing, active=True):
        controller = self.controller
        if controller is None:
            return
        try:
            controller.update(
                str(title or "Unknown track"), str(artist or "Vooc"),
                str(album or ""), str(art_path or ""),
                int(max(0, position_ms)), int(max(0, duration_ms)),
                bool(playing), bool(active),
            )
        except Exception as exc:
            print("Vooc media session update failed: %s" % exc)

    def release(self):
        controller, self.controller = self.controller, None
        self.listener = None
        if controller is not None:
            try:
                controller.release()
            except Exception as exc:
                print("Vooc media session release failed: %s" % exc)
