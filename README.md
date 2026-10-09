# Android Use

**Windows + Android 的 Codex 插件，由 [NaNQiQ](https://github.com/NaNQiQ) 维护。**

让 Codex 通过 USB 操作 Android 手机，并在当前聊天右侧显示实时手机画面。支持打开 App、读取页面、点击、滑动、中文输入和动作结果核验。

**中文** · [English](README.en.md)

控制后端采用 ADB + openatx/uiautomator2，屏幕预览采用 scrcpy 视频流与原生 MCP Apps 侧栏。无需 Mac 或 Xcode。

## 安装

需要 Python 3.12+、Codex CLI、PATH 中的 ADB，以及已授权 USB 调试的 Android 手机。安装依赖使用独立 Python 环境；第一次连接会向手机部署 UIAutomator2 服务。电脑安装 scrcpy 后可启用视频预览，缺少 scrcpy 时使用截图回退。

```powershell
git clone https://github.com/NaNQiQ/Android-Use.git
cd Android-Use
powershell -ExecutionPolicy Bypass -File scripts/install-android.ps1
```

多设备时加 `-Serial YOUR_DEVICE_SERIAL`。安装器会打包 Android 插件、注册本地 marketplace、安装插件和两个 skill，并将 `android_use` MCP 指向安装缓存；与插件同名的标准 MCP 注册优先，避免重复工具。

重连或新开聊天后，在 `@` 插件选择入口搜索 **Android Use**。技能的实际发现名称为 `$android-use:android-use` 和 `$android-use:android-use-setup`。如果插件列表仍未刷新，重启 Codex。可以输入：

> 使用 Android Use 检查已连接的手机并打开手机屏幕。

用户专属配置位于 `%LOCALAPPDATA%/AndroidUse/config.json`，记录 Python、ADB、scrcpy 路径与选定序列号；不进入插件分发包。`ANDROID_USE_STATE_DIR` 可指定替代目录。

## 功能

- 设备诊断、显式重连、连接就绪检查、App 包名发现。
- 精简控件树及读取质量提示；auto 模式在正文标签不足时同次返回新截图，选择器定位与坐标点击。
- 滑动、主屏幕/返回/最近任务、App 启动、超时等待。
- Unicode 中文输入、长文本替换和精确回读，不自动提交。
- 批量步骤、结果期望检查、失败停止；单次滚动查找和有界列表采集。
- 按设备跨进程锁；坐标操作必须提供观察编号，检查视口、前台 Activity、时间与可见应用树。选择器操作检查启用状态及可见区域。
- 通用后置条件（控件出现/消失、前台包名/Activity、原生 Toast 文本），输出已验证/未确认/失败；失败保留现场，批量遇到需要视觉检查的页面停止。
- scrcpy 持续 H.264 视频接收和解码，缓存最新 JPEG 帧供侧边栏取用。视频源上限 60fps，侧边栏请求间隔 33ms，实际刷新率取决于 Codex 主机。视频在执行工具时继续接收，不再为每个预览请求截屏。
- 后台锁屏/在线检查、预览暂停与恢复、点击/拖动提示，屏幕流不落盘。

模型定位截图与用户观看的预览分开。模型截图保留手机原分辨率；预览最长边为 1400px。侧边栏工具栏的截图按钮刷新画面，不复制到 Windows 剪贴板。

操作按页面能力返回新控件树及必要截图，移除统一固定 0.4 秒等待，显式条件采用有界等待。`executed` 仅表示动作发出；`verification` 只证明声明的检查，不推断业务成功。原生 Toast 使用动作前清空的服务端缓存捕获，仅作证据；自绘短暂提示仍可能漏读。树质量判断是启发式，无法证明正文完整；树与截图是顺序采样，不保证原子一致。可见应用树校验无法发现完全不暴露节点的同 Activity 视觉变化，这类坐标仍需及时观察。核对预期页面和文字；不确定错误后先观察，不盲目重放。密码控件的文字被隐藏，密码和认证由用户完成；认证前暂停预览。

## 使用范围

当前已有 Windows + Android USB 真机验证。其他厂商、受保护画面和旋转仍需逐机验收；scrcpy 预览使用文档化 raw_stream 模式，并从本机 scrcpy 获取匹配的服务端版本。设备断连后通过 setup 重连，不重放上次操作。列表仅报告已观察范围，重复相同文本可能合并。

项目根目录是 Android Use 插件源码：`plugin.json` 为插件清单，`skills/` 为操作和安装技能，`server/` 为 Android MCP 后端，`ui/` 为侧栏源码。分发包生成到 `dist/android-use-0.2.3.zip`。

## 开发与检查

```powershell
& "$env:LOCALAPPDATA/AndroidUse/venv/Scripts/python.exe" tests/test_android.py
npm ci --prefix ui
npm run build --prefix ui
npm test --prefix ui
```

真机验收脚本 `tests/test_android_live.py --run` 会操作设置搜索草稿并最后返回主屏幕，需先解锁手机。验证记录见 `VALIDATION.android.md`。手机截图与 UI 内容不进入 Git。

## 许可与来源

项目采用 MIT 许可。部分侧栏代码与交互设计源自 iPhone Use；原作者版权和第三方许可保留在 [LICENSE](LICENSE)、[NOTICE.android.md](NOTICE.android.md) 和 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
