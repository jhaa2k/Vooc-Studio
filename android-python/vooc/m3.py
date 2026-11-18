"""Material 3 components for Vooc, drawn with Kivy graphics (no image assets).

Dark + light colour schemes with an acid-green primary. Every interactive
widget gives immediate visual feedback, and value widgets (sliders, switches,
chips, selects) report every change instantly through ``on_change``.
"""
import math

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle, Triangle
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget


def _hex(value, alpha=1.0):
    h = str(value).lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    a = int(h[6:8], 16) / 255.0 if len(h) >= 8 else alpha
    return rgb + [a]


SCHEMES = {
    "dark": {
        "bg": "#0B0E0A", "surface": "#111610", "surface1": "#171D15", "surface2": "#1C2419",
        "surface3": "#283322", "outline": "#46523D", "outline_var": "#303B2A",
        "on_surface": "#F1F5EA", "on_var": "#A6B19B",
        "primary": "#C6FF00", "on_primary": "#10140B",
        "primary_container": "#34451A", "on_primary_container": "#E2FF9A",
        "secondary": "#2DD4BF", "secondary_container": "#123B37", "on_secondary_container": "#A7F3E8",
        "error": "#DC6B6B", "scrim": "#000000",
    },
    "light": {
        "bg": "#F8FAFC", "surface": "#FFFFFF", "surface1": "#FFFFFFE8", "surface2": "#F1F5F9",
        "surface3": "#E8EEF4", "outline": "#D7E0E8", "outline_var": "#E5EBF0",
        "on_surface": "#1A1A1A", "on_var": "#64748B",
        "primary": "#32CD32", "on_primary": "#FFFFFF",
        "primary_container": "#DCFCE7", "on_primary_container": "#14532D",
        "secondary": "#0D9488", "secondary_container": "#CCFBF1", "on_secondary_container": "#134E4A",
        "error": "#B91C1C", "scrim": "#0F172A",
    },
}


class _Theme:
    dark = True
    seed = None              # "#RRGGBB" -> generated scheme, None -> built-in acid scheme
    contrast = "Standard"
    vision = "None"
    _cache = None

    def configure(self, dark=None, seed=None, contrast=None, vision=None):
        if dark is not None:
            self.dark = bool(dark)
        self.seed = (seed or None) if seed is not False else None
        if contrast:
            self.contrast = contrast
        if vision:
            self.vision = vision
        self._cache = None

    def scheme(self):
        key = (self.dark, self.seed, self.contrast, self.vision)
        if self._cache is None or self._cache[0] != key:
            from .theme_engine import build_scheme
            base = SCHEMES["dark" if self.dark else "light"]
            try:
                sc = build_scheme(self.dark, base, self.seed, self.contrast, self.vision)
            except Exception:
                sc = base
            self._cache = (key, sc)
        return self._cache[1]

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        scheme = self.scheme()
        if name in scheme:
            return _hex(scheme[name])
        raise AttributeError(name)

    def a(self, name, alpha):
        c = getattr(self, name)
        return c[:3] + [alpha]


T = _Theme()

# Shared appearance tokens for every reusable surface.
UI_RADIUS = dp(0)
UI_BORDERS = False

def configure_ui_style(radius=None, borders=None):
    global UI_RADIUS, UI_BORDERS
    if radius is not None:
        UI_RADIUS = dp(0)
    if borders is not None:
        UI_BORDERS = False



def lbl(text="", size=14, color=None, bold=False, halign="left", valign="middle", shorten=True, **kw):
    w = Label(text=text, font_name=kw.pop("font_name", "Roboto"), font_size=sp(size), color=color or T.on_surface, bold=bold, halign=halign,
              valign=valign, shorten=shorten, shorten_from="right", **kw)
    w.bind(size=lambda o, s: setattr(o, "text_size", s))
    return w


class Box(BoxLayout):
    """BoxLayout with optional rounded fill / outline."""
    bg = ListProperty([0, 0, 0, 0])
    line = ListProperty([0, 0, 0, 0])
    radius = NumericProperty(0)

    def __init__(self, **kw):
        # Consistent subtle corners across all app surfaces.
        kw["radius"] = 0
        super().__init__(**kw)
        with self.canvas.before:
            self._shadow_color = Color(0, 0, 0, 0)
            self._shadow = RoundedRectangle(radius=[self.radius])
            self._c = Color(*self.bg)
            self._r = RoundedRectangle(radius=[self.radius])
            self._lc = Color(*self.line)
            # width > 1 forces Kivy's triangle path; 1px GL_LINES drop out on some GPUs
            self._l = Line(width=max(1.05, dp(1)))
        self.bind(pos=self._u, size=self._u, bg=self._u, line=self._u, radius=self._u)
        self._u()

    def _u(self, *_):
        self._shadow.pos = (self.x, self.y - dp(2))
        self._shadow.size = (self.width, self.height + dp(2))
        self._shadow.radius = [self.radius + dp(2)]
        self._c.rgba = self.bg
        self._r.pos, self._r.size, self._r.radius = self.pos, self.size, [self.radius]
        self._lc.rgba = self.line if UI_BORDERS else [0, 0, 0, 0]
        self._l.rectangle = (self.x + .5, self.y + .5, max(1, self.width - 1), max(1, self.height - 1))


def card(**kw):
    kw.setdefault("orientation", "vertical")
    kw.setdefault("padding", dp(14))
    kw.setdefault("spacing", dp(8))
    kw.setdefault("size_hint_y", None)
    kw.setdefault("radius", UI_RADIUS)
    kw.setdefault("bg", T.surface1)
    b = Box(**kw)
    b.bind(minimum_height=b.setter("height"))
    return b


def section(text, hint=""):
    row = BoxLayout(size_hint_y=None, height=dp(30), padding=(dp(4), 0))
    row._vooc_section_heading = True
    row.add_widget(lbl(str(text).upper(), 13, T.primary, bold=True, font_name="Roboto"))
    if hint:
        row.add_widget(lbl(hint, 11, T.on_var, halign="right"))
    return row


