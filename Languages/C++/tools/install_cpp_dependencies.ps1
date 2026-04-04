param(
  [string]$AqtInstallVersion = "3.3.0",
  [string]$QtVersion = "6.10.3",
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
$qtInstallCommand = @($pythonExe, "-m", "aqt", "install-qt", "windows", "desktop", $QtVersion, $QtArch, "--outputdir", $QtOutputDir, "-m") + $qtModules
Invoke-Checked -Label "Installing Qt $QtVersion ($QtArch) with modules: $($qtModules -join ', ')" -Command $qtInstallCommand

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
Write-Host "Qt root: $QtOutputDir/$QtVersion"
Write-Host "vcpkg root: $localVcpkg"
