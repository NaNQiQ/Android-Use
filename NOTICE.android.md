# Android Use attribution

Android Use derives its plugin workflow, observation/action design and screen widget from [zhongerxin/iPhone-use](https://github.com/zhongerxin/iPhone-use), Copyright (c) 2026 ZHONG XIN, MIT License. The full upstream MIT license is retained in `LICENSE`; its original third-party notices are retained in `THIRD_PARTY_NOTICES.md`.

Android runtime dependencies are installed separately:

- [openatx/uiautomator2](https://github.com/openatx/uiautomator2) and [adbutils](https://github.com/openatx/adbutils): Android automation and USB transport.
- [Genymobile/scrcpy](https://github.com/Genymobile/scrcpy): screen encoder/server. The plugin uses the user's installed binary and matching server, not a bundled copy.
- [PyAV](https://github.com/PyAV-Org/PyAV): local H.264 decoding, with its wheel's FFmpeg dependencies.
- [jsonschema](https://github.com/python-jsonschema/jsonschema): tool argument validation.
- [Pillow](https://github.com/python-pillow/Pillow): screenshot and preview image encoding.
- [MCP Apps SDK](https://github.com/modelcontextprotocol/ext-apps): upstream UI host transport.

Dependency license files remain with their respective installed packages. The Android distribution includes no Apple signing data, personal device configuration, runtime screenshots or logs, Python environment or scrcpy binary. The maintainer-provided README demonstration image is included as a documentation asset.
