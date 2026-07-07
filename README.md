# cppkh

`cppkh` is a standalone C++14 port of the integer JavaKh Khovanov homology
computation path. It has no mandatory third-party runtime dependency and does
not require Java or a fixed `PD.txt` file.

## Quick Start

Build the fastest executable that the current machine can support:

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

Run one PD code:

```bat
dist\windows\javakh_cpp.exe --pd-code "PD[X[1,5,2,4],X[3,1,4,6],X[5,3,6,2]]"
```

On Linux the default output is `dist/linux/javakh_cpp`; on macOS it is
`dist/macos/javakh_cpp`.

Run a file or directory:

```bat
dist\windows\javakh_cpp.exe --pd-file path\to\codes.txt
dist\windows\javakh_cpp.exe --pd-dir path\to\pdcode_directory
```

R1-move removal and then nugatory-crossing removal are enabled by default.

## Shared Library

Build a shared library instead of an executable:

```bat
package.bat --shared --name cppkh
```

```sh
sh package.sh --shared --name cppkh
```

This produces `cppkh.dll`, `libcppkh.so`, or `libcppkh.dylib`, depending on the
platform. Any non-system runtime libraries found by the package script are
copied beside it.

## Documentation

- [Build and packaging options](docs/BUILD_AND_PACKAGING.md)
- [Command-line options](docs/CLI_OPTIONS.md)
- [Python ctypes interface](docs/PYTHON_CTYPES.md)
- [Testing against JavaKh](docs/TEST.md)
- [Benchmark results](docs/BENCHMARKS.md)

## References

- Knot Atlas: [Planar Diagrams](https://katlas.org/wiki/Planar_Diagrams)
- Knot Atlas: [Khovanov Homology](https://katlas.org/wiki/Khovanov_Homology)
