param(
    [ValidateSet("auto", "win32", "pthread", "std", "boost", "single")]
    [string]$Backend = "auto",
    [string]$Cxx = "",
    [string]$Out = "",
    [string]$Name = "cppkh",
    [switch]$Shared,
    [switch]$Static,
    [switch]$Native,
    [switch]$NoNative,
    [switch]$Portable,
    [switch]$Lto,
    [switch]$NoLto,
    [switch]$NoStrip,
    [string]$ExtraCxxFlags = $env:CXXFLAGS,
    [string]$ExtraLdFlags = $env:LDFLAGS
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoParent = Split-Path -Parent $ScriptDir

function Split-Args([string]$s) {
    if ([string]::IsNullOrWhiteSpace($s)) { return @() }
    return [System.Management.Automation.PSParser]::Tokenize($s, [ref]$null) |
        Where-Object { $_.Type -eq "CommandArgument" -or $_.Type -eq "CommandParameter" } |
        ForEach-Object { $_.Content }
}

function Invoke-TestCompile([string[]]$Arguments, [string]$Source = "int main(){return 0;}", [string[]]$PostArguments = @()) {
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("cppkh_flag_{0}.cpp" -f ([Guid]::NewGuid()))
    $exe = [IO.Path]::ChangeExtension($tmp, ".exe")
    Set-Content -LiteralPath $tmp -Value $Source -Encoding ASCII
    try {
        $args = @("-std=c++14") + $Arguments + @($tmp, "-o", $exe) + $PostArguments
        & $Cxx @args *> $null
        return $LASTEXITCODE -eq 0
    } finally {
        Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $exe -ErrorAction SilentlyContinue
    }
}

function Test-Flag([string]$Flag) {
    return Invoke-TestCompile -Arguments @($Flag)
}

function Test-Compiler([string]$Candidate) {
    if ([string]::IsNullOrWhiteSpace($Candidate)) { return $false }
    try {
        & $Candidate "--version" *> $null
        if ($LASTEXITCODE -ne 0) { return $false }
    } catch {
        return $false
    }
    $oldCxx = $script:Cxx
    $script:Cxx = $Candidate
    try { return Invoke-TestCompile -Arguments @() }
    finally { $script:Cxx = $oldCxx }
}

function Resolve-Cxx {
    if (-not [string]::IsNullOrWhiteSpace($Cxx)) {
        if (Test-Compiler $Cxx) { return $Cxx }
        throw "C++ compiler '$Cxx' is not usable."
    }
    if (-not [string]::IsNullOrWhiteSpace($env:CXX)) {
        if (Test-Compiler $env:CXX) { return $env:CXX }
        throw "CXX points to '$env:CXX', but it is not usable."
    }
    $candidates = New-Object System.Collections.Generic.List[string]
    $toolchainRoot = Join-Path $RepoParent "toolchains"
    if (Test-Path $toolchainRoot) {
        Get-ChildItem -Path $toolchainRoot -Recurse -Filter "g++.exe" -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "\\mingw64\\bin\\g\+\+\.exe$" } |
            Sort-Object FullName -Descending |
            ForEach-Object { $candidates.Add($_.FullName) | Out-Null }
    }
    foreach ($name in @("g++", "clang++", "c++")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { $candidates.Add($cmd.Source) | Out-Null }
    }
    foreach ($candidate in $candidates) {
        if (Test-Compiler $candidate) { return $candidate }
    }
    throw "No usable C++14 compiler found. Install g++ or pass -Cxx <compiler>."
}

function Test-Backend([string]$Name) {
    switch ($Name) {
        "pthread" { return Invoke-TestCompile -Arguments @("-DKH_THREAD_BACKEND_PTHREAD", "-pthread") -Source "#include <pthread.h>`nint main(){pthread_t t; (void)t; return 0;}" }
        "win32" { return Invoke-TestCompile -Arguments @("-DKH_THREAD_BACKEND_WIN32") -Source "#include <windows.h>`nint main(){CRITICAL_SECTION cs; InitializeCriticalSection(&cs); DeleteCriticalSection(&cs); return 0;}" }
        "std" { return Invoke-TestCompile -Arguments @("-DKH_THREAD_BACKEND_STD") -Source "#include <thread>`nint main(){return 0;}" }
        "boost" { return Invoke-TestCompile -Arguments @("-DKH_THREAD_BACKEND_BOOST") -PostArguments @("-lboost_thread", "-lboost_system") -Source "#include <boost/thread.hpp>`nint main(){return 0;}" }
        "single" { return Invoke-TestCompile -Arguments @("-DKH_THREAD_BACKEND_SINGLE") }
    }
    return $false
}

