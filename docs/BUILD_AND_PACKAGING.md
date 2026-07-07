# Build and Packaging

This project is a single C++14 translation unit with selectable threading
backends. The build scripts can be called with no arguments; they probe the
available compiler and backend choices, then select the fastest supported local
mode.

## Requirements

- A C++14 compiler. `g++` is the default choice.
- On Windows, a 64-bit MinGW-w64 toolchain is recommended.
- Java is not required for building or running `cppkh`.

If Windows does not have a suitable compiler, install the bundled WinLibs GCC
toolchain:

```powershell
.\tools\install_winlibs_gcc.ps1
```

The package scripts automatically search `..\toolchains\winlibs-*` before
falling back to `CXX`, `g++`, `clang++`, or `c++`.

## Fast Executable Packaging

Windows:

```bat
package.bat
```

PowerShell:

```powershell
.\package.ps1
```

Linux / macOS / MSYS2:

```sh
sh package.sh
```

Default outputs:

| Platform | Output |
| --- | --- |
| Windows | `dist\windows\javakh_cpp.exe` |
| Linux | `dist/linux/javakh_cpp` |
| macOS | `dist/macos/javakh_cpp` |

With no arguments, the scripts use `-O3 -DNDEBUG`, enable `-march=native` when
the compiler accepts it, keep LTO disabled by default, and strip the final
binary when a compatible `strip` is available. The default mode keeps dynamic
runtime libraries dynamic, scans the finished binary, and copies any
non-system runtime dependencies it can locate into the output directory.

Use `--portable` when the result must run on CPUs older or different from the
build machine. Use `--static` only when you explicitly want the executable to
try full static linking.

## Shared Library Packaging

Windows:

```bat
package.bat --shared --name cppkh
```

PowerShell:

```powershell
.\package.ps1 -Shared -Name cppkh
```

Linux / macOS / MSYS2:

```sh
sh package.sh --shared --name cppkh
```

Default shared-library outputs:

| Platform | Output |
| --- | --- |
| Windows | `dist\windows\cppkh.dll` |
| Linux | `dist/linux/libcppkh.so` |
| macOS | `dist/macos/libcppkh.dylib` |

Shared-library packaging also runs the dependency scanner. On Windows it uses
`objdump -p` when available; on Linux it uses `ldd`; on macOS it uses
`otool -L`. Non-system dependencies that can be resolved from the compiler
directory or runtime search paths are copied beside `cppkh.dll`,
`libcppkh.so`, or `libcppkh.dylib`. Keep those copied files beside the library
when moving it to another machine.

The shared library exports this C ABI:

```c
const char* cppkh_version(void);
const char* cppkh_last_error(void);
void cppkh_free(char* value);
char* cppkh_compute_pd(const char* pd_code);
char* cppkh_compute_pd_ex(const char* pd_code, int simplify_pd, int reorder_crossings);
char* cppkh_simplify_pd(const char* pd_code);
```

Strings returned by `cppkh_compute_pd`, `cppkh_compute_pd_ex`, and
`cppkh_simplify_pd` are allocated by the library and must be released with
`cppkh_free`.

## Script Options

Windows batch syntax:

```bat
package.bat --backend pthread --static --no-lto --cxx C:\path\to\g++.exe --out dist\win64
```

PowerShell syntax:

```powershell
.\package.ps1 -Backend pthread -Static -NoLto -Cxx C:\path\to\g++.exe -Out dist\win64
```

POSIX syntax:

```sh
sh package.sh --backend pthread --cxx /opt/gcc/bin/g++ --out dist/linux-gcc
```

Common options:

```text
--backend NAME       auto, pthread, std, boost, win32, single
--cxx COMMAND        compiler command, defaulting to CXX or auto-detection
--out DIR            output directory
--name NAME          executable or library base name
--shared             build a shared library instead of an executable
--static             explicitly try static linking for executables
--native             add -march=native when supported (default)
--no-native          disable -march=native
--portable           same as --no-native
--lto                try -flto
--no-lto             keep LTO disabled (default)
--no-strip           keep symbols
--extra-cxxflags X   append compiler flags
--extra-ldflags X    append linker flags
```

Thread backend notes:

- `pthread` is preferred on POSIX and with POSIX MinGW-w64 builds.
- `win32` uses Windows synchronization primitives.
- `std` uses `std::thread` and links with `-pthread` on POSIX.
- `boost` requires Boost.Thread and Boost.System.
- `single` is the fallback serial backend.

On Windows, executable auto-detection probes `pthread` before `win32` because
that was fastest in the benchmark build. Shared-library auto-detection probes
`win32` before `pthread`; any remaining compiler runtime DLLs are copied beside
the produced `cppkh.dll`.

The runtime `--threads` CLI option is accepted for compatibility, but the core
algorithm intentionally runs one PD code serially because row-level parallelism
was slower in the validated benchmark set.

## Development Builds

The lighter build scripts place binaries in `build/`:

```bat
build.bat
```

```sh
sh build.sh
```

These scripts delegate to the package scripts with `--out build --no-strip`.

## CMake

Executable:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DKH_THREAD_BACKEND=pthread
cmake --build build --config Release
```

Executable plus shared library:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DKH_THREAD_BACKEND=pthread -DCPPKH_BUILD_SHARED=ON
cmake --build build --config Release
```

Valid `KH_THREAD_BACKEND` values are `auto`, `pthread`, `std`, `boost`,
`win32`, and `single`.

CMake builds do not run the dependency-copy scanner. Use `package.ps1`,
`package.bat`, or `package.sh` when you want runtime DLL / SO / dylib files
collected beside the produced binary.
