# Benchmarks

The benchmark helper converts `test_pdcode.txt`, applies the external
R1/nugatory simplifiers for JavaKh input, runs `cppkh` and JavaKh-v2, and
compares quoted homology strings.

Install the external simplifiers used for JavaKh comparison:

```powershell
python -m pip install pd-code-de-r1 pd-code-delete-nugatory
```

Run a benchmark:

```powershell
.\tools\benchmark_pdcode.ps1 -CppExe dist\win64-gcc16-static\javakh_cpp.exe -Limit 1000 -Threads 1
```

When external simplification is enabled, the script passes `--no-simplify-pd`
to `cppkh` so each PD code is simplified exactly once for both programs.

## Final Local Benchmark

Machine-local benchmark on Windows, 2026-07-07:

- C++ compiler: WinLibs GCC 16.1.0 x86_64 UCRT POSIX SEH.
- Java VM: Java HotSpot 64-Bit Server VM 21.0.5.
- `cppkh` executable: `dist\win64-gcc16-static\javakh_cpp.exe`.
- Build command:

```powershell
.\package.ps1 -Backend pthread -Static -NoLto `
  -Cxx ..\toolchains\winlibs-x86_64-posix-seh-gcc-16.1.0-mingw-w64ucrt-14.0.0-r3\mingw64\bin\g++.exe `
  -Out dist\win64-gcc16-static
```

This historical benchmark used an explicitly static benchmark executable. The
current package-script default keeps runtime libraries dynamic and copies
resolved non-system dependencies beside the produced executable or shared
library.

The Java side was fed the same externally simplified PD codes. The comparison
reports the core JavaKh computation time separately from Python
pre-simplification time.

| Input set | Items | prepare_pdcode | cppkh | JavaKh-v2 | cppkh speedup | compare |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| First 1000 lines | 1000 | 1.560s | 4.300s | 7.035s | 1.636x | OK |
| Last 1000 lines (`0006791` to `0007790`) | 1000 | 1.676s | 9.912s | 12.047s | 1.215x | OK |
| Full `test_pdcode.txt` | 6614 | 9.787s | 37.980s | 43.229s | 1.138x | OK |

Average milliseconds per PD code, lower is better:

```text
First 1000
cppkh      | ############ 4.300 ms
JavaKh-v2  | #################### 7.035 ms

Last 1000
cppkh      | ################ 9.912 ms
JavaKh-v2  | #################### 12.047 ms

Full 6614
cppkh      | ################## 5.742 ms
JavaKh-v2  | #################### 6.536 ms
```