# ---------------------------------------------------------------- icons
class Icon(Widget):
    name = StringProperty("")
    tint = ListProperty([1, 1, 1, 1])

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(pos=self.redraw, size=self.redraw, name=self.redraw, tint=self.redraw)
        self.redraw()

    STROKE = 0.06          # stroke half-width relative to the icon radius (thin outline style)

    def redraw(self, *_):
        self.canvas.clear()
        s = min(self.width, self.height) / 2.0
        cx, cy = self.x + self.width / 2.0, self.y + self.height / 2.0
        w = max(dp(0.55), s * self.STROKE)
        n = self.name
        with self.canvas:
            Color(*self.tint)
            draw = getattr(self, "_i_" + n, None)
            if draw:
                draw(cx, cy, s, w)

    # helpers ---------------------------------------------------------
    @staticmethod
    def _ln(pts, w, close=False):
        Line(points=pts, width=w, cap="round", joint="round", close=close)

    def _chev(self, x, y, dx, dy, w):
        """Open arrow head at (x, y) pointing along (dx, dy)."""
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L
        k = L
        self._ln([x - ux * k - uy * k * .8, y - uy * k + ux * k * .8, x, y,
                  x - ux * k + uy * k * .8, y - uy * k - ux * k * .8], w)

    # media -----------------------------------------------------------
    def _i_play(self, cx, cy, s, w):
        self._ln([cx - s * .3, cy - s * .48, cx - s * .3, cy + s * .48, cx + s * .5, cy], w, True)

    def _i_pause(self, cx, cy, s, w):
        for x in (-.24, .24):
            self._ln([cx + s * x, cy - s * .45, cx + s * x, cy + s * .45], w)

    def _i_next(self, cx, cy, s, w, k=1):
        self._ln([cx - k * s * .42, cy - s * .4, cx - k * s * .42, cy + s * .4, cx + k * s * .2, cy], w, True)
        x = cx + k * s * .38
        self._ln([x, cy - s * .42, x, cy + s * .42], w)

    def _i_prev(self, cx, cy, s, w):
        self._i_next(cx, cy, s, w, -1)

    def _i_shuffle(self, cx, cy, s, w):
        self._ln([cx - s * .6, cy - s * .35, cx - s * .25, cy - s * .35, cx + s * .2, cy + s * .35, cx + s * .58, cy + s * .35], w)
        self._ln([cx - s * .6, cy + s * .35, cx - s * .25, cy + s * .35, cx + s * .2, cy - s * .35, cx + s * .58, cy - s * .35], w)
        for y in (.35, -.35):
            self._chev(cx + s * .62, cy + s * y, s * .2, 0, w)

    def _i_repeat(self, cx, cy, s, w, one=False):
        Line(rounded_rectangle=(cx - s * .58, cy - s * .34, s * 1.16, s * .68, s * .22), width=w)
        self._chev(cx + s * .22, cy + s * .34, s * .18, 0, w)
        self._chev(cx - s * .22, cy - s * .34, -s * .18, 0, w)
        if one:
            self._ln([cx - s * .06, cy + s * .08, cx + s * .04, cy + s * .16, cx + s * .04, cy - s * .16], w)

    def _i_repeat_one(self, cx, cy, s, w):
        self._i_repeat(cx, cy, s, w, True)

    def _i_note(self, cx, cy, s, w):
        Line(ellipse=(cx - s * .55, cy - s * .62, s * .48, s * .38), width=w)
        self._ln([cx - s * .07, cy - s * .44, cx - s * .07, cy + s * .58, cx + s * .45, cy + s * .38], w)

    def _i_bars(self, cx, cy, s, w):
        for i, h in enumerate((.45, .85, .6, 1.0, .35)):
            x = cx - s * .56 + i * s * .28
            self._ln([x, cy - s * .55, x, cy - s * .55 + s * 1.1 * h], w)

    def _i_tune(self, cx, cy, s, w):
        for i, k in enumerate((.25, -.3, .1)):
            x = cx - s * .45 + i * s * .45
            self._ln([x, cy - s * .6, x, cy + s * k - s * .14], w)
            self._ln([x, cy + s * k + s * .14, x, cy + s * .6], w)
            Line(circle=(x, cy + s * k, s * .14), width=w)

    def _i_settings(self, cx, cy, s, w):
        # Use a clear, compact settings glyph in the top bar.
        self._i_tune(cx, cy, s, w)

    def _i_layers(self, cx, cy, s, w):
        self._ln([cx - s * .6, cy + s * .2, cx, cy + s * .52, cx + s * .6, cy + s * .2, cx, cy - s * .12], w, True)
        for dy in (-.12, -.42):
            self._ln([cx - s * .6, cy + s * (dy + .02), cx, cy + s * (dy - .3), cx + s * .6, cy + s * (dy + .02)], w)

    def _i_studio(self, cx, cy, s, w):
        for dx in (-1, 1):
            for dy in (-1, 1):
                Line(rounded_rectangle=(cx + dx * s * .3 - s * .22, cy + dy * s * .3 - s * .22, s * .44, s * .44, s * .1),
                     width=w)

    # actions ---------------------------------------------------------
    def _i_plus(self, cx, cy, s, w):
        self._ln([cx - s * .5, cy, cx + s * .5, cy], w)
        self._ln([cx, cy - s * .5, cx, cy + s * .5], w)

    def _i_close(self, cx, cy, s, w):
        self._ln([cx - s * .4, cy - s * .4, cx + s * .4, cy + s * .4], w)
        self._ln([cx - s * .4, cy + s * .4, cx + s * .4, cy - s * .4], w)

    def _i_check(self, cx, cy, s, w):
        self._ln([cx - s * .45, cy, cx - s * .12, cy - s * .35, cx + s * .5, cy + s * .35], w)

    def _i_eye(self, cx, cy, s, w, off=False):
        self._ln([cx - s * .65, cy, cx - s * .3, cy + s * .34, cx, cy + s * .4, cx + s * .3, cy + s * .34, cx + s * .65, cy,
                  cx + s * .3, cy - s * .34, cx, cy - s * .4, cx - s * .3, cy - s * .34], w, True)
        Line(circle=(cx, cy, s * .17), width=w)
        if off:
            self._ln([cx - s * .6, cy - s * .6, cx + s * .6, cy + s * .6], w)

    def _i_eye_off(self, cx, cy, s, w):
        self._i_eye(cx, cy, s, w, True)

    def _i_lock(self, cx, cy, s, w, open_=False):
        Line(rounded_rectangle=(cx - s * .45, cy - s * .55, s * .9, s * .65, s * .12), width=w)
        r = s * .27
        top = cy + s * .3
        Line(circle=(cx, top, r, -90, 90), width=w)
        self._ln([cx - r, top, cx - r, cy + s * .1], w)
        self._ln([cx + r, top, cx + r, cy + (s * .22 if open_ else s * .1)], w)

    def _i_unlock(self, cx, cy, s, w):
        self._i_lock(cx, cy, s, w, True)

    def _i_up(self, cx, cy, s, w, k=1):
        self._ln([cx - s * .4, cy - k * s * .15, cx, cy + k * s * .25, cx + s * .4, cy - k * s * .15], w)

    def _i_down(self, cx, cy, s, w):
        self._i_up(cx, cy, s, w, -1)

    def _i_delete(self, cx, cy, s, w):
        self._ln([cx - s * .5, cy + s * .4, cx + s * .5, cy + s * .4], w)
        self._ln([cx - s * .15, cy + s * .55, cx + s * .15, cy + s * .55], w)
        self._ln([cx - s * .38, cy + s * .3, cx - s * .3, cy - s * .55, cx + s * .3, cy - s * .55, cx + s * .38, cy + s * .3], w)
        for x in (-.1, .1):
            self._ln([cx + s * x, cy + s * .15, cx + s * x, cy - s * .35], w)

    def _i_copy(self, cx, cy, s, w):
        Line(rounded_rectangle=(cx - s * .55, cy - s * .55, s * .75, s * .75, s * .12), width=w)
        self._ln([cx - s * .25, cy + s * .35, cx - s * .25, cy + s * .55, cx + s * .55, cy + s * .55,
                  cx + s * .55, cy - s * .25, cx + s * .35, cy - s * .25], w)

    def _i_save(self, cx, cy, s, w):
        self._ln([cx, cy + s * .55, cx, cy - s * .2], w)
        self._ln([cx - s * .3, cy + s * .1, cx, cy - s * .22, cx + s * .3, cy + s * .1], w)
        self._ln([cx - s * .55, cy - s * .2, cx - s * .55, cy - s * .55, cx + s * .55, cy - s * .55, cx + s * .55, cy - s * .2], w)

    def _i_folder(self, cx, cy, s, w):
        self._ln([cx - s * .6, cy + s * .4, cx - s * .15, cy + s * .4, cx, cy + s * .25, cx + s * .6, cy + s * .25,
                  cx + s * .6, cy - s * .45, cx - s * .6, cy - s * .45], w, True)

    def _i_sun(self, cx, cy, s, w):
        Line(circle=(cx, cy, s * .26), width=w)
        for i in range(8):
            a = i * math.pi / 4
            self._ln([cx + math.cos(a) * s * .45, cy + math.sin(a) * s * .45,
                      cx + math.cos(a) * s * .62, cy + math.sin(a) * s * .62], w)

    def _i_moon(self, cx, cy, s, w):
        Line(circle=(cx, cy, s * .55), width=w)
        Line(circle=(cx, cy, s * .55, 180, 360), width=w)
        self._ln([cx, cy - s * .55, cx, cy + s * .55], w)

    _i_theme = _i_moon

    def _i_text(self, cx, cy, s, w):
        self._ln([cx - s * .5, cy + s * .5, cx + s * .5, cy + s * .5], w)
        self._ln([cx, cy + s * .5, cx, cy - s * .55], w)

    def _i_image(self, cx, cy, s, w):
        Line(rounded_rectangle=(cx - s * .6, cy - s * .5, s * 1.2, s, s * .15), width=w)
        self._ln([cx - s * .45, cy - s * .3, cx - s * .1, cy + s * .1, cx + s * .1, cy - s * .1, cx + s * .25, cy + s * .05,
                  cx + s * .45, cy - s * .3], w)
        Line(circle=(cx + s * .22, cy + s * .26, s * .09), width=w)

    def _i_back(self, cx, cy, s, w):
        self._ln([cx + s * .5, cy, cx - s * .5, cy], w)
        self._ln([cx - s * .1, cy + s * .42, cx - s * .52, cy, cx - s * .1, cy - s * .42], w)

    def _i_reset(self, cx, cy, s, w):
        Line(circle=(cx, cy, s * .45, 60, 360), width=w)
        self._chev(cx + s * .39, cy + s * .23, s * .1, s * .17, w)

    def _i_star(self, cx, cy, s, w):
        pts = []
        for k in range(10):
            r = s * (.62 if k % 2 == 0 else .27)
            a = math.pi / 2 + k * math.pi / 5
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
        self._ln(pts, w, True)

    def _i_star_on(self, cx, cy, s, w):
        outer = []
        for k in range(10):
            r = s * (.66 if k % 2 == 0 else .29)
            a = math.pi / 2 + k * math.pi / 5
            outer.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        for k in range(10):
            (x1, y1), (x2, y2) = outer[k], outer[(k + 1) % 10]
            Triangle(points=[cx, cy, x1, y1, x2, y2])
        self._ln([c for p in outer for c in p], w, True)

    def _i_eyedropper(self, cx, cy, s, w):
        self._ln([cx - s * .55, cy - s * .55, cx + s * .12, cy + s * .12], w)
        self._ln([cx - s * .02, cy + s * .4, cx + s * .4, cy - s * .02], w)
        Line(circle=(cx + s * .36, cy + s * .36, s * .2), width=w)

    def _i_undo(self, cx, cy, s, w):
        Line(circle=(cx + s * .05, cy - s * .05, s * .45, -80, 170), width=w)
        self._chev(cx - s * .4, cy - s * .02, -s * .04, -s * .2, w)

    def _i_redo(self, cx, cy, s, w):
        Line(circle=(cx - s * .05, cy - s * .05, s * .45, -170, 80), width=w)
        self._chev(cx + s * .4, cy - s * .02, s * .04, -s * .2, w)

    def _i_info(self, cx, cy, s, w):
        Line(circle=(cx, cy, s * .55), width=w)
        Ellipse(pos=(cx - w * 1.2, cy + s * .22), size=(w * 2.4, w * 2.4))
        self._ln([cx, cy - s * .3, cx, cy + s * .05], w)

    def _i_sparkle(self, cx, cy, s, w):
        for dx, dy, r in ((0, 0, .55), (.45, .45, .2), (-.45, -.42, .16)):
            x, y, rr = cx + dx * s, cy + dy * s, r * s
            q = rr * .22
            self._ln([x, y + rr, x + q, y + q, x + rr, y, x + q, y - q, x, y - rr, x - q, y - q, x - rr, y, x - q, y + q], w, True)

    def _i_export(self, cx, cy, s, w):
        self._ln([cx, cy - s * .2, cx, cy + s * .55], w)
        self._ln([cx - s * .3, cy + s * .25, cx, cy + s * .57, cx + s * .3, cy + s * .25], w)
        self._ln([cx - s * .55, cy + s * .05, cx - s * .55, cy - s * .55, cx + s * .55, cy - s * .55, cx + s * .55, cy + s * .05], w)

    def _i_more(self, cx, cy, s, w):
        for dy in (-.4, 0, .4):
            Ellipse(pos=(cx - s * .08, cy + dy * s - s * .08), size=(s * .16, s * .16))


