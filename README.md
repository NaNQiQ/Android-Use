# Android Use

**Windows + Android 的 Codex 插件。**

让 Codex 通过 USB 操作 Android 手机，并在当前聊天右侧显示实时手机画面。支持打开 App、读取页面、点击、滑动、中文输入和动作结果核验。

**中文** · [English](README.en.md)

![Android Use 在 Codex 中执行手机任务，并在右侧显示真实 Android 手机画面](assets/android-use-demo.png)

*实际使用截图：左侧为任务与执行结果，右侧为通过 USB 连接的 Android 手机实时预览。*

控制后端采用 ADB + openatx/uiautomator2，屏幕预览采用 scrcpy 视频流与原生 MCP Apps 侧栏。无需 Mac 或 Xcode。

**使用前，请用 USB 数据线连接你自己的 Android 手机，开启 USB 调试，并在手机上允许这台电脑调试。** 第一次连接时，UIAutomator2 可能向手机部署自动化服务；安装电脑插件并不代表手机已经就绪。

## 用一段提示词让 AI 安装

将下面这段话复制到能执行本机 PowerShell 命令的 Codex：

```text
请帮我在这台 Windows 电脑安装和配置 Android Use：
https://github.com/NaNQiQ/Android-Use

先读取仓库 README、scripts/install-android.ps1 和
skills/android-use-setup/SKILL.md，再检查 Windows 本机 PowerShell、
Codex CLI、Python、ADB、scrcpy，以及 USB 连接的 Android 手机。
确认 Codex CLI 支持 plugin marketplace、plugin add 和 mcp add。
优先复用已安装的依赖和已有 Android Use 配置，不照搬作者的本机路径、
手机序列号或安装缓存，也不要为了重新安装删除我的运行数据。

把仓库克隆到合适的本机目录，在仓库根目录运行：
powershell -ExecutionPolicy Bypass -File scripts/install-android.ps1
需要指定 Python 或多设备时，使用脚本的 -Python / -Serial 参数。
缺少依赖时说明具体缺项，从官方来源帮助安装，并确认命令能被找到。
scrcpy 客户端与 scrcpy-server 必须来自同一版本。

安装器会建立独立 Python 环境、打包插件、注册本地 marketplace、
安装插件及技能，并配置 android_use MCP。不要重复注册第二套工具。
如果当前聊天还没加载新工具，明确告诉我重连、重启或新开聊天后继续，
不要把安装成功说成手机操作已经可用。

工具加载后，按 android-use-setup 技能检查和连接手机。
只有 android_ready 返回 ready=true，才确认手机就绪；
打开 android_screen 并取得有效画面后，才确认右侧预览正常。
说明实际使用的是 scrcpy 视频还是截图回退，不把回退称为实时视频。

开启 USB 调试、接受调试授权、安装驱动、解锁手机或账号登录需要我
操作时，给出明确步骤，等我完成再继续。不要绕过锁屏或改成无线 ADB。
验收时核对连接和画面，不发送消息、下单或修改我的系统设置。
```

安装后的工具需要由本机客户端加载。其他能执行本机命令的 AI 可以协助安装，但本文的插件入口和右侧手机画面以 Codex 为目标；普通网页聊天不能直接访问 USB 手机。

## 运行环境与依赖

| 环境 / 依赖 | 用途与要求 |
| --- | --- |
| Windows 本机 + PowerShell | 当前安装目标；从 Windows 运行安装脚本，不使用 WSL 路径或 Linux 命令替代 |
| Codex 桌面端 + Codex CLI | 桌面端显示 MCP Apps 手机侧栏；CLI 注册插件与 MCP。需支持 `codex plugin`、`codex plugin marketplace`、`codex mcp add`；已验证 CLI 0.149.1 |
| Python 3.12+ | 运行 Android MCP 服务和安装器；当前检查使用 Python 3.13。需可通过 `python` 调用，或传 `-Python` 指定解释器 |
| ADB / Android SDK Platform-Tools | 发现和控制 USB 手机；`adb` 必须在 PATH 中，无需安装完整 Android Studio |
| Android 真机 + USB 数据线 | 开启开发者选项和 USB 调试、接受调试授权，操作时解锁并保持亮屏；部分厂商需要额外 USB 驱动或允许调试输入 |
| scrcpy（推荐） | 提供视频流；已验证 scrcpy 4.0。需能找到客户端及同版本 `scrcpy-server`，其他版本需实际验收；缺少时使用截图预览回退 |
| Git | 用于克隆与更新仓库；也可以下载源码 ZIP 后解压 |
| Node.js / npm（开发时） | 重建与测试侧栏，当前 CI 使用 Node.js 24；直接安装已有源码中的侧栏 HTML 不需要重建 UI |

