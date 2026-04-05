param(
  [string]$AqtInstallVersion = "3.3.0",
  [string]$QtVersion = "6.11.0",
  [string]$QtArch = "win64_msvc2022_64",
  [string]$QtOutputDir = "C:/Qt",
  [string]$Triplet = "x64-windows",
  [string]$VcpkgRef = "d0ba406f0e5352517386709dba49fbabf99a9e3c"
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Label,
    [Parameter(Mandatory = $true)]
    [string[]]$Command
  )

  Write-Host "$Label..."
  if ($Command.Count -le 0) {
    throw "$Label failed because no command was provided."
  }
  if ($Command.Count -eq 1) {
    & $Command[0]
  } else {
    & $Command[0] $Command[1..($Command.Count - 1)]
  }
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with exit code $LASTEXITCODE."
  }
}

function Test-VersionAtLeast {
  param(
    [string]$Left,
    [string]$Right
  )

  try {
    return ([version]$Left) -ge ([version]$Right)
  } catch {
    return $false
  }
}

function Test-QtOfficialAuthAvailable {
  $qtAccountIni = Join-Path $env:APPDATA "Qt\qtaccount.ini"
  if (Test-Path $qtAccountIni) {
    return $true
  }
  return -not [string]::IsNullOrWhiteSpace($env:QT_INSTALLER_JWT_TOKEN)
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$cppRoot = Resolve-Path (Join-Path $scriptDir "..")
$repoRoot = Resolve-Path (Join-Path $cppRoot "..\..")
$localVcpkg = Join-Path $repoRoot ".vcpkg"

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
  $pythonExe = $venvPython
} else {
  $pythonExe = "python"
}

Write-Host "Using Python: $pythonExe"
Write-Host "Repository root: $repoRoot"

$aqtInstallSpec = "aqtinstall==$AqtInstallVersion"
Invoke-Checked -Label "Installing $aqtInstallSpec" -Command @($pythonExe, "-m", "pip", "install", "--upgrade", $aqtInstallSpec)

$qtModules = @("qtwebengine", "qtwebsockets", "qtwebchannel", "qtpositioning")
$fallbackQtVersion = "6.10.3"
$resolvedQtVersion = $null

function Install-QtViaMirrorAqt {
  param([string]$Version)
  $qtInstallCommand = @($pythonExe, "-m", "aqt", "install-qt", "windows", "desktop", $Version, $QtArch, "--outputdir", $QtOutputDir, "-m") + $qtModules
  Invoke-Checked -Label "Installing Qt $Version ($QtArch) with mirror-based aqt and modules: $($qtModules -join ', ')" -Command $qtInstallCommand
}

function Install-QtViaOfficialAqt {
  param([string]$Version)
  $qtInstallCommand = @(
    $pythonExe,
    "-m",
    "aqt",
    "install-qt-official",
    "desktop",
    $QtArch,
    $Version,
    "--outputdir",
    $QtOutputDir,
    "--modules"
  ) + $qtModules
  Invoke-Checked -Label "Installing Qt $Version ($QtArch) with the official Qt installer and modules: $($qtModules -join ', ')" -Command $qtInstallCommand
}

$qtInstallErrors = New-Object System.Collections.Generic.List[string]
$qtOfficialAuthAvailable = Test-QtOfficialAuthAvailable

if (Test-VersionAtLeast -Left $QtVersion -Right "6.11.0") {
  if ($qtOfficialAuthAvailable) {
    try {
      Install-QtViaOfficialAqt -Version $QtVersion
      $resolvedQtVersion = $QtVersion
    } catch {
      $qtInstallErrors.Add("Official Qt installer failed for $QtVersion ($QtArch): $($_.Exception.Message)")
      Write-Warning "Official Qt installer failed for Qt $QtVersion. Falling back to mirror-based aqt and, if needed, Qt $fallbackQtVersion."
    }
  } else {
    Write-Warning "Qt $QtVersion on Windows needs Qt account credentials for the official installer path. Falling back to mirror-based aqt and, if needed, Qt $fallbackQtVersion."
  }
}

if (-not $resolvedQtVersion) {
  try {
    Install-QtViaMirrorAqt -Version $QtVersion
    $resolvedQtVersion = $QtVersion
  } catch {
    $qtInstallErrors.Add("Mirror-based aqt install failed for $QtVersion ($QtArch): $($_.Exception.Message)")
    Write-Warning "Mirror-based aqt install failed for Qt $QtVersion."
  }
}

if (-not $resolvedQtVersion -and $QtVersion -ne $fallbackQtVersion) {
  try {
    Install-QtViaMirrorAqt -Version $fallbackQtVersion
    $resolvedQtVersion = $fallbackQtVersion
    Write-Warning "Installed fallback Qt $fallbackQtVersion because Qt $QtVersion was not provisionable through the current Windows setup path."
  } catch {
    $qtInstallErrors.Add("Mirror-based aqt install failed for fallback Qt $fallbackQtVersion ($QtArch): $($_.Exception.Message)")
  }
}

if (-not $resolvedQtVersion) {
  throw ("Qt installation failed. " + ($qtInstallErrors -join " "))
}

if (!(Test-Path (Join-Path $localVcpkg "vcpkg.exe"))) {
  if (!(Test-Path $localVcpkg)) {
    Write-Host "Cloning vcpkg into $localVcpkg"
    Invoke-Checked -Label "Cloning vcpkg into $localVcpkg" -Command @("git", "clone", "https://github.com/microsoft/vcpkg.git", $localVcpkg)
  }
}

Push-Location $localVcpkg
Invoke-Checked -Label "Fetching vcpkg tags" -Command @("git", "fetch", "--tags", "--force")
if ([string]::IsNullOrWhiteSpace($VcpkgRef)) {
  throw "VcpkgRef cannot be empty."
}
Invoke-Checked -Label "Checking out pinned vcpkg ref $VcpkgRef" -Command @("git", "checkout", $VcpkgRef)
Write-Host "Using pinned vcpkg ref: $VcpkgRef"
Pop-Location

Invoke-Checked -Label "Bootstrapping vcpkg" -Command @(Join-Path $localVcpkg "bootstrap-vcpkg.bat", "-disableMetrics")

$vcpkgExe = Join-Path $localVcpkg "vcpkg.exe"
$ports = @(
  "eigen3:$Triplet",
  "xtensor:$Triplet",
  "talib:$Triplet",
  "cpr:$Triplet",
  "curl[tool,ssl]:$Triplet",
  "vulkan-headers:$Triplet"
)

$vcpkgInstallCommand = @($vcpkgExe, "install") + $ports
Invoke-Checked -Label "Installing vcpkg ports: $($ports -join ', ')" -Command $vcpkgInstallCommand

Write-Host "Done."
Write-Host "Qt root: $QtOutputDir/$resolvedQtVersion"
Write-Host "vcpkg root: $localVcpkg"
