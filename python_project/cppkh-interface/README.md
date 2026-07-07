# cppkh-interface

`cppkh-interface` is a Python package for computing integer Khovanov homology
with the C++ `cppkh` implementation.

The package is compatible with the main `javakh-interface` function:

```python
import cppkh_interface

pd_code = [[1, 5, 2, 4], [3, 1, 4, 6], [5, 3, 6, 2]]
print(cppkh_interface.solve_khovanov(pd_code, de_r1=True, de_k8=True))
```

Unlike wrappers that ship a prebuilt DLL or shared object, this package ships
the `cppkh` C++ source file and compiles a local executable on first use through
`cpp-simple-interface`. The compiled executable is cached for later calls.

## Install

```sh
pip install cppkh-interface
```

A `g++` compatible compiler must be available at runtime. To select a compiler,
set `CXX` before importing or calling the package:

```sh
CXX=clang++ python your_script.py
```

Windows PowerShell:

```powershell
$env:CXX = "C:\path\to\g++.exe"
python your_script.py
```

## Build And Publish

From this directory:

```sh
poetry build
poetry publish
```

For local testing:

```sh
poetry run python -m cppkh_interface "[[1,5,2,4], [3,1,4,6], [5,3,6,2]]"
```
