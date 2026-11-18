"""Stop collapsed accordion bodies from drawing over the cards below them.

The accordions in main.py (page sections) and property_editor.py (property
categories) collapse a body by setting ``height = 0``. Kivy does not clip
children to their parent, so the body's widgets kept drawing and receiving
touches on top of the next card (overlapping text, ghost toggles, clipped
sliders). Bodies are plain ``BoxLayout`` objects created with
``size_hint_y=None, height=0``; this hides such a body whenever its height is
~0 and shows it again as soon as it is expanded.

Hiding is not enough: a zero-height body lays its children out over the
neighbouring card, so taps on the next accordion header were eaten. A collapsed
body now ignores touch events entirely (they fall through to the widgets
underneath).

main.Scroll.on_touch_down also ``walk()``s the whole tree looking for vertical
EQ sliders and, on a hit, bypasses the ScrollView. The ghosts of the collapsed
Equalizer overlapped the first Sound headers, so those taps never reached the
header. Sliders inside a collapsed body therefore never report a collision.
"""


def _sync(widget, height):
    collapsed = height < 1
    widget.opacity = 0 if collapsed else 1
    widget._vooc_collapsed = collapsed


def _hidden(widget):
    p = widget.parent
    for _ in range(60):
        if p is None:
            return False
        if getattr(p, "_vooc_collapsed", False):
            return True
        p = p.parent
    return False


def _patch_sliders():
    try:
        from vooc.m3 import Slider3
    except Exception:
        return
    if getattr(Slider3, "_vooc_collapse_clip", False):
        return
    collide = Slider3.collide_point

    def collide_point(self, x, y):
        return False if _hidden(self) else collide(self, x, y)

    Slider3.collide_point = collide_point
    Slider3._vooc_collapse_clip = True


def install():
    try:
        from kivy.uix.boxlayout import BoxLayout
    except Exception:  # Kivy not available (plain unit tests)
        return
    if getattr(BoxLayout, "_vooc_collapse_clip", False):
        return
    original = BoxLayout.__init__

    def guard(orig):
        def handler(self, touch):
            if self._vooc_collapsed:
                return False
            return orig(self, touch)
        return handler

    BoxLayout._vooc_collapsed = False
    for name in ("on_touch_down", "on_touch_move", "on_touch_up"):
        setattr(BoxLayout, name, guard(getattr(BoxLayout, name)))

    def __init__(self, **kw):
        original(self, **kw)
        if kw.get("size_hint_y", 1) is None and kw.get("height", 1) == 0:
            self.bind(height=_sync)
            _sync(self, self.height)

    BoxLayout.__init__ = __init__
    BoxLayout._vooc_collapse_clip = True
    _patch_sliders()


install()
