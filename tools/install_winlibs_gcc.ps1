param(
    [string]$InstallRoot = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
    $InstallRoot = Join-Path (Split-Path -Parent $RepoRoot) "toolchains"
}

New-Item -ItemType Directory -Force $InstallRoot | Out-Null
$InstallRoot = (Resolve-Path $InstallRoot).Path

$headers = @{ "User-Agent" = "cppkh-winlibs-installer" }
$releases = Invoke-RestMethod -Uri "https://api.github.com/repos/brechtsanders/winlibs_mingw/releases" -Headers $headers
$asset = $releases |
    ForEach-Object { $_.assets } |
    Where-Object {
        $_.name -match "x86_64" -and
        $_.name -match "posix" -and
        $_.name -match "ucrt" -and
        $_.name -match "\.zip$" -and
        $_.name -notmatch "llvm|snapshot"
    } |
    Select-Object -First 1

if (-not $asset) {
    throw "No matching WinLibs x86_64 POSIX UCRT zip asset was found."
}

$baseName = [IO.Path]::GetFileNameWithoutExtension($asset.name)
$zipPath = Join-Path $InstallRoot $asset.name
$dest = Join-Path $InstallRoot $baseName
$gxx = Join-Path $dest "mingw64\bin\g++.exe"

if ($Force -and (Test-Path $dest)) {
    Remove-Item -LiteralPath $dest -Recurse -Force
}

if (-not (Test-Path $zipPath) -or ((Get-Item $zipPath).Length -ne [int64]$asset.size)) {
    Write-Host "Downloading $($asset.name) ..."
    curl.exe -L --fail --retry 3 --retry-delay 2 -o $zipPath $asset.browser_download_url
    if ($LASTEXITCODE -ne 0) {
        throw "curl failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path $gxx)) {
    New-Item -ItemType Directory -Force $dest | Out-Null
    Write-Host "Extracting to $dest ..."
    tar.exe -xf $zipPath -C $dest
    if ($LASTEXITCODE -ne 0) {
        throw "tar failed with exit code $LASTEXITCODE"
    }
}

$readme = Join-Path $InstallRoot "README-winlibs.txt"
@(
    "WinLibs MinGW-w64 GCC toolchain",
    "Source: https://github.com/brechtsanders/winlibs_mingw/releases",
    "Asset: $($asset.name)",
    "URL: $($asset.browser_download_url)",
    "Compiler: $gxx"
) | Set-Content -LiteralPath $readme -Encoding ASCII

$envFile = Join-Path $InstallRoot "winlibs-gcc64.env.ps1"
@(
    "`$env:CXX = '$gxx'",
    "Write-Host `"CXX=`$env:CXX`""
) | Set-Content -LiteralPath $envFile -Encoding ASCII

Write-Host "Installed compiler:"
& $gxx --version | Select-Object -First 1
Write-Host "Target: $(& $gxx -dumpmachine)"
Write-Host "CXX: $gxx"
Write-Host "Environment helper: $envFile"