# ---------------------------------------------------------------- touch guard
class TouchGuard:
    """Mixin for ButtonBehavior widgets: a press that slides more than a few dp
    (scrolling, swiping) is cancelled instead of firing, so brushing past a
    button never triggers it."""
    GUARD_DIST = dp(10)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.ud.setdefault("guard_start", touch.pos)
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            sx, sy = touch.ud.get("guard_start", touch.pos)
            if abs(touch.x - sx) > self.GUARD_DIST or abs(touch.y - sy) > self.GUARD_DIST:
                touch.ud["guard_cancel"] = True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self and touch.ud.get("guard_cancel"):
            touch.ungrab(self)
            self.state = "normal"
            try:
                Animation(a=0, d=0.2).start(self._sc)
            except Exception:
                pass
            return True
        return super().on_touch_up(touch)


# ---------------------------------------------------------------- buttons
class Tap(TouchGuard, ButtonBehavior, Box):
    """Pressable square-corner surface with no ripple overlay."""

    def __init__(self, on_tap=None, **kw):
        super().__init__(**kw)
        self._base = list(self.bg)
        with self.canvas.after:
            self._sc = Color(1, 1, 1, 0)
            self._sr = RoundedRectangle(radius=[self.radius])
        self.bind(pos=self._us, size=self._us, radius=self._us)
        self._us()
        if on_tap:
            self.bind(on_release=lambda *_: on_tap())

    def _us(self, *_):
        self._sr.pos, self._sr.size, self._sr.radius = self.pos, self.size, [self.radius]

    def on_press(self):
        self._sc.rgba = (0, 0, 0, 0)

    def on_release(self):
        self._sc.rgba = (0, 0, 0, 0)


class Button3(Tap):
    """M3 button. kind: filled | tonal | outlined | text."""

    def __init__(self, text, on_tap=None, kind="tonal", icon=None, height=dp(44), fs=14, **kw):
        colors = {
            "filled": (T.primary, T.on_primary, [0, 0, 0, 0]),
            "tonal": (T.secondary_container, T.on_secondary_container, [0, 0, 0, 0]),
            "outlined": ([0, 0, 0, 0], T.primary, T.outline),
            "text": ([0, 0, 0, 0], T.primary, [0, 0, 0, 0]),
            "surface": (T.surface3, T.on_surface, [0, 0, 0, 0]),
        }[kind]
        kw.setdefault("size_hint_y", None)
        super().__init__(on_tap=on_tap, bg=colors[0], line=colors[2], radius=UI_RADIUS, height=height,
                         padding=(dp(16), 0), spacing=dp(8), **kw)
        self.fg = colors[1]
        inner = BoxLayout(spacing=dp(8))
        self.add_widget(Widget(size_hint_x=0.0001))
        if icon:
            self.icon = Icon(name=icon, tint=self.fg, size_hint=(None, 1), width=dp(18))
            inner.add_widget(self.icon)
        self.label = lbl(text, fs, self.fg, bold=True, halign="center" if not icon else "left")
        inner.add_widget(self.label)
        self.add_widget(inner)
        self._inner = inner
        if icon:
            # narrow phones / large font scale: drop the icon before the text gets cut
            self.bind(width=self._fit)
            self.label.bind(text=self._fit)

    def _fit(self, *_):
        # cheap estimate (bold Roboto ~0.6 em per glyph) - no extra native text measuring
        need = len(self.label.text) * self.label.font_size * 0.6
        room = self.width - self.padding[0] * 2 - self.spacing - dp(6)
        show = need + dp(18) + dp(8) <= room
        self.icon.opacity = 1 if show else 0
        self.icon.width = dp(18) if show else 0
        self._inner.spacing = dp(8) if show else 0
        self.label.halign = "left" if show else "center"
        if not show and need > room and self.padding[0] > dp(8):
            self.padding = (dp(8), 0)

    @property
    def text(self):
        return self.label.text

    @text.setter
    def text(self, v):
        self.label.text = v


