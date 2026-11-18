import os
import unittest


class BuildozerSpecTest(unittest.TestCase):
    def test_record_audio_declared(self):
        # RECORD_AUDIO is requested at runtime (Visualizer + Microphone source);
        # Android ignores the request unless it is declared in the manifest.
        p = os.path.join(os.path.dirname(__file__), "..", "buildozer.spec")
        with open(p, encoding="utf-8") as f:
            line = next(l for l in f if l.startswith("android.permissions"))
        self.assertIn("RECORD_AUDIO", line)


if __name__ == "__main__":
    unittest.main()