Python 依赖版本固定在 [requirements-android.txt](requirements-android.txt)，由安装器装入独立环境，包括 UIAutomator2、JSON Schema 和 PyAV；不需要 root、Mac、Xcode 或独立 Appium Server。

官方入口：[Codex 插件文档](https://developers.openai.com/plugins/build/plugins)、[Python for Windows](https://www.python.org/downloads/windows/)、[Android Platform-Tools](https://developer.android.com/tools/releases/platform-tools)、[scrcpy Windows 安装说明](https://github.com/Genymobile/scrcpy/blob/master/doc/windows.md)。Codex CLI 若尚未安装，可按[官方 CLI 安装说明](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex#quickstart-using-goals)安装。使用 npm 安装 CLI 时才需要 Node.js / npm。

### 先准备自己的手机

1. 用支持数据传输的 USB 线连接手机，在手机设置中开启开发者选项与 USB 调试。
2. 解锁手机，接受“允许 USB 调试”提示；需要时安装厂商官方 USB 驱动。
3. 在 Windows PowerShell 运行 `adb devices -l`。目标手机应显示 `device`；`unauthorized` 表示尚未授权，`offline` 表示连接未就绪。
4. 多设备时记下你自己的目标序列号，安装时用 `-Serial` 指定。不要使用演示图中的设备信息。

### 手动安装插件

```powershell
git clone https://github.com/NaNQiQ/Android-Use.git
cd Android-Use
powershell -ExecutionPolicy Bypass -File scripts/install-android.ps1
```

多设备时加 `-Serial YOUR_DEVICE_SERIAL`。安装器会打包 Android 插件、注册本地 marketplace、安装插件和两个 skill，并将 `android_use` MCP 指向安装缓存；与插件同名的标准 MCP 注册优先，避免重复工具。

指定 Python 与手机的例子（替换为你的实际路径和序列号）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-android.ps1 -Python 'C:\Path\To\Python\python.exe' -Serial YOUR_DEVICE_SERIAL
```

安装器会联网安装 Python 依赖。若从源码 ZIP 安装，在解压后的项目根目录执行同一个脚本即可；日常安装使用仓库中已有的侧栏 HTML，无需先执行 npm 构建。

### 在 Codex 中连接和验收

重连或新开聊天后，在 `@` 插件选择入口搜索 **Android Use**。技能的实际发现名称为 `$android-use:android-use` 和 `$android-use:android-use-setup`。如果插件列表仍未刷新，重启 Codex。可以输入：

> 使用 Android Use 检查已连接的手机并打开手机屏幕。

成功标准是 `android_ready.ready=true`，并且右侧预览取得有效手机画面；仅脚本退出成功不代表当前聊天已经加载工具。已有健康连接会复用，不需要每个新任务都重装手机服务。

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

真机验收脚本 `tests/test_android_live.py --run` 会操作设置搜索草稿并最后返回主屏幕，需先解锁手机。验证记录见 `VALIDATION.android.md`。本机配置、日志和运行产物不进入 Git；本文演示图由项目维护者提供。

## 更新与常见问题

```powershell
git pull --ff-only
powershell -ExecutionPolicy Bypass -File scripts/install-android.ps1
```

更新后重连或重启 Codex，以加载新工具、技能和侧栏资源。安装器复用已有 Python 环境与手机选择；不要删除个人运行目录来处理普通升级。

| 现象 | 检查方法 |
| --- | --- |
| 找不到 `codex` / 没有 `plugin` 子命令 | 检查 CLI 安装、PATH 和版本；先确认 `codex plugin --help` 可用 |
| `adb devices -l` 无设备 | 检查数据线、USB 调试、USB 驱动，解锁手机后重新连接 |
| 设备 `unauthorized` / `offline` | 接受手机授权；检查连接并使用 setup 显式重连，不重放先前操作 |
| 安装成功但聊天没有工具 | 重连、新开聊天或完全重启 Codex，再启用 Android Use |
| 只有截图、画面刷新慢 | 检查 `android_doctor` / `android_screen` 报告的来源和故障；确认 scrcpy、同版服务端及 PyAV 可用 |
| 多台手机选错设备 | 使用你自己的 `-Serial` 重新安装，或按 setup 技能选择目标设备 |

视频源上限与侧栏实际帧率是不同指标；不要把“安装成功”“Live”或缓存帧传输耗时解释为零延迟。

## 许可与来源

项目采用 MIT 许可。部分侧栏代码与交互设计源自 iPhone Use；原作者版权和第三方许可保留在 [LICENSE](LICENSE)、[NOTICE.android.md](NOTICE.android.md) 和 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