class IconBtn(TouchGuard, ButtonBehavior, Widget):
    """Square icon button. kind: standard | tonal | filled."""
    active = BooleanProperty(False)

    def __init__(self, icon, on_tap=None, kind="standard", size=dp(44), tint=None, **kw):
        kw.setdefault("size_hint", (None, None))
        super().__init__(size=(size, size), **kw)
        self.kind = kind
        self._tint = tint
        with self.canvas.before:
            self._c = Color(0, 0, 0, 0)
            self._e = Rectangle()
            self._sc = Color(0, 0, 0, 0)
            self._se = Rectangle()
        self.icon = Icon(name=icon)
        self.add_widget(self.icon)
        self.bind(pos=self._u, size=self._u, active=self._colors)
        self._colors()
        if on_tap:
            self.bind(on_release=lambda *_: on_tap())

    def _colors(self, *_):
        if self.kind == "filled" or (self.kind == "toggle" and self.active):
            bg, fg = T.primary, T.on_primary
        elif self.kind == "tonal":
            bg, fg = T.surface3, T.on_surface
        else:
            bg, fg = [0, 0, 0, 0], (T.primary if self.active else (self._tint or T.on_var))
        self._c.rgba = bg
        self.icon.tint = fg

    def set_icon(self, name):
        self.icon.name = name

    def _u(self, *_):
        self._e.pos, self._e.size = self.pos, self.size
        self._se.pos, self._se.size = self.pos, self.size
        p = self.width * 0.27
        self.icon.pos = (self.x + p, self.y + p)
        self.icon.size = (self.width - 2 * p, self.height - 2 * p)

    def on_press(self):
        self._sc.rgba = (0, 0, 0, 0)

    def on_release(self):
        self._sc.rgba = (0, 0, 0, 0)


# ---------------------------------------------------------------- chips
class Chip(Tap):
    selected = BooleanProperty(False)

    def __init__(self, text, on_tap=None, selected=False, swatch=None, **kw):
        kw.setdefault("size_hint", (None, None))
        kw.setdefault("height", dp(34))
        super().__init__(on_tap=on_tap, radius=dp(3), padding=(dp(12), 0), spacing=dp(6), **kw)
        self.swatch = swatch
        if swatch:
            self._sw = Widget(size_hint=(None, None), size=(dp(16), dp(16)))
            with self._sw.canvas:
                Color(*swatch[0])
                self._swe = Ellipse()
                Color(*swatch[1])
                self._swe2 = Ellipse(angle_start=0, angle_end=180)
            self._sw.bind(pos=self._usw)
            self.add_widget(BoxLayout(size_hint=(None, 1), width=dp(16), padding=(0, dp(9))))
            self.children[0].add_widget(self._sw)
        self.check = Icon(name="check", size_hint=(None, 1), width=dp(16))
        self.label = Label(text=text, font_size=sp(13), bold=True, size_hint=(None, 1))
        self.label.bind(texture_size=self._fit)
        self.add_widget(self.check)
        self.add_widget(self.label)
        self.bind(selected=self._style)
        self.selected = selected
        self._style()

    def _usw(self, *_):
        self._swe.pos, self._swe.size = self._sw.pos, self._sw.size
        self._swe2.pos, self._swe2.size = self._sw.pos, self._sw.size

    def _fit(self, *_):
        self.label.width = self.label.texture_size[0]
        self.width = self.label.width + dp(24) + (dp(22) if self.selected else 0) + (dp(22) if self.swatch else 0)

    def _style(self, *_):
        if self.selected:
            self.bg, self.line = T.primary_container, [0, 0, 0, 0]
            fg = T.on_primary_container
            self.check.width, self.check.opacity = dp(16), 1
        else:
            self.bg, self.line = [0, 0, 0, 0], T.outline
            fg = T.on_var
            self.check.width, self.check.opacity = 0, 0
        self.label.color = fg
        self.check.tint = fg
        self._fit()


class ChipGroup(ScrollView):
    """Horizontally scrolling single- (or multi-) select chip row."""

    def __init__(self, options, value, on_change, swatches=None, wrap=False, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(40))
        super().__init__(do_scroll_y=False, bar_width=0, **kw)
        self.on_change = on_change
        self.row = BoxLayout(size_hint_x=None, spacing=dp(8), padding=(dp(2), dp(3)))
        self.row.bind(minimum_width=self.row.setter("width"))
        self.chips = {}
        for opt in options:
            c = Chip(str(opt), selected=(str(opt) == str(value)),
                     swatch=(swatches or {}).get(opt))
            c.bind(on_release=lambda w, o=opt: self.select(o))
            self.chips[str(opt)] = c
            self.row.add_widget(c)
        self.add_widget(self.row)

    def select(self, opt, notify=True):
        for k, c in self.chips.items():
            c.selected = (k == str(opt))
        if notify:
            self.on_change(opt)


