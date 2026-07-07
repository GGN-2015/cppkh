param(
    [string]$InputFile = "",
    [string]$CppExe = "",
    [ValidateSet("source", "local", "both")]
    [string]$JavaMode = "source",
    [string]$JavaSourceDir = "",
    [string]$LocalJavaRoot = "",
    [int]$Limit = 0,
    [int]$Threads = 1,
    [string]$OutDir = "",
    [switch]$SkipJavaBuild,
    [switch]$NoExternalSimplify
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$RepoParent = Split-Path -Parent $RepoRoot

if ([string]::IsNullOrWhiteSpace($InputFile)) {
    $candidate = Join-Path $RepoParent "javakh_ori\test_pdcode.txt"
    if (Test-Path $candidate) {
        $InputFile = $candidate
    } else {
        $InputFile = Join-Path $RepoRoot "test_pdcode.txt"
    }
}
$InputFile = (Resolve-Path $InputFile).Path

if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $OutDir = Join-Path $RepoRoot "benchmark"
}
New-Item -ItemType Directory -Force $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path

if ([string]::IsNullOrWhiteSpace($CppExe)) {
    $cppCandidates = @(
        (Join-Path $RepoRoot "dist\windows\cppkh.exe"),
        (Join-Path $RepoRoot "build\cppkh.exe"),
        (Join-Path $RepoRoot "cppkh.exe")
    )
    $CppExe = ($cppCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1)
    if ([string]::IsNullOrWhiteSpace($CppExe)) {
        throw "Cannot find cppkh.exe. Build first or pass -CppExe."
    }
}
$CppExe = (Resolve-Path $CppExe).Path

if ([string]::IsNullOrWhiteSpace($JavaSourceDir)) {
    $JavaSourceDir = Join-Path $env:TEMP "JavaKh-v2-src"
}
if ([string]::IsNullOrWhiteSpace($LocalJavaRoot)) {
    $LocalJavaRoot = Join-Path $RepoParent "javakh_ori"
}

function Join-ClassPath([string[]]$Parts) {
    return ($Parts -join [IO.Path]::PathSeparator)
}

function Convert-TestPdCode {
    param(
        [string]$Path,
        [string]$PdOut,
        [string]$LabelsOut,
        [int]$MaxItems
    )

    $prepare = Join-Path $ScriptDir "prepare_pdcode.py"
    $simplifyMode = if ($NoExternalSimplify) { "none" } else { "external" }
    $args = @($prepare, "--input", $Path, "--pd-out", $PdOut, "--labels-out", $LabelsOut, "--simplify", $simplifyMode)
    if ($MaxItems -gt 0) {
        $args += @("--limit", [string]$MaxItems)
    }
    $countText = & python @args
    if ($LASTEXITCODE -ne 0) {
        throw "prepare_pdcode.py failed"
    }
    $lastLine = [string]($countText | Select-Object -Last 1)
    return [int]$lastLine.Trim()
}

function Get-QuotedResults {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return @() }
    $text = [IO.File]::ReadAllText($Path)
    $matches = [regex]::Matches($text, '"([^"]*)"')
    $results = New-Object System.Collections.Generic.List[string]
    foreach ($m in $matches) {
        $results.Add($m.Groups[1].Value) | Out-Null
    }
    return @($results)
}

