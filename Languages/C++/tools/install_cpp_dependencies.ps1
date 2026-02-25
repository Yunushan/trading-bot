param(
  [string]$QtVersion = "6.10.2",
  [string]$QtArch = "win64_msvc2022_64",
  [string]$QtOutputDir = "C:/Qt",
  [string]$Triplet = "x64-windows",
  [ValidateSet("pinned", "latest")]
  [string]$VcpkgMode = "pinned",
  [string]$VcpkgRef = "26283ac5e8a068561a718ce18b169bfad84c7dab"
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

Write-Host "Installing aqtinstall..."
& $pythonExe -m pip install --upgrade aqtinstall

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
if ($VcpkgMode -eq "latest") {
  $remoteHead = git symbolic-ref refs/remotes/origin/HEAD
  $branch = ($remoteHead -replace "^refs/remotes/origin/", "").Trim()
  if ([string]::IsNullOrWhiteSpace($branch)) {
    $branch = "master"
  }
  git checkout $branch
  git pull --ff-only origin $branch
  Write-Host "Using latest vcpkg from branch: $branch"
} else {
  if ([string]::IsNullOrWhiteSpace($VcpkgRef)) {
    throw "VcpkgRef cannot be empty when VcpkgMode is 'pinned'."
  }
  git checkout $VcpkgRef
  Write-Host "Using pinned vcpkg ref: $VcpkgRef"
}
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
