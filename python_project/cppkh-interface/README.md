# cppkh-interface

`cppkh-interface` is a Python package for computing integer Khovanov homology
with the C++ `cppkh` implementation.

Version `0.1.3` has no runtime Python-package dependencies. Link crossing signs,
PD validation, R1 removal, and nugatory-crossing removal all use the bundled
canonical `cppkh` C++ source and its SageMath-compatible orientation rules.

The package is compatible with the main `javakh-interface` function:

```python
import cppkh_interface

pd_code = [[1, 5, 2, 4], [3, 1, 4, 6], [5, 3, 6, 2]]
print(cppkh_interface.solve_khovanov(pd_code, de_r1=True, de_k8=True))
print(cppkh_interface.solve_many_khovanov([pd_code, pd_code]))
```

Unlike wrappers that ship a prebuilt DLL or shared object, this package ships
the `cppkh` C++ source file in built distributions and compiles a local
executable on first use using only Python's standard library. The compiled
executable is cached for later calls.

In the repository checkout, the package does not keep a committed backup copy
of the C++ source. The build backend copies `../../src/main.cpp` into the
package data directory only while the PEP 517 build is running, then removes
that temporary copy.

## Install

```sh
pip install cppkh-interface
```

A C++14 compiler must be available at runtime. The package looks at
`CPPKH_INTERFACE_CXX`, then `CXX`, then searches `PATH` for `g++`, `clang++`, or
`c++`. To select a compiler explicitly:

```sh
CPPKH_INTERFACE_CXX=clang++ python your_script.py
```

Windows PowerShell:

```powershell
$env:CPPKH_INTERFACE_CXX = "C:\path\to\g++.exe"
python your_script.py
```

## Build And Publish

From this directory:

```sh
python -m build
poetry publish
```

Do not use `poetry build` or `poetry publish --build`: Poetry's direct builder
bypasses the source-synchronizing PEP 517 backend. Build first with
`python -m build`, inspect/test the wheel, then publish the existing artifacts.

For local testing:

```sh
poetry run python -m cppkh_interface "[[1,5,2,4], [3,1,4,6], [5,3,6,2]]"
```