function Invoke-CapturedProcess {
    param(
        [string]$FileName,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [string]$StdInFile,
        [string]$OutFile,
        [string]$ErrFile
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FileName
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.RedirectStandardInput = -not [string]::IsNullOrWhiteSpace($StdInFile)
    $escapedArgs = New-Object System.Collections.Generic.List[string]
    foreach ($arg in $Arguments) {
        if ($null -eq $arg) {
            $escapedArgs.Add('""') | Out-Null
        } elseif ($arg -match '[\s"]') {
            $escapedArgs.Add(('"{0}"' -f ($arg -replace '"', '\"'))) | Out-Null
        } else {
            $escapedArgs.Add($arg) | Out-Null
        }
    }
    $psi.Arguments = ($escapedArgs -join " ")

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $proc.Start() | Out-Null
    $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
    $stderrTask = $proc.StandardError.ReadToEndAsync()
    if (-not [string]::IsNullOrWhiteSpace($StdInFile)) {
        $proc.StandardInput.Write([IO.File]::ReadAllText($StdInFile))
        $proc.StandardInput.Close()
    }
    $proc.WaitForExit()
    $timer.Stop()

    [IO.File]::WriteAllText($OutFile, $stdoutTask.GetAwaiter().GetResult())
    [IO.File]::WriteAllText($ErrFile, $stderrTask.GetAwaiter().GetResult())
    return [pscustomobject]@{
        Seconds = $timer.Elapsed.TotalSeconds
        ExitCode = $proc.ExitCode
    }
}

function Build-JavaKhV2 {
    param([string]$Root)
    $Root = (Resolve-Path $Root).Path
    $buildDir = Join-Path $Root "build"
    $mainClass = Join-Path $buildDir "org\katlas\JavaKh\JavaKh.class"
    if ((Test-Path $mainClass) -and $SkipJavaBuild) { return }
    if (Test-Path $mainClass) { return }

    New-Item -ItemType Directory -Force $buildDir | Out-Null
    $jars = @(
        (Join-Path $Root "jars\log4j-1.2.12.jar"),
        (Join-Path $Root "jars\junit-4.12.jar"),
        (Join-Path $Root "jars\commons-logging-1.1.jar"),
        (Join-Path $Root "jars\commons-io-1.2.jar"),
        (Join-Path $Root "jars\commons-cli-1.0.jar")
    )
    $cp = Join-ClassPath $jars
    $sourcesFile = Join-Path $buildDir "sources.list"
    Get-ChildItem (Join-Path $Root "src") -Recurse -Filter *.java | ForEach-Object { $_.FullName } | Set-Content -Encoding ASCII $sourcesFile
    & javac -d $buildDir -cp $cp "@$sourcesFile"
    if ($LASTEXITCODE -ne 0) {
        throw "javac failed while building JavaKh-v2."
    }
}

function Invoke-Cpp {
    param([string]$PdFile)
    $out = Join-Path $OutDir "cpp.out"
    $err = Join-Path $OutDir "cpp.err"
    $threadArg = if ($Threads -eq 0) { "auto" } else { [string]([Math]::Max(1, $Threads)) }
    $cppArgs = @("--pd-file", $PdFile, "--quiet", "--threads", $threadArg)
    if (-not $NoExternalSimplify) {
        $cppArgs += "--no-simplify-pd"
    }
    $elapsed = Measure-Command {
        & $CppExe @cppArgs > $out 2> $err
    }
    $exit = $LASTEXITCODE
    return [pscustomobject]@{
        Name = "cppkh"
        Seconds = $elapsed.TotalSeconds
        ExitCode = $exit
        Out = $out
        Err = $err
        Results = @(Get-QuotedResults $out)
    }
}

function Invoke-JavaKhSource {
    param([string]$PdFile)
    $root = (Resolve-Path $JavaSourceDir).Path
    Build-JavaKhV2 $root
    $buildDir = Join-Path $root "build"
    $cp = Join-ClassPath @(
        $buildDir,
        (Join-Path $root "jars\log4j-1.2.12.jar"),
        (Join-Path $root "jars\junit-4.12.jar"),
        (Join-Path $root "jars\commons-logging-1.1.jar"),
        (Join-Path $root "jars\commons-io-1.2.jar"),
        (Join-Path $root "jars\commons-cli-1.0.jar")
    )
    $out = Join-Path $OutDir "javakh-v2-source.out"
    $err = Join-Path $OutDir "javakh-v2-source.err"
    $run = Invoke-CapturedProcess -FileName "java" -Arguments @("-Xmx4g", "-cp", $cp, "org.katlas.JavaKh.JavaKh", "-Z") -WorkingDirectory $root -StdInFile $PdFile -OutFile $out -ErrFile $err
    return [pscustomobject]@{
        Name = "javakh-v2-source"
        Seconds = $run.Seconds
        ExitCode = $run.ExitCode
        Out = $out
        Err = $err
        Results = @(Get-QuotedResults $out)
    }
}

function Invoke-JavaKhLocal {
    param([string]$PdFile)
    $root = (Resolve-Path $LocalJavaRoot).Path
    $cp = Join-ClassPath @(
        $root,
        (Join-Path $root "jars\log4j-1.2.12.jar"),
        (Join-Path $root "jars\commons-io-1.2.jar"),
        (Join-Path $root "jars\commons-cli-1.0.jar"),
        (Join-Path $root "jars\commons-logging-1.1.jar")
    )
    $work = Join-Path $OutDir "local-java-work"
    New-Item -ItemType Directory -Force $work | Out-Null
    Copy-Item -Force $PdFile (Join-Path $work "PD.txt")
    $out = Join-Path $OutDir "javakh-local.out"
    $err = Join-Path $OutDir "javakh-local.err"
    Push-Location $work
    try {
        $elapsed = Measure-Command {
            & java -Xmx4g -cp $cp org.katlas.JavaKh.JavaKh > $out 2> $err
        }
        $exit = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    return [pscustomobject]@{
        Name = "javakh-local"
        Seconds = $elapsed.TotalSeconds
        ExitCode = $exit
        Out = $out
        Err = $err
        Results = @(Get-QuotedResults $out)
    }
}

function Compare-Results {
    param(
        [string[]]$Expected,
        [string[]]$Actual,
        [string[]]$Labels,
        [string]$ActualName
    )
    $max = [Math]::Max($Expected.Count, $Actual.Count)
    $mismatches = New-Object System.Collections.Generic.List[string]
    for ($i = 0; $i -lt $max; $i++) {
        $e = if ($i -lt $Expected.Count) { $Expected[$i] } else { "<missing>" }
        $a = if ($i -lt $Actual.Count) { $Actual[$i] } else { "<missing>" }
        if ($e -ne $a) {
            $label = if ($i -lt $Labels.Count) { $Labels[$i] } else { "#$($i + 1)" }
            $mismatches.Add(("{0}: expected [{1}] but {2} produced [{3}]" -f $label, $e, $ActualName, $a)) | Out-Null
            if ($mismatches.Count -ge 20) { break }
        }
    }
    return @($mismatches)
}

$pdFile = Join-Path $OutDir "converted.pd"
$labelsFile = Join-Path $OutDir "labels.txt"
$count = 0
$prepElapsed = Measure-Command {
    $script:preparedCount = Convert-TestPdCode -Path $InputFile -PdOut $pdFile -LabelsOut $labelsFile -MaxItems $Limit
}
$count = $script:preparedCount
$labels = @([IO.File]::ReadAllLines($labelsFile))

Write-Host ("Converted {0} PD codes to {1} in {2:N3}s" -f $count, $pdFile, $prepElapsed.TotalSeconds)
if ($NoExternalSimplify) {
    Write-Host "External PD simplification: disabled"
} else {
    Write-Host "External PD simplification: pd_code_de_r1.de_r1 -> pd_code_delete_nugatory.erase_all_nugatory"
}
Write-Host "Running cppkh..."
$cpp = Invoke-Cpp $pdFile
Write-Host ("cppkh: {0:N3}s, exit={1}, results={2}" -f $cpp.Seconds, $cpp.ExitCode, $cpp.Results.Count)

$javaRuns = @()
if ($JavaMode -eq "source" -or $JavaMode -eq "both") {
    Write-Host "Running JavaKh-v2 source..."
    $javaRuns += Invoke-JavaKhSource $pdFile
}
if ($JavaMode -eq "local" -or $JavaMode -eq "both") {
    Write-Host "Running local JavaKh..."
    $javaRuns += Invoke-JavaKhLocal $pdFile
}

$summaryLines = New-Object System.Collections.Generic.List[string]
$summaryLines.Add("Input: $InputFile") | Out-Null
$summaryLines.Add("Items: $count") | Out-Null
$summaryLines.Add(("prepare_pdcode: {0:N6}s external_simplify={1}" -f $prepElapsed.TotalSeconds, (-not $NoExternalSimplify))) | Out-Null
$summaryLines.Add(("cppkh: {0:N6}s exit={1} results={2}" -f $cpp.Seconds, $cpp.ExitCode, $cpp.Results.Count)) | Out-Null

foreach ($java in $javaRuns) {
    $mismatches = @(Compare-Results -Expected $java.Results -Actual $cpp.Results -Labels $labels -ActualName "cppkh")
    $speedup = if ($cpp.Seconds -gt 0) { $java.Seconds / $cpp.Seconds } else { 0 }
    $pipelineSpeedup = if ($cpp.Seconds -gt 0) { ($java.Seconds + $prepElapsed.TotalSeconds) / $cpp.Seconds } else { 0 }
    $status = if ($mismatches.Count -eq 0 -and $java.Results.Count -eq $cpp.Results.Count) { "OK" } else { "MISMATCH" }

    $summaryLines.Add(("{0}: {1:N6}s exit={2} results={3}" -f $java.Name, $java.Seconds, $java.ExitCode, $java.Results.Count)) | Out-Null
    $summaryLines.Add(("cppkh speedup vs {0}: {1:N3}x" -f $java.Name, $speedup)) | Out-Null
    $summaryLines.Add(("cppkh speedup vs {0}+prepare: {1:N3}x" -f $java.Name, $pipelineSpeedup)) | Out-Null
    $summaryLines.Add(("compare vs {0}: {1}" -f $java.Name, $status)) | Out-Null
    if ($mismatches.Count -gt 0) {
        $mismatchFile = Join-Path $OutDir ("mismatch-{0}.txt" -f $java.Name)
        [IO.File]::WriteAllLines($mismatchFile, $mismatches)
        $summaryLines.Add("first mismatches written to $mismatchFile") | Out-Null
    }

    Write-Host ("{0}: {1:N3}s, exit={2}, results={3}" -f $java.Name, $java.Seconds, $java.ExitCode, $java.Results.Count)
    Write-Host ("cppkh speedup vs {0}: {1:N3}x; vs {0}+prepare: {2:N3}x; compare={3}" -f $java.Name, $speedup, $pipelineSpeedup, $status)
}

$summaryPath = Join-Path $OutDir "summary.txt"
[IO.File]::WriteAllLines($summaryPath, $summaryLines)
Write-Host "Summary written to $summaryPath"
