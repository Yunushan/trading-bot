# Build a Windows .exe using PyInstaller.
# The explicit metadata/submodule flags keep package version detection consistent
# between local runs and bundled onefile releases.
param(
  [string]$Python = "python",
  [string]$Icon = "",
  [string]$Name = "Trading-Bot-Python",
  [switch]$Console,
  [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
$pythonRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repoRoot = (Resolve-Path (Join-Path $pythonRoot "..\\..")).Path
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

  & $Python @pyInstallerArgs

  Write-Host "Done. EXE at: dist\$Name.exe"
}
finally {
  Pop-Location
}
