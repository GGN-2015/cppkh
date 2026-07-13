# cppkh-interface Python Package

`cppkh-interface` is a Poetry-managed Python package in:

```text
python_project/cppkh-interface/
```

It provides a Python API compatible with the main `javakh-interface` call while
using the C++ `cppkh` implementation.

## Key Design

The package does not ship a prebuilt `.dll`, `.so`, or `.dylib`. Instead, built
wheel and sdist archives include the C++ source file:

```text
cppkh_interface/data/src/main.cpp
```

On first use, `cppkh-interface` uses Python's standard library to invoke a
local C++14 compiler. The executable is cached and reused by later calls. The
installed package has no runtime Python-package dependencies.

The repository checkout does not keep that data-file copy under version
control. During a PEP 517 build, a custom backend copies the canonical source
from:

```text
src/main.cpp
```

into the package data directory, builds the distribution, and then removes the
temporary copy. Editable/development runs fall back to the repository-root
`src/main.cpp` when the package data file is absent.

## Requirements

- Python 3.10 or newer.
- A C++14 compiler available at runtime.
- The `build` frontend and Poetry are needed only by package maintainers.

The compiler is selected in this order:

1. A command passed to `compile_cppkh(cxx=...)` for the current process.
2. `CPPKH_INTERFACE_CXX` environment variable.
3. `CXX` environment variable.
4. `g++`, `clang++`, or `c++` on `PATH`.

Windows PowerShell example:

```powershell
$env:CPPKH_INTERFACE_CXX = "C:\path\to\g++.exe"
```

Linux / macOS example:

```sh
export CPPKH_INTERFACE_CXX=clang++
```

Benchmark scripts in this repository may choose a faster 64-bit compiler for
timing runs, but that compiler selection is intentionally outside the published
Python package.

## Build

Use a PEP 517 frontend so the custom backend embeds the canonical C++ source:

```sh
cd python_project/cppkh-interface
python -m build
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

Do not use `poetry build` or `poetry publish --build`; those commands bypass
the custom PEP 517 backend and omit `src/main.cpp`. Always run
`python -m build`, validate the resulting wheel, and then publish the existing
artifacts with `poetry publish`.

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

All four `de_r1`/`de_k8` combinations are passed directly to the compiled C++
backend. With both values `True`, cppkh performs R1 removal followed by
nugatory-crossing removal. With both values `False`, it computes the raw input.
Nugatory-only mode includes the R1 cleanup required by that algorithm, matching
the historical `pd-code-delete-nugatory` behavior.

Crossing signs use the same directed-edge traversal as SageMath and the bundled
JavaKh patch. Because the package compiles the repository's `src/main.cpp`, no
separate Python sign implementation is involved.

## Batch API

Use `solve_many_khovanov` or `compute_many_pd` to process many PD codes through
one cached cppkh executable invocation:

```python
import cppkh_interface

pd_codes = [
    [[1, 5, 2, 4], [3, 1, 4, 6], [5, 3, 6, 2]],
    "PD[X[1,5,2,4],X[3,1,4,6],X[5,3,6,2]]",
]

results = cppkh_interface.solve_many_khovanov(
    pd_codes,
    de_r1=True,
    de_k8=True,
    threads="1",
)
```

The batch functions accept either a newline-separated PD document string or a
sequence containing supported single PD-code inputs. All four `de_r1`/`de_k8`
combinations stay on the same high-throughput C++ batch path; no Python-side PD
simplifier is involved.

## Additional API

`cppkh-interface` also exposes a few C++-oriented helpers:

```python
from cppkh_interface import compute_pd, compute_many_pd, simplify_pd, compile_cppkh

print(compute_pd("PD[X[1,5,2,4],X[3,1,4,6],X[5,3,6,2]]"))
print(compute_many_pd(["PD[X[1,5,2,4],X[3,1,4,6],X[5,3,6,2]]"] * 10))
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

The cache key includes the C++ source, compiler identity, flags, and platform.
Each process compiles to its own temporary file and atomically publishes the
immutable executable, so concurrent processes do not share a global lock or a
mutable computation cache.

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

## Source Sync During Packaging

No manual source-copy step is required. The package build backend performs the
temporary copy automatically before generating the wheel or sdist and cleans it
afterward. The temporary path is intentionally ignored by Git:

```text
python_project/cppkh-interface/cppkh_interface/data/src/main.cpp
```
