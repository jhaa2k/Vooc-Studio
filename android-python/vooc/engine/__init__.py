# Register the Avee-style WAVEFORM extras (ring / trails / fill) as soon as the
# engine package is used. Skipped silently where Kivy is not installed (CI unit
# tests of the pure-numpy helpers).
try:
    from . import vector_layers as _vector_layers  # noqa: F401
    from . import wave_plus as _wave_plus  # noqa: F401
except ImportError:  # pragma: no cover
    pass