function Resolve-Backend {
    if ($Backend -ne "auto") {
        if (Test-Backend $Backend) { return $Backend }
        throw "Requested backend '$Backend' is not supported by compiler '$Cxx'."
    }
    $order = if ($isWindows -and $Shared) {
        @("win32", "pthread", "std", "single")
    } elseif ($isWindows) {
        @("pthread", "win32", "std", "single")
    } else {
        @("pthread", "std", "single")
    }
    foreach ($candidate in $order) {
        if (Test-Backend $candidate) { return $candidate }
    }
    throw "No supported thread backend found for compiler '$Cxx'."
}

$isWindows = $PSVersionTable.Platform -eq "Win32NT" -or $env:OS -eq "Windows_NT"
$platform = if ($isWindows) { "windows" } elseif ($IsMacOS) { "macos" } else { "linux" }
$exeExt = if ($isWindows) { ".exe" } else { "" }
$sharedExt = if ($isWindows) { ".dll" } elseif ($platform -eq "macos") { ".dylib" } else { ".so" }

$Cxx = Resolve-Cxx
$Backend = Resolve-Backend

if ([string]::IsNullOrWhiteSpace($Out)) {
    $Out = Join-Path "dist" $platform
}
New-Item -ItemType Directory -Path $Out -Force | Out-Null
$targetExt = if ($Shared) { $sharedExt } else { $exeExt }
if ($Shared -and -not $isWindows -and -not $Name.StartsWith("lib")) {
    $target = Join-Path $Out ("lib" + $Name + $targetExt)
} else {
    $target = Join-Path $Out ($Name + $targetExt)
}

$cxxflags = @("-std=c++14", "-O3", "-DNDEBUG", "-Isrc")
$ldflags = @()
$libs = @()

if ($Shared) {
    $cxxflags += "-DCPPKH_SHARED_LIBRARY"
    if (-not $isWindows -and (Test-Flag "-fPIC")) { $cxxflags += "-fPIC" }
    if ($platform -eq "macos") { $ldflags += "-dynamiclib" }
    else { $ldflags += "-shared" }
}

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
if ($Static) {
    if ($Shared) {
        Write-Warning "--static is ignored when -Shared is used"
    } elseif ($platform -eq "macos") {
        Write-Warning "--static is not supported by normal macOS toolchains; ignoring"
    } elseif (Test-Flag "-static") {
        if (Test-Flag "-static-libstdc++") { $ldflags += "-static-libstdc++" }
        if (Test-Flag "-static-libgcc") { $ldflags += "-static-libgcc" }
        $ldflags += "-static"
    } else {
        Write-Warning "full static linking is not supported by this compiler; continuing with dynamic runtime libraries"
    }
}

$cxxflags += Split-Args $ExtraCxxFlags
$ldflags += Split-Args $ExtraLdFlags

Write-Host "Compiler : $Cxx"
Write-Host "Platform : $platform"
Write-Host "Backend  : $Backend"
Write-Host "Kind     : $(if ($Shared) { 'shared library' } else { 'executable' })"
Write-Host "Output   : $target"

& $Cxx @cxxflags "src/main.cpp" "-o" $target @ldflags @libs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $NoStrip) {
    $stripCommand = ""
    try {
        $compilerPath = (Resolve-Path $Cxx -ErrorAction SilentlyContinue).Path
        if (-not [string]::IsNullOrWhiteSpace($compilerPath)) {
            $compilerStrip = Join-Path (Split-Path -Parent $compilerPath) ("strip" + $exeExt)
            if (Test-Path $compilerStrip) { $stripCommand = $compilerStrip }
        }
    } catch {}
    if ([string]::IsNullOrWhiteSpace($stripCommand)) {
        $strip = Get-Command strip -ErrorAction SilentlyContinue
        if ($strip) { $stripCommand = $strip.Source }
    }
    if (-not [string]::IsNullOrWhiteSpace($stripCommand)) {
        $oldPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $stripCommand $target *> $null
        $stripExit = $LASTEXITCODE
        $ErrorActionPreference = $oldPreference
        if ($stripExit -ne 0) {
            Write-Warning "strip failed; leaving the executable unstripped"
        }
    }
}

if ($Shared -or -not $Static) {
    $depScript = Join-Path $ScriptDir "tools\copy_runtime_deps.ps1"
    if (Test-Path $depScript) {
        & $depScript -Target $target -Out $Out -Compiler $Cxx
    } else {
        Write-Warning "runtime dependency scanner was not found: $depScript"
    }
}

if ($Shared) {
    Write-Host "Packaged shared library: $target"
} else {
    Write-Host "Packaged executable: $target"
}
