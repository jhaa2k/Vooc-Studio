# Vooc Studio

A redesigned next-generation Android audio visualizer and music video studio, built from the existing Vooc feature set.

## Project direction

Vooc Studio preserves the original visualizer, audio, layer, effect, preset, project and export capabilities while introducing a cleaner mobile-first Material-inspired interface.

### Technology strategy

- **Python + Kivy** — existing application logic, visualizer property model, presets, project persistence and UI foundation.
- **Java / Android APIs** — Android media session, notification controls, media import, platform integration and video export bridges.
- **GLSL / OpenGL ES** — GPU visualizer layers, compositing and real-time effects.
- **Kotlin** — planned native Android service and UI integration where it improves lifecycle, media and platform reliability.
- **C++ / JNI** — reserved for measured audio/DSP bottlenecks; not introduced without profiling evidence.

The app will continue to build through GitHub Actions so development can be managed from a phone.

## Feature preservation

The migration baseline includes the existing Vooc modules, property schema, audio providers, visualizer layers, effects, presets, templates, project persistence, media controls and export pipeline. Existing functionality must not be removed during the redesign.

## Development

Work happens on the `studio-dev` branch. The `main` branch is kept as the initial repository landing point.

See:
- `docs/TECH_STACK.md`
- `docs/REDESIGN_ROADMAP.md`
- `android-python/README.md`

## Build

The Android debug APK is built by GitHub Actions. Run the **Build Vooc Studio Android APK** workflow manually or push changes under `android-python/`.

> The initial migration is a preserved baseline, not a claim that the redesigned UI or device export has already been completed or verified.