# ---------------------------------------------------------------- slider
class Slider3(Widget):
    """Thin M3 slider with a live value bubble. Horizontal or vertical,
    optional bipolar fill (from centre) for EQ / balance.

    Touch rules (no accidental changes):
      * a plain tap never moves the value;
      * the value only follows the finger after it slides ``DRAG_START`` along
        the slider axis (a vertical swipe on a horizontal slider scrolls the
        page instead);
      * a double tap resets to ``default`` (when given).
    ``on_change(value)`` fires on every movement, ``on_commit(value)`` on release.
    """
    value = NumericProperty(0.0)
    DRAG_START = dp(6)
    DOUBLE_TAP = 0.32

    def __init__(self, lo=0.0, hi=1.0, value=0.0, step=0.0, on_change=None, on_commit=None,
                 fmt=None, vertical=False, bipolar=False, default=None, on_reset=None, **kw):
        if vertical:
            kw.setdefault("size_hint_x", None)
            kw.setdefault("width", dp(30))
        else:
            kw.setdefault("size_hint_y", None)
            kw.setdefault("height", dp(30))
        super().__init__(**kw)
        self.lo, self.hi, self.step = float(lo), float(hi), float(step or 0)
        self.vertical, self.bipolar = vertical, bipolar
        self.on_change, self.on_commit = on_change, on_commit
        self.default, self.on_reset = default, on_reset
        self.fmt = fmt or (lambda v: ("%d" % round(v)) if self.step >= 1 else ("%.3f" % v))
        self.dragging = False
        self._pending = None          # touch that may become a drag
        self._last_tap = 0.0
        self._grow = 0.0
        with self.canvas:
            self._ci = Color(*T.surface3)
            self._ti = RoundedRectangle()
            self._ca = Color(*T.primary)
            self._ta = RoundedRectangle()
            self._cz = Color(*T.a("on_var", 0.6))
            self._zero = Rectangle()
            self._ch = Color(*T.a("primary", 0.0))
            self._halo = Ellipse()
            self._ct = Color(*T.primary)
            self._th = Ellipse()
        with self.canvas.after:
            self._cb = Color(*T.a("primary", 0))
            self._bubble = RoundedRectangle()
            self._bt = Color(*T.a("on_primary", 0))
            self._btxt = Rectangle()
        self.value = max(self.lo, min(self.hi, float(value)))
        self.bind(pos=self._draw, size=self._draw, value=self._draw)
        self._draw()

    def _frac(self):
        return 0.0 if self.hi == self.lo else (self.value - self.lo) / (self.hi - self.lo)

    def _draw(self, *_):
        f = self._frac()
        th = dp(3)                                   # thin track
        knob = dp(14) + self._grow * dp(4)
        if self.vertical:
            x = (self.x + self.width / 2.0) - th / 2
            y0, L = self.y + dp(10), max(1, self.height - dp(20))
            pos = y0 + f * L
            self._ti.pos, self._ti.size, self._ti.radius = (x, y0), (th, L), [0]
            if self.bipolar:
                mid = y0 + L * ((0 - self.lo) / (self.hi - self.lo))
                a, b = sorted((mid, pos))
                self._ta.pos, self._ta.size = (x, a), (th, max(0, b - a))
                self._zero.pos, self._zero.size = (x - dp(3), mid - dp(.5)), (th + dp(6), dp(1))
            else:
                self._ta.pos, self._ta.size = (x, y0), (th, pos - y0)
                self._zero.size = (0, 0)
            cx, cy = (self.x + self.width / 2.0), pos
        else:
            y = (self.y + self.height / 2.0) - th / 2
            x0, L = self.x + dp(10), max(1, self.width - dp(20))
            pos = x0 + f * L
            self._ti.pos, self._ti.size, self._ti.radius = (x0, y), (L, th), [0]
            if self.bipolar:
                mid = x0 + L * ((0 - self.lo) / (self.hi - self.lo))
                a, b = sorted((mid, pos))
                self._ta.pos, self._ta.size = (a, y), (max(0, b - a), th)
                self._zero.pos, self._zero.size = (mid - dp(.5), y - dp(3)), (dp(1), th + dp(6))
            else:
                self._ta.pos, self._ta.size = (x0, y), (pos - x0, th)
                self._zero.size = (0, 0)
            cx, cy = pos, (self.y + self.height / 2.0)
        self._ta.radius = [0]
        self._th.pos, self._th.size = (cx - knob / 2, cy - knob / 2), (knob, knob)
        r = dp(15) * self._grow
        self._halo.pos, self._halo.size = (cx - r, cy - r), (2 * r, 2 * r)
        self._ch.a = 0.18 * self._grow
        if self.dragging:
            from kivy.core.text import Label as CoreLabel
            t = CoreLabel(text=self.fmt(self.value), font_size=sp(12), bold=True)
            t.refresh()
            tw, tht = t.texture.size
            bw, bh = tw + dp(16), dp(24)
            bx = cx - bw / 2
            by = cy + dp(16)
            if self.vertical:
                bx = self.right + dp(4) if self.right + bw + dp(4) < (self.parent.right if self.parent else 1e9) else self.x - bw - dp(4)
                by = cy - bh / 2
            self._bubble.pos, self._bubble.size, self._bubble.radius = (bx, by), (bw, bh), [0]
            self._btxt.texture = t.texture
            self._btxt.pos, self._btxt.size = (bx + (bw - tw) / 2, by + (bh - tht) / 2), (tw, tht)
            self._cb.a, self._bt.a = 1, 1
        else:
            self._cb.a, self._bt.a = 0, 0

    def _set_from_touch(self, touch):
        if self.vertical:
            f = (touch.y - self.y - dp(10)) / max(1, self.height - dp(20))
        else:
            f = (touch.x - self.x - dp(10)) / max(1, self.width - dp(20))
        self._apply(self.lo + max(0.0, min(1.0, f)) * (self.hi - self.lo))

    def _apply(self, v):
        if self.step:
            v = round((v - self.lo) / self.step) * self.step + self.lo
        v = max(self.lo, min(self.hi, v))
        if abs(v - self.value) > 1e-9:
            self.value = v
            if self.on_change:
                self.on_change(v)

    def reset(self):
        if self.default is None:
            return
        self._apply(float(self.default))
        if self.on_commit:
            self.on_commit(self.value)
        if self.on_reset:
            self.on_reset(self.value)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos) or touch.is_mouse_scrolling:
            return False
        now = Clock.get_time()
        if self.default is not None and now - self._last_tap < self.DOUBLE_TAP:
            self._last_tap = 0.0
            self.reset()
            return True
        self._last_tap = now
        touch.grab(self)
        touch.ud["slider_start"] = touch.pos
        self._pending = touch
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
        if self._pending is touch:
            sx, sy = touch.ud.get("slider_start", touch.pos)
            along = abs(touch.y - sy) if self.vertical else abs(touch.x - sx)
            across = abs(touch.x - sx) if self.vertical else abs(touch.y - sy)
            if across > self.DRAG_START * 1.5 and across > along:
                # the user is scrolling the page, not using the slider
                self._pending = None
                touch.ungrab(self)
                return False
            if along < self.DRAG_START:
                return True
            self._pending = None
            self._last_tap = 0.0
            self.dragging = True
            Animation.cancel_all(self, "_grow")
            self._grow = 1.0
        if self.dragging:
            self._set_from_touch(touch)
            return True
        return False

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        self._pending = None
        if self.dragging:
            self.dragging = False
            self._grow = 0.0
            self._draw()
            if self.on_commit:
                self.on_commit(self.value)
        return True

    def set_value(self, v):
        if not self.dragging:
            self.value = max(self.lo, min(self.hi, float(v)))


def number_dialog(title, value, lo, hi, step, on_value, default=None, fmt=None):
    """Small sheet with a numeric keyboard for exact values."""
    sheet = Sheet(title)
    sheet.height = dp(236)
    fmt = fmt or (lambda v: ("%d" % round(v)) if (step or 0) >= 1 else ("%.3f" % v))
    row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
    ti = TextInput(text=("%d" % round(value)) if (step or 0) >= 1 else ("%.3f" % value).rstrip("0").rstrip("."),
                   multiline=False, input_filter="float", size_hint_y=None, height=dp(48),
                   background_normal="", background_active="", background_color=T.surface3,
                   foreground_color=T.on_surface, cursor_color=T.primary, font_size=sp(18),
                   selection_color=T.a("primary", 0.35), padding=(dp(14), dp(12)))
    row.add_widget(ti)
    sheet.box.add_widget(lbl("Range %s .. %s" % (fmt(lo), fmt(hi)), 12, T.on_var, size_hint_y=None, height=dp(20)))
    sheet.box.add_widget(row)
    err = lbl("", 12, T.error, size_hint_y=None, height=dp(18))
    sheet.box.add_widget(err)
    btns = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))

    def apply(*_):
        try:
            v = float(ti.text.replace(",", "."))
        except ValueError:
            err.text = "Enter a number"
            return
        v = max(lo, min(hi, v))
        if step:
            v = round((v - lo) / step) * step + lo
        sheet.dismiss()
        on_value(v)
    if default is not None:
        btns.add_widget(Button3("Reset", lambda: (sheet.dismiss(), on_value(float(default))), kind="text", icon="reset"))
    btns.add_widget(Button3("Cancel", sheet.dismiss, kind="outlined"))
    btns.add_widget(Button3("Set", apply, kind="filled"))
    sheet.box.add_widget(btns)
    ti.bind(on_text_validate=apply)
    sheet.open()
    Clock.schedule_once(lambda _dt: (setattr(ti, "focus", True), ti.select_all()), 0.15)
    return sheet


class SliderRow(BoxLayout):
    """Label + value chip + thin slider.

    Tap the value chip to type an exact number; double tap the slider (or use
    Reset in the dialog) to restore the default."""

    def __init__(self, title, lo, hi, value, on_change, step=0.0, unit="", fmt=None, bipolar=False,
                 default=None, icon=None, **kw):
        super().__init__(orientation="vertical", size_hint_y=None, height=dp(48), spacing=0, **kw)
        self.unit = unit
        self.lo, self.hi, self.step = float(lo), float(hi), float(step or 0)
        self.title = title
        self.fmt = fmt or (lambda v: ((("%+d" if bipolar else "%d") % round(v)) if (step or 0) >= 1 else
                                      (("%+.3f" if bipolar else "%.3f") % v)) + unit)
        self.default = value if default is None else default
        self._cb = on_change
        head = BoxLayout(size_hint_y=None, height=dp(24), padding=(dp(10), 0))
        if icon:
            head.add_widget(Icon(name=icon, tint=T.on_var, size_hint_x=None, width=dp(20)))
            head.add_widget(Widget(size_hint_x=None, width=dp(6)))
        head.add_widget(lbl(title, 13, T.on_surface))
        self.chip = Tap(on_tap=self.edit, bg=T.surface3, radius=dp(8), size_hint=(None, None),
                        width=dp(78), height=dp(22), padding=(dp(6), 0))
        self.val = lbl(self.fmt(value), 12, T.primary, bold=True, halign="center")
        self.chip.add_widget(self.val)
        head.add_widget(self.chip)
        self.add_widget(head)
        self.slider = Slider3(lo, hi, value, step, on_change=self._changed, fmt=self.fmt, bipolar=bipolar,
                              default=self.default)
        self.add_widget(self.slider)

    def _changed(self, v):
        self.val.text = self.fmt(v)
        self._cb(v)

    def edit(self):
        """Tap the value chip: type an exact value."""
        def setv(v):
            self.slider.value = v
            self._changed(v)
        number_dialog(self.title, self.slider.value, self.lo, self.hi, self.step, setv, self.default, self.fmt)

    def reset(self):
        self.slider.value = self.default
        self._changed(self.default)

    def set(self, v):
        self.slider.set_value(v)
        self.val.text = self.fmt(self.slider.value)


