[CmdletBinding(DefaultParameterSetName = "Bundle")]
param(
    [Parameter(Mandatory = $true, ParameterSetName = "Bundle")]
    [ValidateNotNullOrEmpty()]
    [string]$BundleDir,

    [Parameter(ParameterSetName = "Bundle")]
    [switch]$RequireCompilerRuntime,

    [Parameter(ParameterSetName = "Bundle")]
    [ValidateSet("x64", "arm64")]
    [string]$Architecture = "x64",

    [Parameter(ParameterSetName = "Bundle")]
    [string]$EvidencePath = "",

    [Parameter(ParameterSetName = "Bundle")]
    [string]$SourceRevision = "",

    [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")]
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-NativeCppBundleRequiredPaths {
    param([bool]$RequireCompilerRuntime)

    $requiredPaths = @(
        "Trading-Bot-C++.exe",
        "Qt6Core.dll",
        "Qt6Gui.dll",
        "Qt6Network.dll",
        "Qt6Widgets.dll",
        "Qt6WebEngineCore.dll",
        "Qt6WebEngineWidgets.dll",
        "QtWebEngineProcess.exe",
        "platforms\qwindows.dll",
        "resources\icudtl.dat",
        "resources\qtwebengine_resources.pak",
        "translations\qtwebengine_locales\en-US.pak"
    )
    if ($RequireCompilerRuntime) {
        $requiredPaths += @(
            "concrt140.dll",
            "msvcp140.dll",
            "vcruntime140.dll",
            "vcruntime140_1.dll"
        )
    }
    return $requiredPaths
}

function Assert-NativeCppBundleComplete {
    param(
        [string]$BundlePath,
        [bool]$RequireCompilerRuntime
    )

    $requiredPaths = Get-NativeCppBundleRequiredPaths -RequireCompilerRuntime $RequireCompilerRuntime
    $missingPaths = @(
        $requiredPaths | Where-Object {
            -not (Test-Path -LiteralPath (Join-Path $BundlePath $_) -PathType Leaf)
        }
    )
    if ($missingPaths.Count -gt 0) {
        throw "C++ bundle is incomplete. Missing: $($missingPaths -join ', ')"
    }
}

function Assert-NativeCppSmokeResult {
    param(
        [int]$ExitCode,
        [AllowEmptyString()][string]$Stdout,
        [AllowEmptyString()][string]$Stderr
    )

    if ($ExitCode -ne 0) {
        throw "Packaged C++ smoke failed with exit code $ExitCode. stderr: $($Stderr.Trim())"
    }
    if ($Stdout -notmatch "Trading Bot C\+\+ smoke ok") {
        throw "Packaged C++ smoke did not emit its success marker. stdout: $($Stdout.Trim())"
    }
    if (-not [string]::IsNullOrWhiteSpace($Stderr)) {
        throw "Packaged C++ smoke emitted diagnostics: $($Stderr.Trim())"
    }
}

function Invoke-WithIsolatedQtEnvironment {
    param(
        [scriptblock]$Action,
        [string]$SystemRootOverride = ""
    )

    $environmentNames = @("PATH", "QT_PLUGIN_PATH", "QTWEBENGINEPROCESS_PATH", "QML2_IMPORT_PATH")
    $originalEnvironment = @{}
    foreach ($name in $environmentNames) {
        $originalEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    }

    try {
        $systemRoot = $SystemRootOverride
        if ([string]::IsNullOrWhiteSpace($systemRoot)) {
            $systemRoot = [Environment]::GetEnvironmentVariable("SystemRoot", "Process")
        }
        if ([string]::IsNullOrWhiteSpace($systemRoot)) {
            throw "SystemRoot is unavailable; cannot create an isolated smoke environment."
        }
        [Environment]::SetEnvironmentVariable(
            "PATH",
            "$(Join-Path $systemRoot 'System32');$systemRoot",
            "Process"
        )
        foreach ($name in @("QT_PLUGIN_PATH", "QTWEBENGINEPROCESS_PATH", "QML2_IMPORT_PATH")) {
            [Environment]::SetEnvironmentVariable($name, $null, "Process")
        }

        return & $Action
    } finally {
        foreach ($name in $environmentNames) {
            [Environment]::SetEnvironmentVariable($name, $originalEnvironment[$name], "Process")
        }
    }
}

function Invoke-NativeCppBundleSmoke {
    param([string]$BundlePath)

    $stdoutPath = Join-Path $BundlePath ".native-cpp-smoke.stdout.txt"
    $stderrPath = Join-Path $BundlePath ".native-cpp-smoke.stderr.txt"
    try {
        $result = Invoke-WithIsolatedQtEnvironment -Action {
            $process = Start-Process `
                -FilePath (Join-Path $BundlePath "Trading-Bot-C++.exe") `
                -ArgumentList "--smoke" `
                -WorkingDirectory $BundlePath `
                -WindowStyle Hidden `
                -RedirectStandardOutput $stdoutPath `
                -RedirectStandardError $stderrPath `
                -Wait `
                -PassThru

            [pscustomobject]@{
                ExitCode = $process.ExitCode
                Stdout = if (Test-Path -LiteralPath $stdoutPath) {
                    Get-Content -LiteralPath $stdoutPath -Raw
                } else {
                    ""
                }
                Stderr = if (Test-Path -LiteralPath $stderrPath) {
                    Get-Content -LiteralPath $stderrPath -Raw
                } else {
                    ""
                }
            }
        }
        Assert-NativeCppSmokeResult `
            -ExitCode $result.ExitCode `
            -Stdout $result.Stdout `
            -Stderr $result.Stderr
        return $result
    } finally {
        foreach ($path in @($stdoutPath, $stderrPath)) {
            if (Test-Path -LiteralPath $path) {
                Remove-Item -LiteralPath $path -Force
            }
        }
    }
}

function Write-NativeCppBundleEvidence {
    param(
        [string]$BundlePath,
        [bool]$RequireCompilerRuntime,
        [ValidateSet("x64", "arm64")][string]$Architecture,
        [string]$EvidencePath,
        [string]$SourceRevision,
        [pscustomobject]$SmokeResult
    )

    $fullEvidencePath = [IO.Path]::GetFullPath($EvidencePath)
    $evidenceDirectory = Split-Path $fullEvidencePath -Parent
    if (-not (Test-Path -LiteralPath $evidenceDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $evidenceDirectory -Force | Out-Null
    }
    $executablePath = Join-Path $BundlePath "Trading-Bot-C++.exe"
    $executable = Get-Item -LiteralPath $executablePath
    $requiredPaths = @(Get-NativeCppBundleRequiredPaths -RequireCompilerRuntime $RequireCompilerRuntime)
    $qtCore = Get-Item -LiteralPath (Join-Path $BundlePath "Qt6Core.dll")
    $payload = [ordered]@{
        schema_version = 1
        kind = "native-cpp-windows-bundle-smoke"
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        source_revision = $SourceRevision
        platform = "windows"
        architecture = $Architecture
        require_compiler_runtime = $RequireCompilerRuntime
        executable = [ordered]@{
            name = $executable.Name
            size_bytes = $executable.Length
            sha256 = (Get-FileHash -LiteralPath $executablePath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        qt = [ordered]@{
            core_file_version = $qtCore.VersionInfo.FileVersion
            webengine_required = $true
        }
        bundle = [ordered]@{
            required_path_count = $requiredPaths.Count
            required_paths = $requiredPaths
            complete = $true
        }
        smoke = [ordered]@{
            argument = "--smoke"
            exit_code = $SmokeResult.ExitCode
            success_marker = "Trading Bot C++ smoke ok"
            success_marker_observed = ($SmokeResult.Stdout -match "Trading Bot C\+\+ smoke ok")
            stderr_empty = [string]::IsNullOrWhiteSpace($SmokeResult.Stderr)
            isolated_path = $true
            inherited_qt_environment_cleared = $true
            ok = $true
        }
    }
    Set-Content -LiteralPath $fullEvidencePath -Value ($payload | ConvertTo-Json -Depth 8) -Encoding utf8
    Write-Output "Native C++ Windows bundle evidence written: $fullEvidencePath"
}

function Assert-ExpectedFailure {
    param(
        [scriptblock]$Action,
        [string]$MessagePattern
    )

    $failed = $false
    try {
        & $Action
    } catch {
        $failed = $true
        if ($_.Exception.Message -notlike $MessagePattern) {
            throw "Unexpected self-test failure: $($_.Exception.Message)"
        }
    }
    if (-not $failed) {
        throw "Self-test expected failure matching '$MessagePattern'."
    }
}

function Invoke-NativeCppWindowsBundleSelfTest {
    $testRoot = Join-Path ([IO.Path]::GetTempPath()) ("trading-bot-cpp-bundle-" + [Guid]::NewGuid().ToString("N"))
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $fullTestRoot = [IO.Path]::GetFullPath($testRoot)
    if (-not $fullTestRoot.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to create self-test outside the temporary directory: $fullTestRoot"
    }

    New-Item -ItemType Directory -Path $testRoot | Out-Null
    $environmentNames = @("PATH", "QT_PLUGIN_PATH", "QTWEBENGINEPROCESS_PATH", "QML2_IMPORT_PATH")
    $originalEnvironment = @{}
    foreach ($name in $environmentNames) {
        $originalEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    }

    try {
        foreach ($relativePath in (Get-NativeCppBundleRequiredPaths -RequireCompilerRuntime $true)) {
            $path = Join-Path $testRoot $relativePath
            $parent = Split-Path $path -Parent
            if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
                New-Item -ItemType Directory -Path $parent -Force | Out-Null
            }
            Set-Content -LiteralPath $path -Value "fixture" -NoNewline
        }
        Assert-NativeCppBundleComplete -BundlePath $testRoot -RequireCompilerRuntime $true

        Remove-Item -LiteralPath (Join-Path $testRoot "Qt6Core.dll") -Force
        Assert-ExpectedFailure `
            -Action {
                Assert-NativeCppBundleComplete -BundlePath $testRoot -RequireCompilerRuntime $true
            } `
            -MessagePattern "C++ bundle is incomplete. Missing: *Qt6Core.dll*"

        Assert-NativeCppSmokeResult -ExitCode 0 -Stdout "Trading Bot C++ smoke ok" -Stderr ""
        Assert-ExpectedFailure `
            -Action { Assert-NativeCppSmokeResult -ExitCode 7 -Stdout "" -Stderr "failure" } `
            -MessagePattern "Packaged C++ smoke failed with exit code 7*"
        Assert-ExpectedFailure `
            -Action { Assert-NativeCppSmokeResult -ExitCode 0 -Stdout "wrong" -Stderr "" } `
            -MessagePattern "Packaged C++ smoke did not emit its success marker*"
        Assert-ExpectedFailure `
            -Action { Assert-NativeCppSmokeResult -ExitCode 0 -Stdout "Trading Bot C++ smoke ok" -Stderr "warning" } `
            -MessagePattern "Packaged C++ smoke emitted diagnostics*"

        [Environment]::SetEnvironmentVariable("PATH", "self-test-path", "Process")
        foreach ($name in @("QT_PLUGIN_PATH", "QTWEBENGINEPROCESS_PATH", "QML2_IMPORT_PATH")) {
            [Environment]::SetEnvironmentVariable($name, "self-test-$name", "Process")
        }
        $observed = Invoke-WithIsolatedQtEnvironment `
            -SystemRootOverride $testRoot `
            -Action {
                [pscustomobject]@{
                    Path = [Environment]::GetEnvironmentVariable("PATH", "Process")
                    QtPluginPath = [Environment]::GetEnvironmentVariable("QT_PLUGIN_PATH", "Process")
                    QtWebEngineProcessPath = [Environment]::GetEnvironmentVariable("QTWEBENGINEPROCESS_PATH", "Process")
                    QmlImportPath = [Environment]::GetEnvironmentVariable("QML2_IMPORT_PATH", "Process")
                }
            }
        $expectedPath = "$(Join-Path $testRoot 'System32');$testRoot"
        if ($observed.Path -ne $expectedPath) {
            throw "Self-test did not isolate PATH. Expected '$expectedPath', observed '$($observed.Path)'."
        }
        foreach ($value in @($observed.QtPluginPath, $observed.QtWebEngineProcessPath, $observed.QmlImportPath)) {
            if (-not [string]::IsNullOrEmpty($value)) {
                throw "Self-test did not clear inherited Qt environment variables."
            }
        }
        if ([Environment]::GetEnvironmentVariable("PATH", "Process") -ne "self-test-path") {
            throw "Self-test did not restore PATH after isolated execution."
        }
        foreach ($name in @("QT_PLUGIN_PATH", "QTWEBENGINEPROCESS_PATH", "QML2_IMPORT_PATH")) {
            if ([Environment]::GetEnvironmentVariable($name, "Process") -ne "self-test-$name") {
                throw "Self-test did not restore $name after isolated execution."
            }
        }

        Set-Content -LiteralPath (Join-Path $testRoot "Qt6Core.dll") -Value "fixture" -NoNewline
        $evidencePath = Join-Path $testRoot "evidence\native-cpp-smoke.json"
        $smokeResult = [pscustomobject]@{
            ExitCode = 0
            Stdout = "Trading Bot C++ smoke ok"
            Stderr = ""
        }
        Write-NativeCppBundleEvidence `
            -BundlePath $testRoot `
            -RequireCompilerRuntime $true `
            -Architecture "x64" `
            -EvidencePath $evidencePath `
            -SourceRevision "self-test-revision" `
            -SmokeResult $smokeResult | Out-Null
        $evidence = Get-Content -LiteralPath $evidencePath -Raw | ConvertFrom-Json
        if (
            $evidence.kind -ne "native-cpp-windows-bundle-smoke" -or
            $evidence.source_revision -ne "self-test-revision" -or
            $evidence.architecture -ne "x64" -or
            -not $evidence.bundle.complete -or
            -not $evidence.smoke.ok -or
            $evidence.executable.sha256 -notmatch "^[0-9a-f]{64}$"
        ) {
            throw "Self-test generated invalid native C++ bundle evidence."
        }
    } finally {
        foreach ($name in $environmentNames) {
            [Environment]::SetEnvironmentVariable($name, $originalEnvironment[$name], "Process")
        }
        if (Test-Path -LiteralPath $testRoot -PathType Container) {
            $resolvedCleanup = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $testRoot).Path)
            if ($resolvedCleanup -ne $fullTestRoot -or -not $resolvedCleanup.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing unsafe self-test cleanup: $resolvedCleanup"
            }
            Remove-Item -LiteralPath $resolvedCleanup -Recurse -Force
        }
    }

    Write-Output "Test-NativeCppWindowsBundle self-test passed."
}

if ($SelfTest) {
    Invoke-NativeCppWindowsBundleSelfTest
} else {
    $resolvedBundle = Resolve-Path -LiteralPath $BundleDir -ErrorAction Stop
    $bundlePath = $resolvedBundle.Path
    if (-not (Test-Path -LiteralPath $bundlePath -PathType Container)) {
        throw "C++ bundle directory does not exist: $bundlePath"
    }
    Assert-NativeCppBundleComplete `
        -BundlePath $bundlePath `
        -RequireCompilerRuntime ([bool]$RequireCompilerRuntime)
    $smokeResult = Invoke-NativeCppBundleSmoke -BundlePath $bundlePath
    if (-not [string]::IsNullOrWhiteSpace($EvidencePath)) {
        Write-NativeCppBundleEvidence `
            -BundlePath $bundlePath `
            -RequireCompilerRuntime ([bool]$RequireCompilerRuntime) `
            -Architecture $Architecture `
            -EvidencePath $EvidencePath `
            -SourceRevision $SourceRevision `
            -SmokeResult $smokeResult
    }
    Write-Output "Native C++ Windows bundle smoke passed: $bundlePath"
}
