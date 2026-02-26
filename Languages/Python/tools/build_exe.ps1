# Build a Windows .exe using PyInstaller.
# The explicit metadata/submodule flags keep package version detection consistent
# between local runs and bundled onefile releases.
param(
  [string]$Python = "python",
  [string]$Icon = "",
  [string]$Name = "Trading-Bot-Python",
  [switch]$Console,
  [switch]$SkipDependencyInstall,
  [string]$ReleaseTag = ""
)

$ErrorActionPreference = "Stop"
$pythonRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repoRoot = (Resolve-Path (Join-Path $pythonRoot "..\\..")).Path
$releaseInfoPath = ""
Push-Location $pythonRoot

try {
  if (-not $SkipDependencyInstall) {
    if (Test-Path "requirements.txt") {
      & $Python -m pip install --upgrade pip | Out-Null
      & $Python -m pip install --upgrade pyinstaller | Out-Null
      & $Python -m pip install -r requirements.txt | Out-Null
    }
    else {
      throw "requirements.txt not found in $pythonRoot"
    }
  }

  $effectiveReleaseTag = "$ReleaseTag".Trim()
  if ([string]::IsNullOrWhiteSpace($effectiveReleaseTag)) {
    $effectiveReleaseTag = "$env:TB_RELEASE_TAG".Trim()
  }
  if (-not [string]::IsNullOrWhiteSpace($effectiveReleaseTag)) {
    if ($effectiveReleaseTag -match "(\d+(?:[._-]\d+){1,3}(?:[-_.]?(?:a|b|rc|post|dev)\d+)?)") {
      $effectiveReleaseTag = $Matches[1].Replace("_", ".")
    }
  }
  if (-not [string]::IsNullOrWhiteSpace($effectiveReleaseTag)) {
    $releaseInfoPath = Join-Path $pythonRoot "build\\release-info.json"
    New-Item -ItemType Directory -Force -Path (Split-Path $releaseInfoPath -Parent) | Out-Null
    $releaseInfoPayload = @{
      release_tag = $effectiveReleaseTag
      built_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    } | ConvertTo-Json -Depth 4
    Set-Content -Path $releaseInfoPath -Value $releaseInfoPayload -Encoding utf8
  }

  $pyInstallerArgs = @(
    "-m", "PyInstaller",
    "main.py",
    "--name", $Name,
    "--onefile",
    "--clean",
    "--noconfirm",
    "--specpath", "build",
    "--collect-submodules", "binance_sdk_derivatives_trading_usds_futures",
    "--collect-submodules", "binance_sdk_derivatives_trading_coin_futures",
    "--collect-submodules", "binance_sdk_spot",
    "--copy-metadata", "python-binance",
    "--copy-metadata", "binance-connector",
    "--copy-metadata", "ccxt",
    "--copy-metadata", "binance-sdk-derivatives-trading-usds-futures",
    "--copy-metadata", "binance-sdk-derivatives-trading-coin-futures",
    "--copy-metadata", "binance-sdk-spot",
    "--hidden-import", "binance.client",
    "--hidden-import", "binance.spot"
  )

  if ($Console) {
    $pyInstallerArgs += "--console"
  }
  else {
    $pyInstallerArgs += "--windowed"
  }

  $iconPath = ""
  if ($Icon -ne "") {
    $iconPath = $Icon
  }
  else {
    $defaultIcon = Join-Path $repoRoot "assets\\crypto_forex_logo.ico"
    if (Test-Path $defaultIcon) {
      $iconPath = $defaultIcon
    }
  }

  if ($iconPath -eq "") {
    throw "Icon not found. Refusing to build EXE without icon resource."
  }
  $pyInstallerArgs += @("--icon", $iconPath)

  $assetsDir = Join-Path $repoRoot "assets"
  if (Test-Path $assetsDir) {
    # Bundle repo assets so onefile runtime can still load icons and logos.
    $pyInstallerArgs += @("--add-data", "$assetsDir;assets")
  }
  if ($releaseInfoPath -ne "" -and (Test-Path $releaseInfoPath)) {
    # Embed release metadata so the running EXE can show its release tag in the UI.
    $pyInstallerArgs += @("--add-data", "$releaseInfoPath;app")
  }

  & $Python @pyInstallerArgs

  Write-Host "Done. EXE at: dist\$Name.exe"
}
finally {
  if ($releaseInfoPath -ne "" -and (Test-Path $releaseInfoPath)) {
    Remove-Item -Force $releaseInfoPath -ErrorAction SilentlyContinue
  }
  Pop-Location
}
