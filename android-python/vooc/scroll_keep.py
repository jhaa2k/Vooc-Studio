"""Keep the page scroll offset (in pixels) stable on the accordion pages.

main.py restores the offset with fixed timers (0.12 s / 0.28 s) after a page
rebuild and after each category toggle. On a slow phone the content has not
reached its final height by then, so the page ended up scrolled to the top.

Here the pixel distance from the top is remembered on every user scroll and
re-applied whenever the content or the viewport changes size, so category
toggles and rebuilds (tapping a layer, visibility, ...) always keep the page
exactly where it was. Only real scrolling (finger down or a fling still running)
updates the remembered offset; any other move of scroll_y (layout pass, timer)
is undone.
"""

ACCORDION_PAGES = ("visual", "sound", "layers", "settings")


def _track(sv):
    if getattr(sv, "_vooc_tracked", False) or not sv.children:
        return
    from kivy.clock import Clock

    vp = sv.children[0]
    st = sv._vooc_scroll = {"px": 0.0, "busy": False, "skip": False, "touching": False}
    sv._vooc_tracked = True

    def top_px():
        return max(0.0, (1.0 - sv.scroll_y) * max(0.0, vp.height - sv.height))

    def apply(*_):
        span = vp.height - sv.height
        if span > 0:
            st["busy"] = True
            sv.scroll_y = max(0.0, min(1.0, 1.0 - st["px"] / span))
            st["busy"] = False

    def unskip(_dt):
        st["skip"] = False

    def settle(secs=0.25):
        st["skip"] = True
        Clock.unschedule(unskip)
        Clock.schedule_once(unskip, secs)

    def user_scrolling():
        # finger down on the page, or the fling it started is still running
        effect = getattr(sv, "effect_y", None)
        return st["touching"] or (effect is not None and abs(getattr(effect, "velocity", 0.0)) > 0.5)

    def on_scroll(*_):
        if st["busy"]:
            return
        if user_scrolling() and not st["skip"]:
            st["px"] = top_px()
        else:
            apply()  # moved by a layout pass or a timer: put it back

    def on_touch_down(widget, touch):
        if widget.collide_point(*touch.pos):
            st["touching"] = True
        return False

    def on_touch_up(widget, touch):
        st["touching"] = False
        return False

    def on_size(*_):
        settle()
        apply()

    st["settle"] = settle
    sv.bind(scroll_y=on_scroll, on_touch_down=on_touch_down, on_touch_up=on_touch_up)
    vp.bind(height=on_size)
    sv.bind(height=on_size)


def _patched_show(original):
    def show(self, page):
        same = page == getattr(self, "page", None) and page in ACCORDION_PAGES
        px = 0.0
        if same:
            body = getattr(self, "body", None)
            old = body.children[0] if body is not None and body.children else None
            st = getattr(old, "_vooc_scroll", None)
            px = st["px"] if st else 0.0
        original(self, page)
        if page not in ACCORDION_PAGES:
            return
        body = getattr(self, "body", None)
        sv = body.children[0] if body is not None and body.children else None
        if sv is not None and hasattr(sv, "scroll_y"):
            _track(sv)
            st = getattr(sv, "_vooc_scroll", None)
            if same and st:
                st["px"] = px
                st["settle"](0.8)
    return show


def install():
    try:
        from kivy.app import App
        from kivy.clock import Clock
    except Exception:  # plain unit tests without Kivy
        return

    def tick(_dt):
        app = App.get_running_app()
        root = getattr(app, "root", None)
        if root is None:
            return
        cls = type(root)  # `show` lives on the root widget, not the App
        if not getattr(cls, "_vooc_scroll_keep", False) and hasattr(cls, "show"):
            cls.show = _patched_show(cls.show)
            cls._vooc_scroll_keep = True
        body = getattr(root, "body", None)
        if body is not None and body.children and hasattr(body.children[0], "scroll_y"):
            _track(body.children[0])
        return False if getattr(cls, "_vooc_scroll_keep", False) else None

    Clock.schedule_interval(tick, 0.2)


install()
