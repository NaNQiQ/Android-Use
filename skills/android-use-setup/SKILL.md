---
name: android-use-setup
description: 安装、诊断或恢复 Windows 上的 Android Use 插件、ADB、USB 调试和 UIAutomator2 服务；用于首次连接或 Android Use 连接故障。
---

# Android Use Setup

Prefer an existing installed plugin and working phone service. `android_doctor` reports devices, selected serial, runtime and streaming dependencies; `android_ready` checks the actual device. Do not reinstall the phone service just because a new chat started.

If tools are absent, inspect `scripts/install-android.ps1` at the repository root and run it from PowerShell. From this skill's directory the source or installed plugin root is two levels up. The installer stages the Android plugin, registers its local marketplace, installs the plugin through the Codex CLI, and points the standard `android_use` MCP entry at the installed cache. It uses one server namespace so plugin and standard registrations do not expose duplicate tools. It stores the Python runtime and selected device only in `%LOCALAPPDATA%/AndroidUse/config.json`, outside the distributable package.

If already installed but this chat lacks tools, tell the user to reconnect tools or open a new chat. Installed skill invocation uses `$android-use` / `$android-use-setup`; the plugin is named **Android Use** in the plugin picker. Verify actual discovery rather than promising the current chat hot-reloaded.

USB recovery:

- `device`: reuse the serial and service. With multiple devices, ask which device the task concerns and pass its serial to the installer or setup tool.
- `unauthorized`: ask the user to unlock the phone and accept its USB debugging trust prompt.
- no device/offline: check cable, USB debugging and Windows device drivers; do not enable ADB over Wi-Fi as an unsolicited workaround.
- `unlock_required`: ask the user to unlock and keep the screen awake. Do not bypass the lock screen.
- an automation service error: call `android_setup(action="reconnect")` once, then `android_ready`; setup reconnects without replaying any previous action.

Scrcpy is optional for control but preferred for preview. The plugin uses the installed scrcpy server with its exact matching client version, decodes the local stream and serves cached frames to the sidebar. `android_screen` reports the actual source (`scrcpy` or `screenshot`) and faults. Missing scrcpy/PyAV can use snapshot fallback while installing dependencies. Consult `README.android.md` at the plugin root for installation paths and limitations.

Only declare the phone ready when `android_ready.ready=true`. Only declare the screen working after receiving a valid frame. User actions such as USB authorization and device unlock cannot be substituted by a successful host install.
