# Build and Packaging

`cppkh` is built with a single cross-platform Python entry point:

```sh
python build.py
```

The script compiles `src/main.cpp`, selects a usable C++14 compiler, probes the
available thread backend, packages the output under `dist/<platform>/`, and
copies non-system runtime dependencies beside the produced binary when dynamic
runtime libraries are used.

## Requirements

- Python 3.10 or newer.
- A C++14 compiler. `g++` is the default choice.
- On Windows, a 64-bit MinGW-w64 toolchain is recommended.
- Java is not required for building or running `cppkh`.

If Windows does not have a suitable compiler, install the bundled WinLibs GCC
toolchain:

```powershell
.\tools\install_winlibs_gcc.ps1
```

`build.py` searches `..\toolchains\winlibs-*` before falling back to `CXX`,
`g++`, `clang++`, or `c++`.

## Fast Executable

Build the default executable:

```sh
python build.py
```

Default outputs:

| Platform | Output |
| --- | --- |
| Windows | `dist\windows\cppkh.exe` |
| Linux | `dist/linux/cppkh` |
| macOS | `dist/macos/cppkh` |

With no arguments, `build.py` uses `-O3 -DNDEBUG`, enables `-march=native` and
`-flto` when the compiler accepts them, strips the final binary when a
compatible `strip` is available, scans the finished binary, and copies
resolvable non-system runtime dependencies into the output directory.

Use `--portable` when the result must run on CPUs older or different from the
build machine. Use `--static` only when you explicitly want the executable to
try full static linking.

## Shared Library

Build a shared library:

```sh
python build.py --shared --name cppkh
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
char* cppkh_compute_pd_batch(const char* pd_codes);
char* cppkh_compute_pd_batch_ex(const char* pd_codes, int simplify_pd, int reorder_crossings);
char* cppkh_simplify_pd(const char* pd_code);
```

Strings returned by `cppkh_compute_pd`, `cppkh_compute_pd_ex`,
`cppkh_compute_pd_batch`, `cppkh_compute_pd_batch_ex`, and `cppkh_simplify_pd`
are allocated by the library and must be released with `cppkh_free`.

The batch compute functions accept a text document containing one or more
standard `PD[...]` blocks and return one unquoted homology string per line.

## Options

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
--lto                try -flto (default)
--no-lto             disable LTO
--no-strip           keep symbols
--extra-cxxflags X   append compiler flags
--extra-ldflags X    append linker flags
```

Example with explicit compiler and output directory:

```sh
python build.py --backend pthread --static --no-lto --cxx C:\path\to\g++.exe --out dist\win64
```

Development-style builds can use the same entry point:

```sh
python build.py --out build --no-strip
```

## Thread Backend Notes

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
