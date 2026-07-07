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

## Performance Snapshot

On the full 8397-case benchmark, `cppkh` matched every bundled JavaKh result and
finished in `62.971s` versus `467.016s` for the patched bundled JavaKh native
multiline runner. That is a `7.416x` full-run speedup, or `7.499 ms/PD` for
`cppkh` versus `55.617 ms/PD` for JavaKh.

Peak RSS on the same prepared full input was `25.87 MiB` for `cppkh` and
`483.36 MiB` for patched JavaKh, so the Java process used about `18.69x` more
resident memory in this local run.

![cppkh benchmark runtime and memory chart](docs/assets/benchmark_runtime_memory.png)

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
- [cppkh-interface Python package](docs/PYTHON_PACKAGE.md)
- [Testing against JavaKh](docs/TEST.md)
- [Bundled JavaKh reference](docs/JAVAKH_REFERENCE.md)
- [Benchmark results](docs/BENCHMARKS.md)

## References

- Knot Atlas: [Planar Diagrams](https://katlas.org/wiki/Planar_Diagrams)
- Knot Atlas: [Khovanov Homology](https://katlas.org/wiki/Khovanov_Homology)
