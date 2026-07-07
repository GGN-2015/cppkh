# cppkh-interface Python Package

`cppkh-interface` is a Poetry-managed Python package in:

```text
python_project/cppkh-interface/
```

It provides a Python API compatible with the main `javakh-interface` call while
using the C++ `cppkh` implementation.

## Key Design

The package does not ship a prebuilt `.dll`, `.so`, or `.dylib`. Instead, the
wheel and sdist include the C++ source file:

```text
cppkh_interface/data/src/main.cpp
```

On first use, `cppkh-interface` calls `cpp-simple-interface` to compile that
source into a local executable. The executable is cached and reused by later
calls.

## Requirements

- Python 3.10 or newer.
- A `g++` compatible compiler available at runtime.
- Poetry for build and publish commands.

The compiler is selected by `cpp-simple-interface` in this order:

1. `CXX` environment variable.
2. The compiler set by `cpp_simple_interface.set_gpp_filepath(...)`.
3. `g++` on `PATH`.

Windows PowerShell example:

```powershell
$env:CXX = "C:\path\to\g++.exe"
```

Linux / macOS example:

```sh
export CXX=clang++
```

## Build

Use the Poetry installed in your Conda base environment, or any Poetry 2.x
installation:

```sh
cd python_project/cppkh-interface
poetry build
```

This creates source and wheel distributions under:

```text
python_project/cppkh-interface/dist/
```

## Publish

Configure your PyPI token in Poetry, then publish:

```sh
cd python_project/cppkh-interface
poetry publish
```

Or build and publish in one step:

```sh
poetry publish --build
```

## Install

After publishing:

```sh
pip install cppkh-interface
```

For local testing from the package directory:

```sh
poetry install
poetry run python -m cppkh_interface "[[1,5,2,4], [3,1,4,6], [5,3,6,2]]"
```

## API Compatibility

The primary compatibility function mirrors `javakh-interface`:

```python
import cppkh_interface

pd_code = [[1, 5, 2, 4], [3, 1, 4, 6], [5, 3, 6, 2]]
result = cppkh_interface.solve_khovanov(
    pd_code,
    encoding=None,
    de_r1=True,
    de_k8=True,
    show_real_pdcode=False,
)
print(result)
```

Expected output:

```text
q^1*t^0*Z[0] + q^3*t^0*Z[0] + q^5*t^2*Z[0] + q^7*t^3*Z[2] + q^9*t^3*Z[0]
```

The arguments match the `javakh-interface` behavior:

- `pd_code`: a `list[list[int]]`; standard `PD[...]` strings and raw
  `[[...]]` strings are also accepted.
- `encoding`: optional subprocess output encoding.
- `de_r1`: remove R1 moves before computing.
- `de_k8`: remove nugatory crossings after R1 removal.
- `show_real_pdcode`: print the simplified PD code before computing.

## Additional API

`cppkh-interface` also exposes a few C++-oriented helpers:

```python
from cppkh_interface import compute_pd, simplify_pd, compile_cppkh

print(compute_pd("PD[X[1,5,2,4],X[3,1,4,6],X[5,3,6,2]]"))
print(simplify_pd([[1, 5, 2, 4], [3, 1, 4, 6], [5, 3, 6, 2]]))
print(compile_cppkh())
```

`compute_pd(..., threads="auto")` passes `--threads auto` to the compiled
`cppkh` executable.

## Runtime Cache

Compiled executables are cached outside the package directory:

- Windows: `%LOCALAPPDATA%\cppkh-interface`
- macOS: `~/Library/Caches/cppkh-interface`
- Linux: `${XDG_CACHE_HOME:-~/.cache}/cppkh-interface`

Override this location with:

```sh
export CPPKH_INTERFACE_CACHE_DIR=/path/to/cache
```

By default, compilation uses:

```text
-std=c++14 -O3 -DNDEBUG -march=native
```

On Linux and macOS, `-pthread` is also added. If `-march=native` fails, the
package automatically retries without it.

Extra flags can be appended with:

```sh
export CPPKH_INTERFACE_CXXFLAGS="-fno-omit-frame-pointer"
```

Disable `-march=native` with:

```sh
export CPPKH_INTERFACE_NATIVE=0
```

## Syncing The C++ Source

The packaged C++ source is copied from the repository root:

```text
src/main.cpp
```

Before publishing a new Python package after changing the C++ implementation,
refresh the package copy:

```powershell
Copy-Item src\main.cpp python_project\cppkh-interface\cppkh_interface\data\src\main.cpp -Force
```

Linux / macOS:

```sh
cp src/main.cpp python_project/cppkh-interface/cppkh_interface/data/src/main.cpp
```
