param([string]$Serial, [string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$stateRoot = if ($env:ANDROID_USE_STATE_DIR) { $env:ANDROID_USE_STATE_DIR } else { Join-Path $env:LOCALAPPDATA 'AndroidUse' }
New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
$configPath = Join-Path $stateRoot 'config.json'
$previousConfig = if (Test-Path $configPath) { Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json } else { $null }
if (!$Serial -and $previousConfig) { $Serial = $previousConfig.serial }
$venvRoot = Join-Path $stateRoot 'venv'
$pythonPath = Join-Path $venvRoot 'Scripts/python.exe'
if (!(Test-Path $pythonPath)) {
    & $Python -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed' }
}
& $pythonPath -m pip install -r (Join-Path $projectRoot 'requirements-android.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
$adbCommand = Get-Command adb -ErrorAction Stop
$scrcpyCommand = Get-Command scrcpy -ErrorAction SilentlyContinue
$settings = @{ python = $pythonPath; adb = $adbCommand.Source }
if ($Serial) { $settings.serial = $Serial }
if ($scrcpyCommand) {
    $settings.scrcpy = $scrcpyCommand.Source
    $serverFile = Join-Path (Split-Path $scrcpyCommand.Source -Parent) 'scrcpy-server'
    if (Test-Path $serverFile) { $settings.scrcpy_server = $serverFile }
    $versionText = (& $scrcpyCommand.Source --version 2>&1 | Out-String)
    if ($versionText -match 'scrcpy\s+(\d+\.\d+(?:\.\d+)?)') { $settings.scrcpy_version = $Matches[1] }
}
$settings | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding utf8
$packageScript = Join-Path $PSScriptRoot 'package_android.py'
if (Test-Path $packageScript) {
    & $pythonPath $packageScript --stage-only
    if ($LASTEXITCODE -ne 0) { throw 'Plugin packaging failed' }
    $marketplaceRoot = Join-Path $projectRoot 'dist/marketplace-android'
} else {
    $marketplaceRoot = Join-Path $stateRoot 'marketplace'
    $sourcePath = Join-Path $marketplaceRoot 'android-use'
    $resolvedSource = [IO.Path]::GetFullPath($sourcePath)
    $resolvedRoot = [IO.Path]::GetFullPath($marketplaceRoot)
    if (![string]::Equals([IO.Path]::GetDirectoryName($resolvedSource), $resolvedRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid package directory' }
    $resolvedProject = [IO.Path]::GetFullPath($projectRoot)
    if (![string]::Equals($resolvedProject, $resolvedSource, [StringComparison]::OrdinalIgnoreCase)) {
        if ($resolvedProject.StartsWith($resolvedSource + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Cannot replace a package containing the installer source' }
        if (Test-Path $sourcePath) { Remove-Item -LiteralPath $resolvedSource -Recurse -Force }
        New-Item -ItemType Directory -Path $sourcePath -Force | Out-Null
        Get-ChildItem -LiteralPath $projectRoot -Force | Copy-Item -Destination $sourcePath -Recurse -Force
    }
    $catalogDirectory = Join-Path $marketplaceRoot '.agents/plugins'
    New-Item -ItemType Directory -Path $catalogDirectory -Force | Out-Null
    @{ name = 'android-use-local'; interface = @{ displayName = 'Android Use Local' }; plugins = @(
        @{ name = 'android-use'; source = @{ source = 'local'; path = './android-use' }; policy = @{ installation = 'AVAILABLE'; authentication = 'ON_INSTALL' }; category = 'Productivity' }
    ) } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $catalogDirectory 'marketplace.json') -Encoding utf8
}
codex plugin marketplace add $marketplaceRoot --json
if ($LASTEXITCODE -ne 0) { throw 'Marketplace registration failed' }
$installationText = (codex plugin add android-use@android-use-local --json | Out-String)
if ($LASTEXITCODE -ne 0) { throw 'Plugin installation failed' }
$installation = $installationText | ConvertFrom-Json
if ($installation.pluginId -ne 'android-use@android-use-local') { throw 'Unexpected plugin installation result' }
$installedRoot = $installation.installedPath
$serverPath = Join-Path $installedRoot 'server/android_use.py'
if (!(Test-Path $serverPath)) { throw 'Installed Android MCP server is missing' }
# Standard config wins over bundled MCP using the same namespace, so tools appear once.
codex mcp add android_use -- $pythonPath (Join-Path $installedRoot 'scripts/launch_android.py')
if ($LASTEXITCODE -ne 0) { throw 'MCP registration failed' }
$installationText | Set-Content -LiteralPath (Join-Path $stateRoot 'installation.json') -Encoding utf8
Write-Host 'Installed Android Use plugin and two skills. Reconnect Codex or open a new chat.'
