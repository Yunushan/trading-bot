[CmdletBinding(DefaultParameterSetName = "Copy")]
param(
    [Parameter(Mandatory = $true, ParameterSetName = "Copy")]
    [ValidateNotNullOrEmpty()]
    [string]$BundleDir,

    [Parameter(Mandatory = $true, ParameterSetName = "Copy")]
    [ValidateSet("x64", "arm64")]
    [string]$Architecture,

    [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")]
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$runtimeNames = @(
    "concrt140.dll",
    "msvcp140.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll"
)

function Test-RuntimeDirectory {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Container)) {
        return $false
    }
    foreach ($name in $runtimeNames) {
        if (-not (Test-Path -LiteralPath (Join-Path $Path $name) -PathType Leaf)) {
            return $false
        }
    }
    return $true
}

function Get-RuntimeCandidateDirectories {
    param([ValidateSet("x64", "arm64")][string]$Architecture)

    $candidateDirectories = [System.Collections.Generic.List[string]]::new()
    $redistHint = [Environment]::GetEnvironmentVariable("VCToolsRedistDir", "Process")
    if (-not [string]::IsNullOrWhiteSpace($redistHint)) {
        $candidateDirectories.Add((Join-Path $redistHint "$Architecture\Microsoft.VC143.CRT"))
        $candidateDirectories.Add((Join-Path $redistHint "$Architecture\Microsoft.VC145.CRT"))
    }

    $visualStudioRoots = [System.Collections.Generic.List[string]]::new()
    foreach ($environmentName in @("ProgramFiles", "ProgramFiles(x86)")) {
        $programFiles = [Environment]::GetEnvironmentVariable($environmentName, "Process")
        if ([string]::IsNullOrWhiteSpace($programFiles)) {
            continue
        }
        $root = Join-Path $programFiles "Microsoft Visual Studio"
        if (Test-Path -LiteralPath $root -PathType Container) {
            $visualStudioRoots.Add($root)
        }
    }

    foreach ($root in $visualStudioRoots) {
        Get-ChildItem -LiteralPath $root -Directory -Recurse -ErrorAction SilentlyContinue |
            Where-Object {
                $_.FullName -match "[\\/]$Architecture[\\/]Microsoft\.VC[0-9]+\.CRT$"
            } |
            Sort-Object FullName -Descending |
            ForEach-Object {
                $candidateDirectories.Add($_.FullName)
            }
    }

    return @($candidateDirectories | Select-Object -Unique)
}

function Find-RuntimeDirectory {
    param(
        [ValidateSet("x64", "arm64")][string]$Architecture,
        [string[]]$CandidateDirectories
    )

    $runtimeDirectory = $CandidateDirectories |
        Where-Object { Test-RuntimeDirectory -Path $_ } |
        Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($runtimeDirectory)) {
        throw "Could not locate a complete MSVC runtime for $Architecture. Install the matching Visual C++ build tools or set VCToolsRedistDir."
    }
    return $runtimeDirectory
}

function Copy-MsvcRuntimeFiles {
    param(
        [string]$BundleDir,
        [ValidateSet("x64", "arm64")][string]$Architecture,
        [string[]]$CandidateDirectories
    )

    $bundlePath = (Resolve-Path -LiteralPath $BundleDir -ErrorAction Stop).Path
    if (-not (Test-Path -LiteralPath $bundlePath -PathType Container)) {
        throw "C++ bundle directory does not exist: $bundlePath"
    }
    if ($null -eq $CandidateDirectories) {
        $CandidateDirectories = @(Get-RuntimeCandidateDirectories -Architecture $Architecture)
    }
    $runtimeDirectory = Find-RuntimeDirectory `
        -Architecture $Architecture `
        -CandidateDirectories $CandidateDirectories

    foreach ($name in $runtimeNames) {
        Copy-Item -LiteralPath (Join-Path $runtimeDirectory $name) -Destination (Join-Path $bundlePath $name) -Force
    }

    $missing = @(
        $runtimeNames | Where-Object {
            -not (Test-Path -LiteralPath (Join-Path $bundlePath $_) -PathType Leaf)
        }
    )
    if ($missing.Count -gt 0) {
        throw "MSVC runtime copy did not produce a complete bundle. Missing: $($missing -join ', ')"
    }

    Write-Output "Copied MSVC $Architecture runtime from $runtimeDirectory to $bundlePath"
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

function Invoke-CopyMsvcRuntimeSelfTest {
    $testRoot = Join-Path ([IO.Path]::GetTempPath()) ("trading-bot-msvc-runtime-" + [Guid]::NewGuid().ToString("N"))
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $fullTestRoot = [IO.Path]::GetFullPath($testRoot)
    if (-not $fullTestRoot.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to create self-test outside the temporary directory: $fullTestRoot"
    }

    New-Item -ItemType Directory -Path $testRoot | Out-Null
    try {
        foreach ($testArchitecture in @("x64", "arm64")) {
            $bundle = Join-Path $testRoot "bundle-$testArchitecture"
            $runtime = Join-Path $testRoot "redist-$testArchitecture"
            New-Item -ItemType Directory -Path $bundle, $runtime | Out-Null
            foreach ($name in $runtimeNames) {
                Set-Content -LiteralPath (Join-Path $runtime $name) -Value "$testArchitecture-$name" -NoNewline
            }

            Copy-MsvcRuntimeFiles `
                -BundleDir $bundle `
                -Architecture $testArchitecture `
                -CandidateDirectories @($runtime) | Out-Null
            foreach ($name in $runtimeNames) {
                $copied = Get-Content -LiteralPath (Join-Path $bundle $name) -Raw
                if ($copied -ne "$testArchitecture-$name") {
                    throw "Self-test copied unexpected content for $testArchitecture/$name."
                }
            }

            Remove-Item -LiteralPath (Join-Path $runtime $runtimeNames[0]) -Force
            Assert-ExpectedFailure `
                -Action {
                    Find-RuntimeDirectory `
                        -Architecture $testArchitecture `
                        -CandidateDirectories @($runtime) | Out-Null
                } `
                -MessagePattern "Could not locate a complete MSVC runtime*"
        }
    } finally {
        if (Test-Path -LiteralPath $testRoot -PathType Container) {
            $resolvedCleanup = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $testRoot).Path)
            if ($resolvedCleanup -ne $fullTestRoot -or -not $resolvedCleanup.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing unsafe self-test cleanup: $resolvedCleanup"
            }
            Remove-Item -LiteralPath $resolvedCleanup -Recurse -Force
        }
    }

    Write-Output "Copy-MsvcRuntimeToBundle self-test passed."
}

if ($SelfTest) {
    Invoke-CopyMsvcRuntimeSelfTest
} else {
    Copy-MsvcRuntimeFiles -BundleDir $BundleDir -Architecture $Architecture
}
