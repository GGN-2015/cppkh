param(
    [Parameter(Mandatory = $true)]
    [string]$Target,
    [Parameter(Mandatory = $true)]
    [string]$Out,
    [string]$Compiler = ""
)

$ErrorActionPreference = "Stop"

function Resolve-Tool([string[]]$Names, [string]$CompilerPath) {
    $dirs = New-Object System.Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace($CompilerPath)) {
        try {
            $resolved = (Resolve-Path $CompilerPath -ErrorAction SilentlyContinue).Path
            if ($resolved) { $dirs.Add((Split-Path -Parent $resolved)) | Out-Null }
        } catch {}
    }
    foreach ($dir in $dirs) {
        foreach ($name in $Names) {
            $candidate = Join-Path $dir $name
            if (Test-Path $candidate) { return $candidate }
        }
    }
    foreach ($name in $Names) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return ""
}

function Get-SearchDirs([string]$TargetPath, [string]$OutDir, [string]$CompilerPath) {
    $dirs = New-Object System.Collections.Generic.List[string]
    foreach ($dir in @((Split-Path -Parent $TargetPath), $OutDir)) {
        if (-not [string]::IsNullOrWhiteSpace($dir) -and (Test-Path $dir)) {
            $dirs.Add((Resolve-Path $dir).Path) | Out-Null
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($CompilerPath)) {
        try {
            $resolved = (Resolve-Path $CompilerPath -ErrorAction SilentlyContinue).Path
            if ($resolved) { $dirs.Add((Split-Path -Parent $resolved)) | Out-Null }
        } catch {}
    }
    foreach ($envName in @("PATH", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH")) {
        $value = [Environment]::GetEnvironmentVariable($envName)
        if ([string]::IsNullOrWhiteSpace($value)) { continue }
        foreach ($dir in $value -split [IO.Path]::PathSeparator) {
            if (-not [string]::IsNullOrWhiteSpace($dir) -and (Test-Path $dir)) {
                try { $dirs.Add((Resolve-Path $dir).Path) | Out-Null } catch {}
            }
        }
    }
    return $dirs | Select-Object -Unique
}

function Test-SystemDependency([string]$PathOrName) {
    $name = [IO.Path]::GetFileName($PathOrName).ToLowerInvariant()
    if ($IsWindows -or $env:OS -eq "Windows_NT") {
        if ($name -match '^(api-ms-|ext-ms-)') { return $true }
        if ($name -match '^(kernel32|user32|gdi32|advapi32|shell32|ole32|oleaut32|ntdll|msvcrt|ucrtbase|vcruntime|ws2_32|secur32|bcrypt|crypt32|rpcrt4|comdlg32|comctl32|shlwapi|imm32|winmm|version|normaliz)\.dll$') { return $true }
        try {
            $full = (Resolve-Path $PathOrName -ErrorAction SilentlyContinue).Path
            if ($full -and $env:WINDIR -and $full.StartsWith($env:WINDIR, [StringComparison]::OrdinalIgnoreCase)) { return $true }
        } catch {}
        return $false
    }
    if ($IsMacOS) {
        if ($PathOrName.StartsWith("/System/Library/") -or $PathOrName.StartsWith("/usr/lib/")) { return $true }
        return $name -eq "libsystem.b.dylib"
    }
    return $name -match '^(linux-vdso|ld-linux|ld-musl|libc\.so|libm\.so|libpthread\.so|librt\.so|libdl\.so)'
}

function Get-DependencySpecs([string]$File, [string]$CompilerPath) {
    if ($IsWindows -or $env:OS -eq "Windows_NT") {
        $objdump = Resolve-Tool @("objdump.exe", "objdump") $CompilerPath
        if ([string]::IsNullOrWhiteSpace($objdump)) {
            Write-Warning "objdump was not found; cannot scan DLL dependencies for $File"
            return @()
        }
        return (& $objdump -p $File 2>$null) |
            ForEach-Object {
                if ($_ -match 'DLL Name:\s*(.+)$') { $Matches[1].Trim() }
            }
    }
    if ($IsMacOS) {
        $otool = Resolve-Tool @("otool") $CompilerPath
        if ([string]::IsNullOrWhiteSpace($otool)) {
            Write-Warning "otool was not found; cannot scan dylib dependencies for $File"
            return @()
        }
        return (& $otool -L $File 2>$null) |
            Select-Object -Skip 1 |
            ForEach-Object { ($_ -split '\s+')[0].Trim() } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    }
    $ldd = Resolve-Tool @("ldd") $CompilerPath
    if ([string]::IsNullOrWhiteSpace($ldd)) {
        Write-Warning "ldd was not found; cannot scan shared-library dependencies for $File"
        return @()
    }
    return (& $ldd $File 2>$null) |
        ForEach-Object {
            if ($_ -match '=>\s*(/[^ ]+)') { $Matches[1] }
            elseif ($_ -match '^\s*(/[^ ]+)') { $Matches[1] }
        } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
}

function Resolve-Dependency([string]$Spec, [string[]]$SearchDirs) {
    if ([string]::IsNullOrWhiteSpace($Spec)) { return "" }
    if ([IO.Path]::IsPathRooted($Spec) -and (Test-Path $Spec)) {
        return (Resolve-Path $Spec).Path
    }
    $name = [IO.Path]::GetFileName($Spec)
    foreach ($dir in $SearchDirs) {
        $candidate = Join-Path $dir $name
        if (Test-Path $candidate) { return (Resolve-Path $candidate).Path }
    }
    return ""
}

$targetPath = (Resolve-Path $Target).Path
New-Item -ItemType Directory -Path $Out -Force | Out-Null
$outPath = (Resolve-Path $Out).Path
$searchDirs = @(Get-SearchDirs $targetPath $outPath $Compiler)

$queue = New-Object System.Collections.Generic.Queue[string]
$seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
$copied = 0
$queue.Enqueue($targetPath)

while ($queue.Count -gt 0) {
    $file = $queue.Dequeue()
    if (-not $seen.Add($file)) { continue }
    foreach ($spec in @(Get-DependencySpecs $file $Compiler)) {
        if (Test-SystemDependency $spec) { continue }
        $dep = Resolve-Dependency $spec $searchDirs
        if ([string]::IsNullOrWhiteSpace($dep)) {
            Write-Warning "dependency not found: $spec"
            continue
        }
        if (Test-SystemDependency $dep) { continue }
        $dest = Join-Path $outPath ([IO.Path]::GetFileName($dep))
        if ((Resolve-Path $dep).Path -ne $dest) {
            Copy-Item -LiteralPath $dep -Destination $dest -Force
            Write-Host "Copied runtime dependency: $dest"
            $copied += 1
        }
        if (Test-Path $dest) { $queue.Enqueue((Resolve-Path $dest).Path) }
    }
}

Write-Host "Runtime dependency scan complete: copied $copied file(s)."