# ---------------------------------------------------------------- color picker
def _hex8(rgba):
    return "#" + "".join("%02X" % int(round(max(0.0, min(1.0, c)) * 255)) for c in rgba)


def _parse_hex(value, fallback=(1, 1, 1, 1)):
    h = str(value or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) == 6:
        h += "FF"
    try:
        if len(h) == 8:
            return [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4, 6)]
    except ValueError:
        pass
    return None if fallback is None else list(fallback)


RECENT_COLORS = []          # most recent first (#RRGGBBAA), max 20; the app persists it
COLOR_HOOKS = {"eyedropper": None, "recent_changed": None}
COLOR_MODE = {"mode": "HSV"}


def remember_color(hex8):
    hex8 = hex8.upper()
    if hex8 in RECENT_COLORS:
        RECENT_COLORS.remove(hex8)
    RECENT_COLORS.insert(0, hex8)
    del RECENT_COLORS[20:]
    cb = COLOR_HOOKS.get("recent_changed")
    if cb:
        cb(list(RECENT_COLORS))


class _HexSwatch(ButtonBehavior, Widget):
    """Compact in-app hexagonal color chip with an isolated tap target."""
    def __init__(self, rgba, on_pick, **kwargs):
        super().__init__(**kwargs)
        self.rgba, self.on_pick = list(rgba), on_pick
        with self.canvas:
            self.fill = Color(*self.rgba)
            self.triangles = [Triangle(points=[]) for _ in range(6)]
            self.edge_color = Color(*T.outline)
            self.edge = Line(points=[], close=True, width=dp(1))
        self.bind(pos=self._draw_hex, size=self._draw_hex)
        self._draw_hex()

    def _draw_hex(self, *_):
        inset = dp(2)
        w, h = max(1, self.width - inset * 2), max(1, self.height - inset * 2)
        x, y = self.x + inset, self.y + inset
        pts = [x + w * .25, y, x + w * .75, y, x + w, y + h * .5,
               x + w * .75, y + h, x + w * .25, y + h, x, y + h * .5]
        cx, cy = x + w * .5, y + h * .5
        vertices = [(x + w * .25, y), (x + w * .75, y), (x + w, y + h * .5),
                    (x + w * .75, y + h), (x + w * .25, y + h), (x, y + h * .5)]
        for i, tri in enumerate(self.triangles):
            a, b = vertices[i], vertices[(i + 1) % 6]
            tri.points = [cx, cy, a[0], a[1], b[0], b[1]]
        self.edge.points = pts

    def on_release(self):
        self.on_pick(list(self.rgba))


def _swatch_line(colors, pick, height=dp(30)):
    line = BoxLayout(size_hint_y=None, height=height, spacing=dp(4))
    for c in colors:
        line.add_widget(_HexSwatch(_parse_hex(c), pick))
    return line



class HexColorGrid(Widget):
    """Exact-pick hexagonal HSV palette. Every cell returns its own RGB hex value."""
    def __init__(self, selected="#32CD32FF", on_pick=None, **kwargs):
        super().__init__(**kwargs)
        self.selected = str(selected).upper()
        self.on_pick = on_pick or (lambda value: None)
        self._cells = []
        self.bind(pos=self.redraw, size=self.redraw)
        Clock.schedule_once(self.redraw, 0)

    @staticmethod
    def _hex(h, value):
        import colorsys
        rgb = colorsys.hsv_to_rgb(float(h), 1.0, float(value))
        return "#" + "".join("%02X" % int(round(max(0.0, min(1.0, c)) * 255)) for c in rgb) + "FF"

    def redraw(self, *_):
        self.canvas.clear()
        self._cells = []
        if self.width < dp(40) or self.height < dp(40):
            return
        cols, rows = 12, 7
        radius = min(self.width / 18.5, self.height / (7.5 * math.sqrt(3.0)))
        if radius <= 1:
            return
        levels = (1.0, 0.86, 0.72, 0.50, 0.36, 0.22, 0.12)
        with self.canvas:
            for row in range(rows):
                for col in range(cols):
                    color_hex = self._hex(col / float(cols), levels[row])
                    rgb = _parse_hex(color_hex)
                    cx = self.x + radius + col * 1.5 * radius
                    cy = self.top - math.sqrt(3.0) * radius * (0.5 + row + 0.5 * (col % 2))
                    pts = []
                    for k in range(6):
                        a = math.radians(60 * k)
                        pts.extend((cx + radius * math.cos(a), cy + radius * math.sin(a)))
                    Color(*rgb)
                    for k in range(6):
                        j = (k + 1) % 6
                        Triangle(points=(cx, cy, pts[2*k], pts[2*k+1], pts[2*j], pts[2*j+1]))
                    if color_hex == self.selected:
                        Color(0.05, 0.12, 0.10, 1)
                        Line(points=pts, close=True, width=dp(2.2))
                    else:
                        Color(1, 1, 1, 0.55)
                        Line(points=pts, close=True, width=dp(0.7))
                    self._cells.append((cx, cy, radius, color_hex))

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        for cx, cy, radius, color_hex in reversed(self._cells):
            dx, dy = touch.x - cx, touch.y - cy
            if abs(dx) <= radius and abs(dy) <= math.sqrt(3.0) * radius / 2.0 and abs(dx) + abs(dy) / math.sqrt(3.0) <= radius + dp(1):
                self.selected = color_hex
                self.redraw()
                self.on_pick(color_hex)
                return True
        return True


