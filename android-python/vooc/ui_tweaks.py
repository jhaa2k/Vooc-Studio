"""Move the preview's "Live/Idle" and template chips out of the preview.

main.VoocApp builds both chips *inside* the preview stage, on top of the live
visual. They now sit in a slim status row directly below the preview card
(never over or above it). A light poll re-applies the move whenever the UI is
rebuilt (theme switch, aspect-ratio change), since the chips are recreated
inside the stage each time.
"""


def _move(root):
    status = getattr(root, "status", None)
    chip = getattr(root, "style_chip", None)
    frame = getattr(root, "visual_frame", None)
    if status is None or chip is None or frame is None or frame.parent is None:
        return
    if getattr(status.parent, "_vooc_chips", False):
        return
    from kivy.metrics import dp
    from kivy.uix.boxlayout import BoxLayout
    from vooc.m3 import T

    for w in (status, chip):
        if w.parent is not None:
            w.parent.remove_widget(w)
        w.pos_hint = {}
    row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(8), padding=(dp(2), dp(4), dp(2), dp(4)))
    row._vooc_chips = True
    status.size_hint = (None, 1)
    status.width = dp(104)
    chip.size_hint = (1, 1)
    for box, txt in ((status, getattr(root, "status_text", None)), (chip, getattr(root, "style_text", None))):
        box.bg = list(T.surface2)
        box.line = list(T.a("outline_var", .6)) if hasattr(T, "a") else box.line
        if txt is not None:
            txt.color = T.on_surface
    row.add_widget(status)
    row.add_widget(chip)
    parent = frame.parent
    parent.add_widget(row, index=parent.children.index(frame))


def install():
    try:
        from kivy.app import App
        from kivy.clock import Clock
    except Exception:  # plain unit tests without Kivy
        return

    def tick(_dt):
        app = App.get_running_app()
        root = getattr(app, "root", None)
        if root is not None:
            try:
                _move(root)
            except Exception:
                pass

    Clock.schedule_interval(tick, 0.25)


install()
