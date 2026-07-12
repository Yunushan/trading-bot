[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^https://github\.com/[^/]+/[^/]+/?$')]
    [string]$RepositoryUrl,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$RegistrationToken,

    [string]$RunnerDirectory = (Join-Path $env:ProgramData 'TradingBot\actions-runner'),

    [string]$RunnerName = "$env:COMPUTERNAME-trading-bot-windows-11",

    [switch]$InstallService
)

$ErrorActionPreference = 'Stop'

function Assert-Windows11X64 {
    $operatingSystem = Get-CimInstance -ClassName Win32_OperatingSystem
    $computerSystem = Get-CimInstance -ClassName Win32_ComputerSystem
    $build = [int]($operatingSystem.BuildNumber)

    if ($operatingSystem.ProductType -ne 1 -or $build -lt 22000) {
        throw 'This helper only configures a Windows 11 workstation runner. Windows Server and Windows 10 are not accepted.'
    }
    if ($computerSystem.SystemType -notmatch 'x64') {
        throw "This helper requires an x64 host; observed system type: $($computerSystem.SystemType)."
    }
}

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'InstallService requires an elevated PowerShell session.'
    }
}

function Get-RunnerAssetUrl {
    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/actions/runner/releases/latest' -Headers @{ 'User-Agent' = 'trading-bot-runner-setup' }
    $asset = @($release.assets | Where-Object { $_.name -match '^actions-runner-win-x64-[0-9.]+\.zip$' }) | Select-Object -First 1
    if ($null -eq $asset -or -not $asset.browser_download_url) {
        throw 'Could not locate the latest actions-runner Windows x64 archive.'
    }
    return [string]$asset.browser_download_url
}

Assert-Windows11X64

if ($InstallService) {
    Assert-Administrator
}

$resolvedDirectory = [IO.Path]::GetFullPath($RunnerDirectory)
if (Test-Path -LiteralPath $resolvedDirectory) {
    $existing = Get-ChildItem -LiteralPath $resolvedDirectory -Force -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $existing) {
        throw "Runner directory is not empty: $resolvedDirectory. Choose a new empty directory; this helper never replaces an existing runner."
    }
}

$labels = 'tb-release-platform,windows-11-x64'
$archivePath = Join-Path ([IO.Path]::GetTempPath()) "actions-runner-win-x64-$([Guid]::NewGuid().ToString('N')).zip"

if (-not $PSCmdlet.ShouldProcess($resolvedDirectory, 'Download and configure the GitHub Actions Windows 11 release runner')) {
    Write-Output 'No runner configuration was performed.'
    return
}

New-Item -ItemType Directory -Path $resolvedDirectory -Force | Out-Null
$assetUrl = Get-RunnerAssetUrl
try {
    Invoke-WebRequest -Uri $assetUrl -OutFile $archivePath
    Expand-Archive -LiteralPath $archivePath -DestinationPath $resolvedDirectory -Force

    Push-Location $resolvedDirectory
    try {
        & .\config.cmd --unattended --url $RepositoryUrl --token $RegistrationToken --name $RunnerName --labels $labels --work '_work'
        if ($LASTEXITCODE -ne 0) {
            throw "GitHub Actions runner configuration failed with exit code $LASTEXITCODE."
        }
        if ($InstallService) {
            & .\svc.cmd install
            if ($LASTEXITCODE -ne 0) {
                throw "GitHub Actions runner service installation failed with exit code $LASTEXITCODE."
            }
            & .\svc.cmd start
            if ($LASTEXITCODE -ne 0) {
                throw "GitHub Actions runner service start failed with exit code $LASTEXITCODE."
            }
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    Remove-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue
}

Write-Output "Windows 11 x64 runner labels: self-hosted, windows, x64, $labels"
Write-Output "Runner directory: $resolvedDirectory"
if (-not $InstallService) {
    Write-Output 'Runner configured without a service. Start run.cmd manually or rerun with -InstallService from an elevated session.'
}
