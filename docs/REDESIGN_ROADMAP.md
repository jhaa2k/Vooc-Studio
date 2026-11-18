# Vooc Studio redesign roadmap

## Non-negotiable preservation rules

- Preserve all 11 modules: COMPOSITION, TEXT, BARS, PARTICLES, IMAGE, AUDIOPROVIDER, BLUREFFECT, RGBSPLITEFFECT, MOTIONBLUREFFECT, MIRROREREFFECT and CUSTOMSHADER.
- Preserve layer ordering, visibility, blend modes, shape paths, Measure modes, per-property controls and defaults.
- Preserve music import, playback, seek, queue, metadata, album art and notification/lock-screen controls.
- Preserve presets, templates, palettes, project persistence, undo/history and export settings.
- Do not delete or silently rename existing project properties. Schema migrations must be backward compatible.

## Phase 0 — preserved baseline

- [x] Create a separate repository.
- [x] Copy the Vooc source baseline from `fix/android-ui-overlap`.
- [x] Keep the original Vooc repository untouched.
- [x] Use a dedicated `studio-dev` branch for implementation.
- [ ] Run the new repository's first CI build and resolve migration-only failures.

## Phase 1 — new mobile UI

- Redesign the app shell with a dark graphite surface and lime accent.
- Use compact square-corner controls, clear touch targets and consistent spacing.
- Keep the preview visible while switching between Library, Visual, Sound, Layers, Properties, Scene and Export.
- Make the preview edge-to-edge and prevent controls from overlapping system insets.
- Replace crowded navigation with clear editor sections without removing advanced controls.
- Keep property accordions lazy-loaded and preserve the complete property schema.

## Phase 2 — audio and playback reliability

- Verify import, metadata, album art, queue, seek, shuffle/repeat and background playback on a physical Android device.
- Verify notification shade and lock-screen transport actions.
- Profile audio callback latency and visualizer frame time before adding native C++ DSP.

## Phase 3 — export reliability

- Exercise the full export lifecycle: prepare, render, encode, mux, finalize, cancel and cleanup.
- Ensure every failure path releases MediaCodec, MediaMuxer, files and temporary audio spools.
- Test audio-only, video-only and muxed output, plus long tracks and low-storage conditions.
- Verify playable MP4 output on a real device; CI compilation alone is not proof of device export correctness.

## Phase 4 — native performance layer

- Add Kotlin services only where Android lifecycle or platform integration benefits.
- Add C++/JNI DSP only after repeatable profiling demonstrates a bottleneck.
- Keep OpenGL ES/GLSL rendering on the GPU.
- Maintain Python fallbacks for desktop tests and unsupported devices.

## Release gate

A release is not considered complete until CI passes, the APK installs over the previous Vooc Studio build, music import and playback work, notification controls work, projects reopen correctly, and an exported video plays with synchronized audio on a physical Android device.
