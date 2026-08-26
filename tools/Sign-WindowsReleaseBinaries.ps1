[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("windows-x64", "windows-arm64")]
    [string]$TargetId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[0-9a-f]{40}$")]
    [string]$SourceRevision,

    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-OneReleaseFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Filter
    )

    $matches = @(Get-ChildItem -LiteralPath "release" -Filter $Filter -File)
    if ($matches.Count -ne 1) {
        throw "Expected exactly one release file matching $Filter; found $($matches.Count)."
    }
    return $matches[0]
}

function Resolve-SignTool {
    $command = Get-Command "signtool.exe" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    $kitsRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    if (!(Test-Path -LiteralPath $kitsRoot -PathType Container)) {
        throw "SignTool was not found on PATH and the Windows SDK bin directory is unavailable."
    }
    $candidate = Get-ChildItem -LiteralPath $kitsRoot -Recurse -Filter "signtool.exe" -File |
        Sort-Object FullName -Descending |
        Select-Object -First 1
    if ($null -eq $candidate) {
        throw "SignTool was not found in the Windows SDK."
    }
    return $candidate.FullName
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,

        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code $LASTEXITCODE)."
    }
}

if ([string]::IsNullOrWhiteSpace($env:WINDOWS_CODESIGN_PFX_B64) -or
    [string]::IsNullOrWhiteSpace($env:WINDOWS_CODESIGN_PFX_PASSWORD)) {
    throw "Required Windows code-signing credentials are unavailable. Tagged releases must fail closed."
}
if ($TimestampUrl -notmatch "^https?://[^/?#]+(?:/[^?#]*)?$") {
    throw "TimestampUrl must be an HTTP(S) URL without a query or fragment."
}
if ($env:WINDOWS_CODESIGN_PFX_B64.Length -gt 4000000) {
    throw "Windows code-signing certificate payload exceeds the 4,000,000 character limit."
}

$workspace = if ([string]::IsNullOrWhiteSpace($env:GITHUB_WORKSPACE)) {
    (Get-Location).Path
} else {
    $env:GITHUB_WORKSPACE
}
$workspace = [IO.Path]::GetFullPath($workspace)
$releaseDir = [IO.Path]::GetFullPath((Join-Path $workspace "release"))
if (!(Test-Path -LiteralPath $releaseDir -PathType Container)) {
    throw "Release directory does not exist: $releaseDir"
}

$pythonAsset = Get-OneReleaseFile -Filter "Trading-Bot-Python-$TargetId-*.exe"
$rustAsset = Get-OneReleaseFile -Filter "Trading-Bot-Rust-$TargetId-*.exe"
$tauriAsset = Get-OneReleaseFile -Filter "Trading-Bot-Rust-tauri-$TargetId-*.exe"
$cppZip = Get-OneReleaseFile -Filter "Trading-Bot-C++-$TargetId-*.zip"
$cppBundleName = if ($TargetId -eq "windows-arm64") { "Trading-Bot-C++-arm64" } else { "Trading-Bot-C++" }
$cppBundleDir = Join-Path $releaseDir $cppBundleName
$cppExecutable = Join-Path $cppBundleDir "Trading-Bot-C++.exe"
if (!(Test-Path -LiteralPath $cppExecutable -PathType Leaf)) {
    throw "Packaged C++ executable does not exist: $cppExecutable"
}

