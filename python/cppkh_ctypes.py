"""Small ctypes wrapper for the cppkh shared library.

The wrapper expects a library built with package scripts using --shared, or a
CMake build configured with -DCPPKH_BUILD_SHARED=ON. Set CPPKH_LIBRARY or pass
the library path to CppKhLibrary when the file is not beside this module.
"""

from __future__ import annotations

import ctypes
import ast
import os
import pathlib
import re
import sys
from typing import Optional, Sequence, Union


PathLike = Union[str, os.PathLike]
PdInput = Union[str, Sequence[Sequence[int]]]


def _format_pd(crossings: Sequence[Sequence[int]]) -> str:
    parts = []
    for crossing in crossings:
        values = list(crossing)
        if len(values) != 4:
            raise ValueError(f"PD crossing must have four entries: {crossing!r}")
        parts.append("X[{},{},{},{}]".format(*(int(value) for value in values)))
    return "PD[" + ",".join(parts) + "]"


def _parse_x_crossings(text: str) -> Optional[str]:
    pattern = r"X\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\]"
    crossings = []
    for match in re.finditer(pattern, text):
        crossings.append([int(match.group(i)) for i in range(1, 5)])
    if crossings:
        return _format_pd(crossings)
    return None


def normalize_pd_code(pd_code: PdInput) -> str:
    """Normalize accepted Python PD-code inputs into a C++ friendly PD[...] string."""

    if isinstance(pd_code, str):
        body = pd_code.strip()
        if ":" in body:
            body = body.split(":", 1)[1].strip()

        if body.replace(" ", "") == "PD[]":
            return "PD[]"
        if body.startswith("PD["):
            parsed = _parse_x_crossings(body)
            return parsed if parsed is not None else body
        if body.replace(" ", "") == "[]":
            return "PD[]"

        parsed = _parse_x_crossings(body)
        if parsed is not None:
            return parsed

        try:
            value = ast.literal_eval(body)
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"unsupported PD-code string format: {pd_code!r}") from exc
        return _format_pd(value)

    return _format_pd(pd_code)


def normalize_pd_codes(pd_codes: Sequence[PdInput]) -> str:
    """Normalize multiple PD-code inputs into a newline-separated PD document."""

    return "\n".join(normalize_pd_code(pd_code) for pd_code in pd_codes)


def _default_library_names():
    if sys.platform.startswith("win"):
        return ("cppkh.dll", "javakh_cpp.dll")
    if sys.platform == "darwin":
        return ("libcppkh.dylib", "cppkh.dylib", "libjavakh_cpp.dylib")
    return ("libcppkh.so", "cppkh.so", "libjavakh_cpp.so")


def _candidate_paths() -> list[pathlib.Path]:
    env_path = os.environ.get("CPPKH_LIBRARY")
    if env_path:
        return [pathlib.Path(env_path)]

    here = pathlib.Path(__file__).resolve().parent
    roots = [
        here,
        here.parent,
        here.parent / "dist" / "windows",
        here.parent / "dist" / "linux",
        here.parent / "dist" / "macos",
        here.parent / "build",
    ]
    return [root / name for root in roots for name in _default_library_names()]


def find_library() -> pathlib.Path:
    for path in _candidate_paths():
        if path.exists():
            return path
    names = ", ".join(_default_library_names())
    raise FileNotFoundError(
        "Could not find cppkh shared library. Set CPPKH_LIBRARY or place one "
        f"of these files beside this module: {names}"
    )


