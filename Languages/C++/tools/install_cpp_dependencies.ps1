param(
  [string]$AqtInstallVersion = "3.3.0",
  [string]$QtVersion = "6.10.2",
  [string]$QtArch = "win64_msvc2022_64",
  [string]$QtOutputDir = "C:/Qt",
  [string]$Triplet = "x64-windows",
  [string]$VcpkgRef = "c1f21baeaf7127c13ee141fe1bdaa49eed371c0c"
)

$ErrorActionPreference = "Stop"

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
Write-Host "Installing $aqtInstallSpec..."
& $pythonExe -m pip install --upgrade $aqtInstallSpec

$qtModules = @("qtwebengine", "qtwebsockets", "qtwebchannel", "qtpositioning")
Write-Host "Installing Qt $QtVersion ($QtArch) with modules: $($qtModules -join ', ')"
& $pythonExe -m aqt install-qt windows desktop $QtVersion $QtArch --outputdir $QtOutputDir -m @qtModules

if (!(Test-Path (Join-Path $localVcpkg "vcpkg.exe"))) {
  if (!(Test-Path $localVcpkg)) {
    Write-Host "Cloning vcpkg into $localVcpkg"
    git clone https://github.com/microsoft/vcpkg.git $localVcpkg
  }
}

Push-Location $localVcpkg
git fetch --tags --force
if ([string]::IsNullOrWhiteSpace($VcpkgRef)) {
  throw "VcpkgRef cannot be empty."
}
git checkout $VcpkgRef
Write-Host "Using pinned vcpkg ref: $VcpkgRef"
Pop-Location

Write-Host "Bootstrapping vcpkg..."
& (Join-Path $localVcpkg "bootstrap-vcpkg.bat") -disableMetrics

$vcpkgExe = Join-Path $localVcpkg "vcpkg.exe"
$ports = @(
  "eigen3:$Triplet",
  "xtensor:$Triplet",
  "talib:$Triplet",
  "cpr:$Triplet",
  "curl[tool,ssl]:$Triplet",
  "vulkan-headers:$Triplet"
)

Write-Host "Installing vcpkg ports: $($ports -join ', ')"
& $vcpkgExe install @ports

Write-Host "Done."
Write-Host "Qt root: $QtOutputDir/$QtVersion"
Write-Host "vcpkg root: $localVcpkg"
