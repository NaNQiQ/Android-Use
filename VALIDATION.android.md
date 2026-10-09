# Android adapter validation

## Version 0.2.3

The Windows + Android adapter was validated with automated backend and widget checks, a TypeScript check/build, and an installed-cache smoke test against a USB-connected Android device.

The smoke test covered readiness, accessibility-tree and screenshot observations, Unicode text entry and readback, selector actions, failed postcondition reporting, scrcpy frame delivery, preview pause/resume, batch stop behavior, reconnect, and returning to the launcher. It did not change system settings or submit a purchase or message.

The implementation reports dispatch separately from verification. Coordinate actions require a recent observation; selectors check enabled and visible bounds; generic postconditions can check selector state, foreground package/activity, or native Toast text. Accessibility coverage and sequential tree/screenshot consistency remain heuristic. Custom-drawn transient banners may be missed. The preview is decoded scrcpy video transported through MCP polling, not a native 60 fps video player.

Other device vendors, protected screens, live rotation, long-text limits in individual apps, physical cable reconnection, and simultaneous live clients still need broader validation. The recorded smoke test is not a cross-device benchmark or a claim of production readiness.