class CppKhLibrary:
    """Thin Python interface over the cppkh C ABI."""

    def __init__(self, library_path: Optional[PathLike] = None):
        self.path = (pathlib.Path(library_path) if library_path else find_library()).resolve()
        self._dll_directory = None
        self._preloaded_libraries = []
        if os.name == "nt" and hasattr(os, "add_dll_directory"):
            self._dll_directory = os.add_dll_directory(str(self.path.parent))
        elif os.name != "nt":
            self._preload_sibling_libraries()
        mode = getattr(ctypes, "RTLD_GLOBAL", 0)
        self._lib = ctypes.CDLL(str(self.path), mode=mode)
        self._bind_functions()

    def _preload_sibling_libraries(self) -> None:
        siblings = []
        for path in self.path.parent.iterdir():
            if path == self.path or not path.is_file():
                continue
            if path.suffix == ".dylib" or path.suffix == ".so" or ".so." in path.name:
                siblings.append(path)
        pending = sorted(siblings)
        for _ in range(len(pending)):
            progress = False
            remaining = []
            for path in pending:
                try:
                    self._preloaded_libraries.append(
                        ctypes.CDLL(str(path), mode=getattr(ctypes, "RTLD_GLOBAL", 0))
                    )
                    progress = True
                except OSError:
                    remaining.append(path)
            if not progress:
                break
            pending = remaining

    def _bind_functions(self) -> None:
        self._lib.cppkh_version.argtypes = []
        self._lib.cppkh_version.restype = ctypes.c_char_p

        self._lib.cppkh_last_error.argtypes = []
        self._lib.cppkh_last_error.restype = ctypes.c_char_p

        self._lib.cppkh_free.argtypes = [ctypes.c_void_p]
        self._lib.cppkh_free.restype = None

        self._lib.cppkh_compute_pd.argtypes = [ctypes.c_char_p]
        self._lib.cppkh_compute_pd.restype = ctypes.c_void_p

        self._lib.cppkh_compute_pd_ex.argtypes = [
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._lib.cppkh_compute_pd_ex.restype = ctypes.c_void_p

        self._lib.cppkh_compute_pd_batch.argtypes = [ctypes.c_char_p]
        self._lib.cppkh_compute_pd_batch.restype = ctypes.c_void_p

        self._lib.cppkh_compute_pd_batch_ex.argtypes = [
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._lib.cppkh_compute_pd_batch_ex.restype = ctypes.c_void_p

        self._lib.cppkh_simplify_pd.argtypes = [ctypes.c_char_p]
        self._lib.cppkh_simplify_pd.restype = ctypes.c_void_p

    def version(self) -> str:
        value = self._lib.cppkh_version()
        return value.decode("utf-8") if value else ""

    def compute_pd(
        self,
        pd_code: PdInput,
        *,
        simplify_pd: bool = True,
        reorder_crossings: bool = True,
    ) -> str:
        raw = normalize_pd_code(pd_code).encode("utf-8")
        ptr = self._lib.cppkh_compute_pd_ex(
            raw,
            1 if simplify_pd else 0,
            1 if reorder_crossings else 0,
        )
        return self._take_owned_string(ptr)

    def compute_many_pd(
        self,
        pd_codes: Sequence[PdInput],
        *,
        simplify_pd: bool = True,
        reorder_crossings: bool = True,
    ) -> list[str]:
        raw = normalize_pd_codes(pd_codes).encode("utf-8")
        ptr = self._lib.cppkh_compute_pd_batch_ex(
            raw,
            1 if simplify_pd else 0,
            1 if reorder_crossings else 0,
        )
        value = self._take_owned_string(ptr)
        return value.splitlines() if value else []

    def simplify_pd(self, pd_code: PdInput) -> str:
        ptr = self._lib.cppkh_simplify_pd(normalize_pd_code(pd_code).encode("utf-8"))
        return self._take_owned_string(ptr)

    def _take_owned_string(self, ptr: int) -> str:
        if not ptr:
            error = self._lib.cppkh_last_error()
            message = error.decode("utf-8") if error else "cppkh failed"
            raise RuntimeError(message)
        try:
            return ctypes.cast(ptr, ctypes.c_char_p).value.decode("utf-8")
        finally:
            self._lib.cppkh_free(ptr)


def compute_pd(pd_code: PdInput, library_path: Optional[PathLike] = None) -> str:
    return CppKhLibrary(library_path).compute_pd(pd_code)


def compute_many_pd(pd_codes: Sequence[PdInput], library_path: Optional[PathLike] = None) -> list[str]:
    return CppKhLibrary(library_path).compute_many_pd(pd_codes)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python cppkh_ctypes.py <library> <PD[...] code>", file=sys.stderr)
        raise SystemExit(2)
    kh = CppKhLibrary(sys.argv[1])
    print(kh.compute_pd(sys.argv[2]))
