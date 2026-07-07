# Python ctypes Interface

The shared library exposes a small C ABI that can be loaded with Python
`ctypes` on Windows, Linux, and macOS. A ready-to-use wrapper is provided in
`python/cppkh_ctypes.py`.

## Build the Library

Windows:

```bat
package.bat --shared --name cppkh
```

PowerShell:

```powershell
.\package.ps1 -Shared -Name cppkh
```

Linux / macOS:

```sh
sh package.sh --shared --name cppkh
```

Default library names:

| Platform | Library |
| --- | --- |
| Windows | `dist\windows\cppkh.dll` |
| Linux | `dist/linux/libcppkh.so` |
| macOS | `dist/macos/libcppkh.dylib` |

The package scripts scan the finished library and copy non-system runtime
dependencies they can locate into the same directory. Keep those copied files
beside the main library. The Python wrapper adds the library directory to the
Windows DLL search path, and on Linux/macOS it preloads sibling `.so` /
`.dylib` files before loading `libcppkh`.

You can also build the shared target with CMake:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCPPKH_BUILD_SHARED=ON
cmake --build build --config Release
```

## Use the Wrapper

Pass the library path explicitly:

```python
from python.cppkh_ctypes import CppKhLibrary

kh = CppKhLibrary(r"dist\windows\cppkh.dll")
print(kh.compute_pd("PD[X[1,5,2,4],X[3,1,4,6],X[5,3,6,2]]"))
print(kh.compute_pd("[[1,5,2,4], [3,1,4,6], [5,3,6,2]]"))
print(kh.compute_pd([[1, 5, 2, 4], [3, 1, 4, 6], [5, 3, 6, 2]]))
```

On Linux:

```python
from python.cppkh_ctypes import CppKhLibrary

kh = CppKhLibrary("dist/linux/libcppkh.so")
print(kh.compute_pd("PD[X[1,5,2,4],X[3,1,4,6],X[5,3,6,2]]"))
```

On macOS:

```python
from python.cppkh_ctypes import CppKhLibrary

kh = CppKhLibrary("dist/macos/libcppkh.dylib")
print(kh.compute_pd("PD[X[1,5,2,4],X[3,1,4,6],X[5,3,6,2]]"))
```

Or set `CPPKH_LIBRARY` and let the wrapper discover it:

Windows:

```bat
set CPPKH_LIBRARY=%CD%\dist\windows\cppkh.dll
python python\cppkh_ctypes.py "%CPPKH_LIBRARY%" "PD[X[1,5,2,4],X[3,1,4,6],X[5,3,6,2]]"
```

Linux / macOS:

```sh
export CPPKH_LIBRARY="$PWD/dist/linux/libcppkh.so"
python3 python/cppkh_ctypes.py "$CPPKH_LIBRARY" "PD[X[1,5,2,4],X[3,1,4,6],X[5,3,6,2]]"
```

## Python API

```python
from python.cppkh_ctypes import CppKhLibrary, compute_pd, normalize_pd_code

kh = CppKhLibrary("path/to/library")

kh.version()
kh.compute_pd(pd_code)
kh.compute_pd(pd_code, simplify_pd=False, reorder_crossings=True)
kh.simplify_pd(pd_code)

compute_pd(pd_code, "path/to/library")
```

`pd_code` may be any of these Python-side forms:

```python
"PD[X[1,5,2,4],X[3,1,4,6],X[5,3,6,2]]"
"X[1,5,2,4], X[3,1,4,6], X[5,3,6,2]"
"[[1,5,2,4], [3,1,4,6], [5,3,6,2]]"
"0000001.txt: [[2,3,1,4], [3,2,4,1]]"
"[K3a1|[[1,5,2,4], [3,1,4,6], [5,3,6,2]]]"
[[1, 5, 2, 4], [3, 1, 4, 6], [5, 3, 6, 2]]
[]
```

The wrapper normalizes these forms with `normalize_pd_code()` before calling
the C ABI, so the C++ library still receives a standard `PD[...]` string.

`compute_pd` uses the same defaults as the CLI: R1 removal, nugatory-crossing
removal, and crossing reordering are enabled.

`simplify_pd` returns the simplified `PD[...]` string without computing
homology.

Errors from the C++ library are raised as `RuntimeError`.

## Raw C ABI

When writing your own `ctypes` wrapper, use `c_void_p` as the return type for
owned strings so Python does not lose the original pointer before it can be
freed:

```python
import ctypes

lib = ctypes.CDLL("dist/linux/libcppkh.so")
lib.cppkh_compute_pd.argtypes = [ctypes.c_char_p]
lib.cppkh_compute_pd.restype = ctypes.c_void_p
lib.cppkh_last_error.argtypes = []
lib.cppkh_last_error.restype = ctypes.c_char_p
lib.cppkh_free.argtypes = [ctypes.c_void_p]

ptr = lib.cppkh_compute_pd(b"PD[X[1,5,2,4],X[3,1,4,6],X[5,3,6,2]]")
try:
    if not ptr:
        raise RuntimeError(lib.cppkh_last_error().decode("utf-8"))
    value = ctypes.cast(ptr, ctypes.c_char_p).value.decode("utf-8")
finally:
    if ptr:
        lib.cppkh_free(ptr)
```
