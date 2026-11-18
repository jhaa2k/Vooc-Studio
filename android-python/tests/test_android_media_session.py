import unittest

from vooc.android_media_session import AndroidMediaSession


class AndroidMediaSessionTests(unittest.TestCase):
    def test_session_bridge_degrades_safely_without_android_runtime(self):
        session = AndroidMediaSession(
            on_play=lambda: None,
            on_pause=lambda: None,
            on_next=lambda: None,
            on_previous=lambda: None,
            on_seek=lambda _position: None,
        )
        # Desktop CI has no Android activity; the bridge must remain optional.
        session.update("Track", "Artist", "Album", "", 0, 1000, False, True)
        session.release()
        self.assertIsNone(session.controller)


if __name__ == "__main__":
    unittest.main()
