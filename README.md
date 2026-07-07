# JavaKh C++ Port

This is a standalone C++ port of the integer JavaKh computation path used by
the bundled `org.katlas.JavaKh.JavaKh` classes.

## Build

The project has no mandatory third-party dependency. Threading is selected at
compile time.

### Windows / MinGW

```bat
build.bat win32
```

This uses the Win32 threading API and works with older MinGW builds whose
`std::thread` support is missing. It is the default for `build.bat`.
For performance comparisons with a 64-bit Java VM, use a 64-bit compiler.
The old MinGW.org `mingw32` compiler produces 32-bit code and is much slower.

To install a standalone 64-bit GCC without touching system `PATH`:

```powershell
.\tools\install_winlibs_gcc.ps1
.\package.ps1 -Backend pthread -Static -NoLto -Cxx ..\toolchains\winlibs-x86_64-posix-seh-gcc-16.1.0-mingw-w64ucrt-14.0.0-r3\mingw64\bin\g++.exe -Out dist\win64-gcc16-static
```

The installer writes `..\toolchains\winlibs-gcc64.env.ps1`; dot-source that
file if you want to set `CXX` for the current shell.

Other Windows choices:

```bat
build.bat single
build.bat std
build.bat pthread
build.bat boost
```

`pthread` requires a pthread-enabled MinGW or pthreads-win32. `boost` requires
Boost.Thread and Boost.System libraries.

### Linux / macOS / MSYS2

```sh
./build.sh pthread
```

This is the POSIX default and links with `-pthread`.

Other POSIX choices:

```sh
./build.sh std
./build.sh boost
./build.sh single
```

`std` uses `std::thread` and still links with `-pthread` on POSIX systems.
`boost` links `-lboost_thread -lboost_system -pthread`.

### CMake

```sh
cmake -S . -B build -DKH_THREAD_BACKEND=pthread
cmake --build build --config Release
```

Valid values are `auto`, `pthread`, `std`, `boost`, `win32`, and `single`.
`auto` picks `win32` on Windows and `pthread` elsewhere.

The Windows batch output is `build\javakh_cpp.exe`; POSIX script output is
`build/javakh_cpp`.

## Package

Use the package scripts when you want an optimized single executable in `dist/`.
They require only a usable C++ compiler command, normally `g++`. You can choose
another compiler with `--cxx` or the `CXX` environment variable.

### Windows

```bat
package.bat
package.bat --backend win32 --cxx g++
package.bat --backend pthread --static --no-lto --cxx C:\msys64\mingw64\bin\g++.exe --out dist\win64
```

PowerShell users can use the equivalent script:

```powershell
.\package.ps1 -Backend win32 -Cxx g++
```

The default output is `dist\windows\javakh_cpp.exe`.

### Linux

```sh
sh package.sh
sh package.sh --backend pthread --cxx g++
CXX=/opt/gcc/bin/g++ sh package.sh --backend std
```

The default output is `dist/linux/javakh_cpp`.

### macOS

```sh
sh package.sh --backend pthread --cxx g++
sh package.sh --backend std --cxx clang++
```

The default output is `dist/macos/javakh_cpp`.

### Packaging Options

```text
--backend NAME       auto, pthread, std, boost, win32, single
--cxx COMMAND        compiler command, defaulting to CXX or g++
--out DIR            output directory
--name NAME          executable base name
--static             try static linking where supported
--native             add -march=native when supported (default)
--no-native          disable -march=native for portable binaries
--portable           same as --no-native
--no-lto             disable automatic -flto probing
--no-strip           keep symbols
--extra-cxxflags X   append compiler flags
--extra-ldflags X    append linker flags
```

Defaults are optimized for the machine doing the build: `win32` on Windows,
`pthread` on Linux/macOS, `-O3 -DNDEBUG`, automatic `-flto` when the compiler
accepts it, `-march=native` when supported, and symbol stripping when `strip` is
available. The package scripts also try `-static-libstdc++` and
`-static-libgcc` so MinGW/GCC builds are more likely to be a self-contained
single executable. Use `--portable` when you need to run the executable on older
or different CPUs.

## References

- Knot Atlas: [Planar Diagrams](https://katlas.org/wiki/Planar_Diagrams)
- Knot Atlas: [Khovanov Homology](https://katlas.org/wiki/Khovanov_Homology)

## Usage

Compute one file:

```bat
build\javakh_cpp.exe --pd-file ..\PD.txt
```

Compute one PD code directly:

```bat
build\javakh_cpp.exe --pd-code "PD[X[13,3,14,2],X[7,17,8,16]]"
```

Compute every `.txt` / `.pd` file in a directory:

```bat
build\javakh_cpp.exe --pd-dir ..\samples
```

Each input file should contain one or more lines in standard `PD[...]` form,
for example `PD[X[4,16,5,15],X[5,11,6,10],...]`.

Useful options:

```text
--pd-code CODE   Compute a literal PD[...] string passed on the command line.
--ordered        Keep the crossing order, like JavaKh -O.
--threads N      Accepted for script compatibility; the core algorithm is serial.
--threads auto   Accepted for script compatibility; the core algorithm is serial.
--quiet          Suppress progress messages.
--profile        Print per-PD timing counters to stderr.
--no-simplify-pd Disable the default R1 then nugatory-crossing simplification.
```

R1 move removal and then nugatory-crossing removal are enabled by default.
The order matters: R1 is applied first, then nugatory crossings are erased.
Use `--no-simplify-pd` only when the input has already been simplified.

The runtime threading flag is intentionally capped to one worker. JavaKh's own
`-P` path is experimental and was slower on the benchmark set, and row-level
parallelism in this port was also slower and unstable with shared caches. The
build and package scripts still support multiple thread backends (`pthread`,
`std`, `boost`, `win32`, `single`) so users can compile on different systems.

## Benchmark

The benchmark helper converts `test_pdcode.txt`, applies the external
R1/nugatory simplifiers for JavaKh input, runs cppkh and JavaKh-v2, and compares
quoted homology strings.

```powershell
python -m pip install pd-code-de-r1 pd-code-delete-nugatory
.\tools\benchmark_pdcode.ps1 -CppExe dist\win64-gcc16-static\javakh_cpp.exe -Limit 1000 -Threads 1
```

When external simplification is enabled, the script passes `--no-simplify-pd`
to cppkh so the PD code is simplified exactly once for both programs.

Final local benchmark on Windows, 2026-07-07:

- C++ compiler: WinLibs GCC 16.1.0 x86_64 UCRT POSIX SEH.
- Java VM: Java HotSpot 64-Bit Server VM 21.0.5.
- cppkh executable: `dist\win64-gcc16-static\javakh_cpp.exe`.
- Build command:

```powershell
.\package.ps1 -Backend pthread -Static -NoLto `
  -Cxx ..\toolchains\winlibs-x86_64-posix-seh-gcc-16.1.0-mingw-w64ucrt-14.0.0-r3\mingw64\bin\g++.exe `
  -Out dist\win64-gcc16-static
```

The Java side was fed the same externally simplified PD codes. The comparison
below reports the core JavaKh computation time separately from the Python
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

For the full set, JavaKh-v2 plus external pre-simplification took `53.016s`
(`8.016 ms/code`), while cppkh took `37.980s` (`5.742 ms/code`).

For a single PD input, the quoted homology string is intended to match JavaKh's
integer output byte-for-byte.

When multiple files or multiple PD lines are supplied, each output line is
prefixed with its input label. For a single input, output matches JavaKh's
quoted homology string style.
