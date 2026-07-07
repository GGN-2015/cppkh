param(
    [ValidateSet("auto", "win32", "pthread", "std", "boost", "single")]
    [string]$Backend = "auto",
    [string]$Cxx = $(if ($env:CXX) { $env:CXX } else { "g++" }),
    [string]$Out = "",
    [string]$Name = "javakh_cpp",
    [switch]$Static,
    [switch]$Native,
    [switch]$NoNative,
    [switch]$Portable,
    [switch]$NoLto,
    [switch]$NoStrip,
    [string]$ExtraCxxFlags = $env:CXXFLAGS,
    [string]$ExtraLdFlags = $env:LDFLAGS
)

$ErrorActionPreference = "Stop"

function Split-Args([string]$s) {
    if ([string]::IsNullOrWhiteSpace($s)) { return @() }
    return [System.Management.Automation.PSParser]::Tokenize($s, [ref]$null) |
        Where-Object { $_.Type -eq "CommandArgument" -or $_.Type -eq "CommandParameter" } |
        ForEach-Object { $_.Content }
}

function Test-Flag([string]$Flag) {
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("javakh_cpp_flag_{0}.cpp" -f ([Guid]::NewGuid()))
    $exe = [IO.Path]::ChangeExtension($tmp, ".exe")
    Set-Content -LiteralPath $tmp -Value "int main(){return 0;}" -Encoding ASCII
    try {
        $args = @("-std=c++14", $Flag, $tmp, "-o", $exe)
        & $Cxx @args *> $null
        return $LASTEXITCODE -eq 0
    } finally {
        Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $exe -ErrorAction SilentlyContinue
    }
}

$isWindows = $PSVersionTable.Platform -eq "Win32NT" -or $env:OS -eq "Windows_NT"
$platform = if ($isWindows) { "windows" } elseif ($IsMacOS) { "macos" } else { "linux" }
$exeExt = if ($isWindows) { ".exe" } else { "" }

if ($Backend -eq "auto") {
    $Backend = if ($isWindows) { "win32" } else { "pthread" }
}

if ([string]::IsNullOrWhiteSpace($Out)) {
    $Out = Join-Path "dist" $platform
}
New-Item -ItemType Directory -Path $Out -Force | Out-Null
$target = Join-Path $Out ($Name + $exeExt)

$cxxflags = @("-std=c++14", "-O3", "-DNDEBUG", "-Isrc")
$ldflags = @()
$libs = @()

switch ($Backend) {
    "win32" { $cxxflags += "-DKH_THREAD_BACKEND_WIN32" }
    "pthread" { $cxxflags += "-DKH_THREAD_BACKEND_PTHREAD"; $libs += "-pthread" }
    "std" { $cxxflags += "-DKH_THREAD_BACKEND_STD"; if (-not $isWindows) { $libs += "-pthread" } }
    "boost" { $cxxflags += "-DKH_THREAD_BACKEND_BOOST"; $libs += @("-lboost_thread", "-lboost_system"); if (-not $isWindows) { $libs += "-pthread" } }
    "single" { $cxxflags += "-DKH_THREAD_BACKEND_SINGLE" }
}

if (-not $NoLto -and (Test-Flag "-flto")) {
    $cxxflags += "-flto"
    $ldflags += "-flto"
}
if (-not $NoNative -and -not $Portable -and (Test-Flag "-march=native")) {
    $cxxflags += "-march=native"
}
if (Test-Flag "-static-libstdc++") {
    $ldflags += "-static-libstdc++"
}
if (Test-Flag "-static-libgcc") {
    $ldflags += "-static-libgcc"
}
if ($Static) {
    if ($platform -eq "macos") {
        Write-Warning "--static is not supported by normal macOS toolchains; ignoring"
    } else {
        $ldflags += "-static"
    }
}

$cxxflags += Split-Args $ExtraCxxFlags
$ldflags += Split-Args $ExtraLdFlags

Write-Host "Compiler : $Cxx"
Write-Host "Platform : $platform"
Write-Host "Backend  : $Backend"
Write-Host "Output   : $target"

& $Cxx @cxxflags "src/main.cpp" "-o" $target @ldflags @libs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $NoStrip) {
    $strip = Get-Command strip -ErrorAction SilentlyContinue
    if ($strip) {
        & $strip.Source $target 2>$null
    }
}

Write-Host "Packaged single executable: $target"