def color_dialog(title, value, on_value, default=None, swatches=None, _start=None):
    """Color picker: HSV / RGB / HSL slider modes, hex input, alpha, palette swatches,
    20 recent colors and an eyedropper (picks from the live preview). Every change calls
    ``on_value`` (#RRGGBBAA) so the preview is live."""
    import colorsys
    from kivy.core.window import Window
    start = _parse_hex(_start if _start is not None else value)
    state = {"rgba": list(_parse_hex(value)), "busy": False}
    sheet = Sheet(title)
    recent = RECENT_COLORS[:20]
    extra = dp(40) if recent else 0
    sheet.height = min(Window.height * 0.9, dp(470) + extra)
    scroll = ScrollView(do_scroll_x=False, bar_width=0)
    body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(7), padding=(dp(2), dp(2)))
    body.bind(minimum_height=body.setter("height"))
    scroll.add_widget(body)
    top = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
    sw = Box(bg=list(state["rgba"]), radius=dp(14), line=T.outline, size_hint_x=None, width=dp(56))
    ti = TextInput(text=_hex8(state["rgba"]), multiline=False, size_hint_y=None, height=dp(46),
                   background_normal="", background_active="", background_color=T.surface3,
                   foreground_color=T.on_surface, cursor_color=T.primary, font_size=sp(16),
                   padding=(dp(14), dp(12)))
    top.add_widget(sw)
    top.add_widget(ti)
    if COLOR_HOOKS.get("eyedropper"):
        def dropper():
            sheet.dismiss()
            def picked(hex8):
                if hex8:
                    on_value(hex8)
                color_dialog(title, hex8 or _hex8(state["rgba"]), on_value, default, swatches, _start=_hex8(start))
            COLOR_HOOKS["eyedropper"](picked)
        top.add_widget(IconBtn("eyedropper", dropper, size=dp(44)))
    body.add_widget(top)
    body.add_widget(lbl("HEXAGON COLOR GRID", 12, T.primary, bold=True, size_hint_y=None, height=dp(22)))
    grid = HexColorGrid(selected=_hex8(state["rgba"]).upper(), size_hint=(1, None), height=dp(254))
    def push(from_text=False):
        rgba = state["rgba"]
        sw.bg = rgba
        grid.selected = _hex8(rgba).upper()
        grid.redraw()
        if not from_text:
            state["busy"] = True
            ti.text = _hex8(rgba)
            state["busy"] = False
        on_value(_hex8(rgba))
    def pick_hex(hex8):
        rgba = _parse_hex(hex8, None)
        if rgba is None:
            return
        state["rgba"] = list(rgba)
        push()
    grid.on_pick = pick_hex
    body.add_widget(grid)
    def typed(_w, text):
        if state["busy"] or len(text.strip().lstrip("#")) not in (6, 8):
            return
        rgba = _parse_hex(text, None)
        if rgba is None:
            return
        state["rgba"] = list(rgba)
        push(from_text=True)
    ti.bind(text=typed)
    if swatches:
        body.add_widget(lbl("PALETTE", 12, T.on_var, size_hint_y=None, height=dp(20)))
        body.add_widget(_swatch_line(list(swatches)[:12], lambda rgba: pick_hex(_hex8(rgba)), dp(30)))
    if recent:
        body.add_widget(lbl("RECENT", 12, T.on_var, size_hint_y=None, height=dp(20)))
        for i in range(0, len(recent), 10):
            chunk = recent[i:i + 10]
            line = _swatch_line(chunk, lambda rgba: pick_hex(_hex8(rgba)), dp(28))
            for _ in range(10 - len(chunk)):
                line.add_widget(Widget())
            body.add_widget(line)
    sheet.box.add_widget(scroll)
    btns = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
    if default is not None:
        btns.add_widget(Button3("Reset", lambda: (sheet.dismiss(), on_value(_hex8(_parse_hex(default)))),
                                kind="text", icon="reset"))
    btns.add_widget(Button3("Cancel", lambda: (sheet.dismiss(), on_value(_hex8(start))), kind="outlined"))

    def done():
        sheet.dismiss()
        remember_color(_hex8(state["rgba"]))
    btns.add_widget(Button3("Done", done, kind="filled"))
    sheet.box.add_widget(btns)
    sheet.open()
    return sheet


class ColorField(Tap):
    """Swatch + hex value; tap opens the color picker."""

    def __init__(self, value, on_change, default=None, swatches=None, title="Color", **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(40))
        super().__init__(on_tap=self._open, bg=[0, 0, 0, 0], line=T.outline, radius=dp(12),
                         padding=(dp(8), dp(6)), spacing=dp(10), **kw)
        self.value, self.on_change, self.default = value, on_change, default
        self.swatches, self.title = swatches, title
        self.sw = Box(bg=_parse_hex(value), radius=dp(8), line=T.outline, size_hint_x=None, width=dp(44))
        self.add_widget(self.sw)
        self.label = lbl(str(value), 13)
        self.add_widget(self.label)
        self.add_widget(Icon(name="down", tint=T.on_var, size_hint_x=None, width=dp(18)))

    def set(self, v):
        self.value = v
        self.sw.bg = _parse_hex(v)
        self.label.text = str(v)

    def _changed(self, v):
        self.set(v)
        self.on_change(v)

    def _open(self):
        sw = self.swatches() if callable(self.swatches) else self.swatches
        color_dialog(self.title, self.value, self._changed, self.default, sw)


# ---------------------------------------------------------------- switch
class Switch3(TouchGuard, ButtonBehavior, Widget):
    active = BooleanProperty(False)

    def __init__(self, active=False, on_change=None, **kw):
        kw.setdefault("size_hint", (None, None))
        super().__init__(size=(dp(52), dp(32)), **kw)
        self.on_change = on_change
        with self.canvas:
            self._tc = Color()
            self._tr = RoundedRectangle()
            self._oc = Color()
            self._ol = Line(width=dp(1.5))
            self._hc = Color()
            self._h = Rectangle()
        self._k = 1.0 if active else 0.0
        self.active = active
        self.bind(pos=self._draw, size=self._draw, active=self._anim)
        self._draw()

    def _anim(self, *_):
        Animation.cancel_all(self)
        Animation(_k=1.0 if self.active else 0.0, d=0.16, t="out_quad").start(self)

    def on__k(self, *_):
        if hasattr(self, "_h"):
            self._draw()

    _k = NumericProperty(0.0)

    def _draw(self, *_):
        k = self._k
        on_bg, off_bg = T.primary, T.surface3
        self._tc.rgba = [off_bg[i] * (1 - k) + on_bg[i] * k for i in range(4)]
        self._tr.pos, self._tr.size, self._tr.radius = self.pos, self.size, [0]
        self._oc.rgba = T.a("outline", 1 - k)
        self._ol.rectangle = (self.x, self.y, self.width, self.height)
        d = dp(16) + dp(8) * k
        cx = self.x + self.height / 2 + k * (self.width - self.height)
        hc_on, hc_off = T.on_primary, T.outline
        self._hc.rgba = [hc_off[i] * (1 - k) + hc_on[i] * k for i in range(4)]
        self._h.pos, self._h.size = (cx - d / 2, (self.y + self.height / 2.0) - d / 2), (d, d)

    def on_release(self):
        self.active = not self.active
        if self.on_change:
            self.on_change(self.active)


def switch_row(title, active, on_change, subtitle="", icon=None):
    row = BoxLayout(size_hint_y=None, height=dp(52) if not subtitle else dp(60), padding=(dp(10), 0), spacing=dp(10))
    if icon:
        row.add_widget(Icon(name=icon, tint=T.on_var, size_hint_x=None, width=dp(20)))
    col = BoxLayout(orientation="vertical", padding=(0, dp(8)))
    col.add_widget(lbl(title, 14))
    if subtitle:
        col.add_widget(lbl(subtitle, 11, T.on_var))
    row.add_widget(col)
    sw = Switch3(active, on_change)
    holder = BoxLayout(size_hint_x=None, width=dp(56), padding=(0, (row.height - dp(32)) / 2))
    holder.add_widget(sw)
    row.add_widget(holder)
    # Keep the switch as the only toggle hit target; parent-row bubbling
    # caused double toggles and taps leaking to nearby controls.
    row.switch = sw
    return row


# ---------------------------------------------------------------- text field / select
def text_field(text, on_change, hint="", multiline=False, height=None):
    ti = TextInput(text=str(text), hint_text=hint, multiline=multiline, size_hint_y=None,
                   height=height or (dp(40) if not multiline else dp(120)),
                   background_normal="", background_active="", background_color=T.surface3,
                   foreground_color=T.on_surface, hint_text_color=T.on_var, cursor_color=T.primary,
                   selection_color=T.a("primary", 0.35), font_size=sp(14),
                   padding=(dp(14), dp(13) if not multiline else dp(10)))
    ti.bind(text=lambda _, v: on_change(v))
    return ti


