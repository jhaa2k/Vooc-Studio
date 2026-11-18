# Vooc Studio technology stack

## Baseline that is already in the repository

| Area | Current implementation | Responsibility |
|---|---|---|
| App and editor logic | Python 3 | Project state, property schema, presets, templates, export planning |
| Mobile UI | Kivy (Python) | Existing Android screens, editor controls and property inspector |
| Android platform bridge | Java + PyJNIus | Media session, audio integration, MediaCodec/MediaMuxer export |
| Audio analysis | NumPy / Python | FFT bands, waveform, RMS and beat analysis |
| Visual rendering | OpenGL ES + GLSL | Layers, compositing, blend modes and shader effects |
| Build | Buildozer + python-for-android | Android APK packaging and GitHub Actions |

The baseline deliberately keeps the proven Vooc code and feature model intact.

## Target hybrid architecture

1. **Python remains the product/core layer.** Keep the existing project schema, presets, templates, editor state and high-level rendering orchestration.
2. **Kotlin is the preferred destination for new Android-native services.** Use it for lifecycle-aware media/session integration, permissions, document access and future native UI surfaces. Migrate existing Java bridges incrementally; do not rewrite working bridges just to change syntax.
3. **C++ with the Android NDK is reserved for profiled hot paths.** Candidate areas are audio ring buffers, FFT/beat analysis and frame conversion. JNI boundaries must use bounded buffers and avoid per-frame object allocation.
4. **GLSL remains the GPU language.** Keep visual effects and compositing on the GPU; do not move shader work into Python or C++.
5. **MediaCodec / MediaMuxer remains the Android export foundation.** Export runs off the preview clock with deterministic frame timestamps and explicit cancellation/cleanup.

## Why this combination

A Python-only Android app would make native media lifecycle, notification controls and sustained real-time DSP harder to maintain. A full rewrite in Kotlin/C++ would risk losing Vooc's large property schema and editor functionality. The hybrid path preserves the existing product while moving only performance- or platform-critical components to native code.

## Build constraint

The current APK pipeline is Buildozer/python-for-android. Kotlin/NDK modules must not be added as decorative, uncompiled source files. Before introducing them, the build pipeline must be updated and tested so the Kotlin compiler and NDK artifacts are actually packaged in the APK.
