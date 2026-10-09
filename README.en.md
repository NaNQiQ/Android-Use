# Android Use

A Codex plugin for Windows and USB-connected Android phones, maintained by [NaNQiQ](https://github.com/NaNQiQ).

Let Codex open apps, inspect pages, tap, swipe, enter Unicode text and verify action results. The native MCP Apps sidebar displays the phone screen in the current chat. Control uses ADB and UIAutomator2; preview uses scrcpy with screenshot fallback. No Mac or Xcode is required.

[中文](README.md) · **English**

## Install

Install Python 3.12+, Codex CLI, ADB on PATH and preferably scrcpy. Connect an unlocked Android phone by USB, enable USB debugging and accept the device trust prompt.

```powershell
git clone https://github.com/NaNQiQ/Android-Use.git
cd Android-Use
powershell -ExecutionPolicy Bypass -File scripts/install-android.ps1
```

The installer creates a separate Python environment, stages the plugin, registers a local marketplace and configures the `android_use` MCP launcher. Personal paths and device selection are stored outside the repository in `%LOCALAPPDATA%/AndroidUse/config.json`. Use `-Serial YOUR_DEVICE_SERIAL` for multiple devices.

Reconnect Codex or restart it after installation. Select **Android Use** from the plugin picker and ask it to check the connected phone and open its screen.

## Development

```powershell
& "$env:LOCALAPPDATA/AndroidUse/venv/Scripts/python.exe" tests/test_android.py
npm ci --prefix ui
npm run build --prefix ui
npm test --prefix ui
python scripts/package_android.py
```

The root contains the Android plugin manifests, `skills/`, `server/`, editable sidebar source in `ui/`, and automated checks in `tests/`. The distribution is generated under `dist/`.

## Limitations

Accessibility coverage is heuristic; screenshots and trees are sampled sequentially. Dispatch is reported separately from verified postconditions. Custom transient banners may be missed. Preview delivers the latest decoded video frame through MCP polling; 60 fps is a capture ceiling, not a guaranteed sidebar rate or zero-latency claim. Device vendors, protected screens and rotation need broader testing. See [validation notes](VALIDATION.android.md).

## License and attribution

MIT. Portions of the sidebar and interaction design derive from iPhone Use. Original copyright and third-party notices are retained in [LICENSE](LICENSE), [NOTICE.android.md](NOTICE.android.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