class Sheet(ModalView):
    """Bottom sheet."""

    def __init__(self, title, **kw):
        super().__init__(size_hint=(1, None), pos_hint={"x": 0, "y": 0}, background="",
                         background_color=T.a("scrim", 0.0), overlay_color=T.a("scrim", 0.5), **kw)
        self.box = Box(orientation="vertical", bg=T.surface2, radius=UI_RADIUS, padding=(dp(16), dp(10), dp(16), dp(16)), spacing=dp(6))
        grip = BoxLayout(size_hint_y=None, height=dp(14))
        g = Widget()
        with g.canvas:
            Color(*T.a("on_var", 0.5))
            gr = Rectangle()
        g.bind(pos=lambda w, *_: setattr(gr, "pos", (w.x + w.width / 2 - dp(16), w.y + w.height / 2 - dp(2))))
        gr.size = (dp(32), dp(4))
        grip.add_widget(g)
        self.box.add_widget(grip)
        self.box.add_widget(lbl(title, 18, bold=True, size_hint_y=None, height=dp(34)))
        self.add_widget(self.box)


def select_sheet(title, options, value, on_pick):
    sheet = Sheet(title)
    from kivy.core.window import Window
    rows = len(options)
    sheet.height = min(Window.height * 0.7, dp(80) + rows * dp(48) + dp(20))
    scroll = ScrollView()
    col = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(2))
    col.bind(minimum_height=col.setter("height"))
    for opt in options:
        sel = str(opt) == str(value)
        r = Tap(size_hint_y=None, height=dp(46), radius=dp(23), padding=(dp(16), 0), spacing=dp(10),
                bg=T.secondary_container if sel else [0, 0, 0, 0])
        r.add_widget(lbl(str(opt), 14, T.on_secondary_container if sel else T.on_surface, bold=sel))
        if sel:
            r.add_widget(Icon(name="check", tint=T.on_secondary_container, size_hint_x=None, width=dp(20)))

        def pick(*_, o=opt):
            sheet.dismiss()
            on_pick(o)
        r.bind(on_release=pick)
        col.add_widget(r)
    scroll.add_widget(col)
    sheet.box.add_widget(scroll)
    sheet.open()
    return sheet


class SelectField(Tap):
    """Outlined select field that opens a bottom sheet with every option."""

    def __init__(self, title, options, value, on_change, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(40))
        super().__init__(bg=[0, 0, 0, 0], line=T.outline, radius=dp(12), padding=(dp(14), 0), spacing=dp(6), **kw)
        self.title, self.options, self.on_change = title, list(options), on_change
        self.value = value
        self.label = lbl(str(value), 14)
        self.add_widget(self.label)
        self.add_widget(Icon(name="down", tint=T.on_var, size_hint_x=None, width=dp(18)))
        self.bind(on_release=lambda *_: select_sheet(self.title, self.options, self.value, self._pick))

    def _pick(self, v):
        self.value = v
        self.label.text = str(v)
        self.on_change(v)


# ---------------------------------------------------------------- navigation
class NavBar(Box):
    def __init__(self, items, on_select, current, **kw):
        super().__init__(size_hint_y=None, height=dp(56), bg=T.surface, radius=dp(3), padding=(dp(2), dp(3), dp(2), dp(3)), **kw)
        self.on_select = on_select
        self.items = {}
        for key, icon, title in items:
            it = _NavItem(key, icon, title, self._tap)
            self.items[key] = it
            self.add_widget(it)
        self.select(current, notify=False)

    def _tap(self, key):
        self.select(key)

    def select(self, key, notify=True):
        for k, it in self.items.items():
            it.set_active(k == key)
        if notify:
            self.on_select(key)


class _NavItem(TouchGuard, ButtonBehavior, BoxLayout):
    _k = NumericProperty(0.0)

    def __init__(self, key, icon, title, cb, **kw):
        super().__init__(orientation="vertical", spacing=dp(1), **kw)
        self.key, self.cb = key, cb
        self._indicator_color = Color(*T.primary)
        self._indicator = Rectangle()
        with self.canvas.before:
            self._indicator_color
            self._indicator
        self.pill = Widget(size_hint_y=None, height=dp(24))
        with self.pill.canvas.before:
            self._pc = Color(*T.secondary_container)
            self._pr = Rectangle()
        self.icon = Icon(name=icon)
        self.pill.add_widget(self.icon)
        self.pill.bind(pos=self._u, size=self._u)
        self.bind(_k=self._u)
        self.title = lbl(title, 9, T.on_var, halign="center", size_hint_y=None, height=dp(14))
        self.add_widget(self.pill)
        self.add_widget(self.title)
        self.bind(on_release=lambda *_: self.cb(self.key))

    def _u(self, *_):
        w = dp(56) * (0.5 + 0.5 * self._k)
        self._pr.pos = ((self.pill.x + self.pill.width / 2.0) - w / 2, self.pill.y)
        self._pr.size = (w, self.pill.height)
        self._pc.a = 0
        self._indicator.pos = (self.x, self.top - dp(2))
        self._indicator.size = (self.width, dp(2) if self._k > 0.02 else 0)
        self._indicator_color.a = self._k
        s = dp(18)
        self.icon.pos = ((self.pill.x + self.pill.width / 2.0) - s / 2, (self.pill.y + self.pill.height / 2.0) - s / 2)
        self.icon.size = (s, s)

    def set_active(self, on):
        Animation.cancel_all(self)
        Animation(_k=1.0 if on else 0.0, d=0.2, t="out_quad").start(self)
        self.icon.tint = T.on_secondary_container if on else T.on_var
        self.title.color = T.on_surface if on else T.on_var
        self.title.bold = on


class Segmented(Box):
    def __init__(self, options, value, on_change, **kw):
        super().__init__(size_hint_y=None, height=dp(42), line=T.outline, radius=dp(3), spacing=0, **kw)
        self.on_change = on_change
        self.btns = {}
        for i, opt in enumerate(options):
            b = Tap(radius=dp(2), padding=(dp(6), 0), spacing=dp(4))
            b.icon = Icon(name="check", size_hint_x=None, width=dp(16))
            b.label = lbl(opt, 13, bold=True, halign="center")
            b.add_widget(b.icon)
            b.add_widget(b.label)
            b.bind(on_release=lambda w, o=opt: self.select(o))
            self.btns[opt] = b
            self.add_widget(b)
        self.select(value, notify=False)

    def select(self, opt, notify=True):
        for k, b in self.btns.items():
            on = k == opt
            b.bg = T.secondary_container if on else [0, 0, 0, 0]
            b.label.color = T.on_secondary_container if on else T.on_surface
            b.icon.tint = T.on_secondary_container
            b.icon.width = dp(16) if on else 0
            b.icon.opacity = 1 if on else 0
        if notify:
            self.on_change(opt)


class Snackbar:
    _current = None

    @classmethod
    def show(cls, text, parent, action=None, on_action=None):
        """``action`` adds a text button (e.g. "Undo"); the bar then stays 5 s."""
        if cls._current is not None and cls._current.parent:
            cls._current.parent.remove_widget(cls._current)
        bar = Box(bg=T.on_surface, radius=dp(3), padding=(dp(16), 0, dp(6), 0), size_hint=(None, None),
                  height=dp(48), width=parent.width - dp(32), pos=(parent.x + dp(16), parent.y + dp(84)))
        bar.add_widget(lbl(text, 13, T.surface, shorten=True))
        if action and on_action:
            btn = Tap(radius=dp(18), size_hint=(None, None), size=(dp(76), dp(36)), padding=(dp(8), 0))
            btn.add_widget(lbl(action, 14, T.inverse_primary if hasattr(T, "inverse_primary") else T.primary_container,
                               bold=True, halign="center"))
            wrap = BoxLayout(size_hint_x=None, width=dp(80), padding=(0, dp(6)))
            wrap.add_widget(btn)

            def act(*_):
                if bar.parent:
                    bar.parent.remove_widget(bar)
                on_action()
            btn.bind(on_release=act)
            bar.add_widget(wrap)
        bar.opacity = 0
        parent.add_widget(bar)
        cls._current = bar
        anim = Animation(opacity=1, d=0.15) + Animation(d=5.0 if action else 2.4) + Animation(opacity=0, d=0.3)
        anim.bind(on_complete=lambda *_: bar.parent and bar.parent.remove_widget(bar))
        anim.start(bar)