$signingTargets = @(
    $pythonAsset.FullName,
    $rustAsset.FullName,
    $tauriAsset.FullName,
    $cppExecutable
)
foreach ($path in $signingTargets) {
    $resolved = [IO.Path]::GetFullPath($path)
    if (!$resolved.StartsWith("$workspace$([IO.Path]::DirectorySeparatorChar)", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to sign a path outside the GitHub workspace."
    }
    if ([IO.Path]::GetExtension($resolved) -ne ".exe") {
        throw "Windows signing targets must be .exe files."
    }
}

$pfxPath = Join-Path $env:RUNNER_TEMP "trading-bot-codesign-$([Guid]::NewGuid().ToString('N')).pfx"
$importedCertificates = @()
try {
    try {
        $pfxBytes = [Convert]::FromBase64String($env:WINDOWS_CODESIGN_PFX_B64)
    } catch {
        throw "Windows code-signing certificate payload is not valid base64."
    }
    if ($pfxBytes.Length -eq 0 -or $pfxBytes.Length -gt 2000000) {
        throw "Windows code-signing certificate must be between 1 byte and 2 MB."
    }
    [IO.File]::WriteAllBytes($pfxPath, $pfxBytes)
    $securePassword = ConvertTo-SecureString $env:WINDOWS_CODESIGN_PFX_PASSWORD -AsPlainText -Force
    $importedCertificates = @(
        Import-PfxCertificate `
            -FilePath $pfxPath `
            -CertStoreLocation "Cert:\CurrentUser\My" `
            -Password $securePassword `
            -Exportable:$false
    )
    $codeSigningCertificates = @(
        $importedCertificates | Where-Object {
            $_.HasPrivateKey -and
            $_.NotBefore.ToUniversalTime() -le (Get-Date).ToUniversalTime() -and
            $_.NotAfter.ToUniversalTime() -gt (Get-Date).ToUniversalTime() -and
            @($_.EnhancedKeyUsageList | ForEach-Object { $_.ObjectId.Value }) -contains "1.3.6.1.5.5.7.3.3"
        }
    )
    if ($codeSigningCertificates.Count -ne 1) {
        throw "The PFX must contain exactly one currently valid code-signing certificate with a private key."
    }
    $certificate = $codeSigningCertificates[0]
    $signTool = Resolve-SignTool

    foreach ($path in $signingTargets) {
        Invoke-Checked `
            -Executable $signTool `
            -Arguments @(
                "sign", "/sha1", $certificate.Thumbprint, "/s", "My",
                "/fd", "SHA256", "/tr", $TimestampUrl, "/td", "SHA256", "/v", $path
            ) `
            -FailureMessage "Authenticode signing failed for $([IO.Path]::GetFileName($path))"
        Invoke-Checked `
            -Executable $signTool `
            -Arguments @("verify", "/pa", "/all", "/tw", "/v", $path) `
            -FailureMessage "Authenticode verification failed for $([IO.Path]::GetFileName($path))"
        $signature = Get-AuthenticodeSignature -LiteralPath $path
        if ($signature.Status -ne "Valid") {
            throw "Authenticode verification did not return Valid for $([IO.Path]::GetFileName($path))."
        }
        if ($null -eq $signature.TimeStamperCertificate) {
            throw "Authenticode verification found no trusted timestamp for $([IO.Path]::GetFileName($path))."
        }
    }

    Remove-Item -LiteralPath $cppZip.FullName -Force
    Compress-Archive -Path (Join-Path $cppBundleDir "*") -DestinationPath $cppZip.FullName -Force
    if (!(Test-Path -LiteralPath $cppZip.FullName -PathType Leaf)) {
        throw "Signed C++ bundle could not be recompressed."
    }

    $evidencePath = Join-Path $releaseDir "release-signing-$TargetId.json"
    $writerArgs = @(
        "tools/write_release_signing_evidence.py",
        "--platform", "windows",
        "--target-id", $TargetId,
        "--source-revision", $SourceRevision,
        "--output", $evidencePath
    )
    foreach ($asset in @($pythonAsset.FullName, $rustAsset.FullName, $tauriAsset.FullName, $cppZip.FullName)) {
        $writerArgs += @("--asset", $asset)
    }
    foreach ($target in $signingTargets) {
        $writerArgs += @("--signature-target", $target)
    }
    Invoke-Checked `
        -Executable "python" `
        -Arguments $writerArgs `
        -FailureMessage "Windows release signing evidence generation failed"
    Invoke-Checked `
        -Executable "python" `
        -Arguments @(
            "tools/check_release_signing_evidence.py", $evidencePath,
            "--asset-dir", $releaseDir, "--require-current-revision"
        ) `
        -FailureMessage "Windows release signing evidence verification failed"
} finally {
    if (Test-Path -LiteralPath $pfxPath) {
        Remove-Item -LiteralPath $pfxPath -Force -ErrorAction SilentlyContinue
    }
    foreach ($imported in $importedCertificates) {
        if (-not [string]::IsNullOrWhiteSpace($imported.Thumbprint)) {
            Remove-Item -LiteralPath "Cert:\CurrentUser\My\$($imported.Thumbprint)" -Force -ErrorAction SilentlyContinue
        }
    }
}
