from __future__ import annotations

import argparse
import ast
import contextlib
import ctypes
import hashlib
import os
import pathlib
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
import threading
from importlib import resources
from typing import Optional, Sequence, Union

PdInput = Union[str, Sequence[Sequence[int]]]
PdManyInput = Union[str, Sequence[PdInput]]
_configured_cxx: Optional[str] = None


class CppkhInterfaceError(RuntimeError):
    """Raised when the C++ executable cannot be built or run."""


def _format_pd(crossings: Sequence[Sequence[int]]) -> str:
    parts = []
    for crossing in crossings:
        values = list(crossing)
        if len(values) != 4:
            raise ValueError(f"PD crossing must have four entries: {crossing!r}")
        parts.append("X[{},{},{},{}]".format(*(int(value) for value in values)))
    return "PD[" + ",".join(parts) + "]"


def _parse_x_crossings(text: str) -> Optional[list[list[int]]]:
    pattern = r"X\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\]"
    crossings = []
    for match in re.finditer(pattern, text):
        crossings.append([int(match.group(i)) for i in range(1, 5)])
    return crossings if crossings else None


def _as_crossings(pd_code: PdInput) -> list[list[int]]:
    if isinstance(pd_code, str):
        body = pd_code.strip()
        if ":" in body:
            body = body.split(":", 1)[1].strip()
        if body.replace(" ", "") in ("PD[]", "[]"):
            return []

        parsed = _parse_x_crossings(body)
        if parsed is not None:
            return parsed

        try:
            value = ast.literal_eval(body)
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"unsupported PD-code string format: {pd_code!r}") from exc
    else:
        value = pd_code

    crossings = []
    for crossing in value:
        values = list(crossing)
        if len(values) != 4:
            raise ValueError(f"PD crossing must have four entries: {crossing!r}")
        crossings.append([int(item) for item in values])
    return crossings


def _check_sanity(crossings: list[list[int]]) -> None:
    counts = {}
    for crossing in crossings:
        for label in crossing:
            counts[label] = counts.get(label, 0) + 1
    if any(count != 2 for count in counts.values()):
        raise TypeError("each PD label must occur exactly twice")


def normalize_pd_code(pd_code: PdInput) -> str:
    """Normalize a supported PD-code value into standard ``PD[X[...],...]`` text."""

    return _format_pd(_as_crossings(pd_code))


def normalize_pd_codes(pd_codes: PdManyInput) -> str:
    """Normalize one or more PD codes into a newline-separated PD document."""

    if isinstance(pd_codes, str):
        return pd_codes.strip()
    return "\n".join(normalize_pd_code(pd_code) for pd_code in pd_codes)


@contextlib.contextmanager
def _resource_source_path():
    source = resources.files("cppkh_interface") / "data" / "src" / "main.cpp"
    try:
        with resources.as_file(source) as resource_path:
            if pathlib.Path(resource_path).exists():
                yield pathlib.Path(resource_path)
                return
    except FileNotFoundError:
        pass

    current = pathlib.Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "src" / "main.cpp"
        if candidate.exists():
            yield candidate
            return

    raise CppkhInterfaceError(
        "cppkh C++ source was not found. Installed wheels include it under "
        "cppkh_interface/data/src/main.cpp; editable checkouts use the "
        "repository root src/main.cpp."
    )


def _cache_dir() -> pathlib.Path:
    env_value = os.environ.get("CPPKH_INTERFACE_CACHE_DIR")
    if env_value:
        root = pathlib.Path(env_value)
    elif sys.platform == "win32":
        root = pathlib.Path(os.environ.get("LOCALAPPDATA", pathlib.Path.home())) / "cppkh-interface"
    elif sys.platform == "darwin":
        root = pathlib.Path.home() / "Library" / "Caches" / "cppkh-interface"
    else:
        root = pathlib.Path(os.environ.get("XDG_CACHE_HOME", pathlib.Path.home() / ".cache")) / "cppkh-interface"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _default_compile_flags() -> list[str]:
    flags = ["-std=c++14", "-O3", "-DNDEBUG"]
    native = os.environ.get("CPPKH_INTERFACE_NATIVE", "1").strip().lower()
    if native not in ("0", "false", "no", "off"):
        flags.append("-march=native")
    if platform.system() != "Windows":
        flags.append("-pthread")
    extra = os.environ.get("CPPKH_INTERFACE_CXXFLAGS", "").strip()
    if extra:
        flags.extend(shlex.split(extra))
    return flags


def _exe_suffix() -> str:
    return ".exe" if platform.system() == "Windows" else ""


def _shared_suffix() -> str:
    return ".dll" if platform.system() == "Windows" else (".dylib" if platform.system() == "Darwin" else ".so")


def _compiler_parts(command: str) -> list[str]:
    command = command.strip()
    if not command:
        return []
    unquoted = command
    if len(unquoted) >= 2 and unquoted[0] == unquoted[-1] and unquoted[0] in ("'", '"'):
        unquoted = unquoted[1:-1]
    if pathlib.Path(unquoted).is_file():
        return [unquoted]
    try:
        parts = shlex.split(command, posix=os.name != "nt")
    except ValueError as exc:
        raise CppkhInterfaceError(f"invalid C++ compiler command: {command!r}") from exc
    return [part.strip("\"'") for part in parts if part.strip("\"'")]


def _subprocess_kwargs() -> dict:
    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if platform.system() == "Windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def _probe_compiler(parts: Sequence[str]) -> subprocess.CompletedProcess:
    if not parts:
        raise CppkhInterfaceError("empty C++ compiler command")
    try:
        result = subprocess.run([*parts, "--version"], timeout=15, **_subprocess_kwargs())
    except (OSError, subprocess.SubprocessError) as exc:
        raise CppkhInterfaceError(f"could not run C++ compiler {' '.join(parts)!r}: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise CppkhInterfaceError(detail or f"C++ compiler {' '.join(parts)!r} is not usable")
    return result


def _resolve_compiler(cxx: Optional[str] = None) -> list[str]:
    global _configured_cxx

    explicit = cxx or _configured_cxx
    if not explicit:
        explicit = os.environ.get("CPPKH_INTERFACE_CXX") or os.environ.get("CXX")
    if explicit:
        parts = _compiler_parts(explicit)
        _probe_compiler(parts)
        if cxx:
            _configured_cxx = cxx
        return parts

    errors = []
    for name in ("g++", "clang++", "c++"):
        candidate = shutil.which(name)
        if not candidate:
            continue
        parts = [candidate]
        try:
            _probe_compiler(parts)
            return parts
        except CppkhInterfaceError as exc:
            errors.append(str(exc))
    detail = f" ({'; '.join(errors)})" if errors else ""
    raise CppkhInterfaceError(
        "no usable C++ compiler was found. Install a C++14 compiler or set "
        f"CPPKH_INTERFACE_CXX/CXX to its command{detail}"
    )


def _compiler_runtime_path_entries(compiler: Sequence[str]) -> list[str]:
    paths = []
    for candidate in compiler:
        resolved = shutil.which(candidate) or candidate
        path = pathlib.Path(resolved)
        if path.exists() and path.is_file():
            parent = str(path.resolve().parent)
            if parent not in paths:
                paths.append(parent)
    return paths


def _compiler_identity(compiler: Sequence[str]) -> str:
    result = _probe_compiler(compiler)
    executable = shutil.which(compiler[0]) or compiler[0]
    return "\0".join([str(pathlib.Path(executable).resolve()), *compiler[1:], result.stdout.strip()])


def _cache_key(source_bytes: bytes, flags: Sequence[str], compiler: Sequence[str]) -> str:
    digest = hashlib.sha256()
    digest.update(source_bytes)
    digest.update("\0".join(flags).encode("utf-8"))
    digest.update(_compiler_identity(compiler).encode("utf-8"))
    digest.update(platform.platform().encode("utf-8"))
    return digest.hexdigest()[:20]


def _compile_source(
    compiler: Sequence[str],
    source: pathlib.Path,
    output: pathlib.Path,
    flags: Sequence[str],
) -> subprocess.CompletedProcess:
    command = [*compiler, *flags, str(source), "-o", str(output)]
    try:
        return subprocess.run(command, **_subprocess_kwargs())
    except OSError as exc:
        raise CppkhInterfaceError(f"could not start C++ compiler: {exc}") from exc


def compile_cppkh(
    *,
    force: bool = False,
    cxx: Optional[str] = None,
    extra_flags: Optional[Sequence[str]] = None,
) -> pathlib.Path:
    """Compile the packaged C++ source and return the cached executable path."""

    with _resource_source_path() as source:
        source_path = pathlib.Path(source)
        source_bytes = source_path.read_bytes()
        compiler = _resolve_compiler(cxx)
        flags = _default_compile_flags()
        if extra_flags:
            flags.extend(str(flag) for flag in extra_flags)

        cache = _cache_dir()
        exe = cache / f"cppkh-{_cache_key(source_bytes, flags, compiler)}{_exe_suffix()}"
        if exe.exists() and not force:
            return exe

        tmp_exe = cache / f"{exe.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}{_exe_suffix()}"
        try:
            result = _compile_source(compiler, source_path, tmp_exe, flags)
            if result.returncode != 0 and "-march=native" in flags:
                fallback_flags = [flag for flag in flags if flag != "-march=native"]
                result = _compile_source(compiler, source_path, tmp_exe, fallback_flags)
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "").strip()
                raise CppkhInterfaceError(detail or "C++ compilation failed")
            if not tmp_exe.exists():
                raise CppkhInterfaceError(f"compiled executable was not created: {tmp_exe}")

            if exe.exists() and not force:
                return exe
            try:
                os.replace(tmp_exe, exe)
            except OSError:
                if force or not exe.exists():
                    raise
            try:
                exe.chmod(exe.stat().st_mode | 0o755)
            except OSError:
                pass
            return exe
        finally:
            try:
                tmp_exe.unlink()
            except OSError:
                pass


def compile_cppkh_shared(*, force: bool = False) -> pathlib.Path:
    """Compile and cache the cppkh C API shared library."""
    with _resource_source_path() as source:
        source_path = pathlib.Path(source)
        compiler = _resolve_compiler()
        flags = _default_compile_flags() + ["-shared", "-DCPPKH_SHARED_LIBRARY"]
        cache = _cache_dir()
        library = cache / f"cppkh-{_cache_key(source_path.read_bytes(), flags, compiler)}{_shared_suffix()}"
        if library.exists() and not force:
            return library
        temporary = cache / f"{library.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}{_shared_suffix()}"
        try:
            result = _compile_source(compiler, source_path, temporary, flags)
            if result.returncode != 0 and "-march=native" in flags:
                result = _compile_source(compiler, source_path, temporary, [flag for flag in flags if flag != "-march=native"])
            if result.returncode != 0:
                raise CppkhInterfaceError((result.stderr or result.stdout or "C++ shared compilation failed").strip())
            os.replace(temporary, library)
            return library
        finally:
            try:
                temporary.unlink()
            except OSError:
                pass


_shared_lock = threading.Lock()
_shared_library = None
_dll_directory_handles = []


def _load_shared_library():
    global _shared_library
    if _shared_library is not None:
        return _shared_library
    runtime_paths = _compiler_runtime_path_entries(_resolve_compiler())
    if runtime_paths:
        os.environ["PATH"] = os.pathsep.join(runtime_paths + [os.environ.get("PATH", "")])
    library_path = compile_cppkh_shared()
    if platform.system() == "Windows" and hasattr(os, "add_dll_directory"):
        for directory in [str(library_path.parent), *runtime_paths]:
            _dll_directory_handles.append(os.add_dll_directory(directory))
    library = ctypes.CDLL(str(library_path))
    library.cppkh_compute_pd_signed_variants_ex.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    library.cppkh_compute_pd_signed_variants_ex.restype = ctypes.c_void_p
    library.cppkh_last_error.restype = ctypes.c_char_p
    library.cppkh_free.argtypes = [ctypes.c_void_p]
    _shared_library = library
    return library


def compute_signed_variants(pd_code: PdInput, signs: Sequence[Sequence[int]]) -> list[str]:
    """Compute several explicit crossing-sign variants in one native call."""
    crossings = _as_crossings(pd_code)
    _check_sanity(crossings)
    rows = [list(row) for row in signs]
    if any(len(row) != len(crossings) or any(sign not in (-1, 1) for sign in row) for row in rows):
        raise ValueError("each sign row must contain one +1/-1 value per crossing")
    pd_text = _format_pd(crossings).encode("utf-8")
    signs_text = "\n".join(" ".join(map(str, row)) for row in rows).encode("ascii")
    with _shared_lock:
        library = _load_shared_library()
        pointer = library.cppkh_compute_pd_signed_variants_ex(pd_text, signs_text, 1)
        if not pointer:
            error = library.cppkh_last_error()
            raise CppkhInterfaceError(error.decode("utf-8", "replace") if error else "signed computation failed")
        try:
            result = ctypes.string_at(pointer).decode("utf-8")
        finally:
            library.cppkh_free(pointer)
    return result.splitlines()


def get_cppkh_executable() -> pathlib.Path:
    """Return the cached executable path, compiling it first when necessary."""

    return compile_cppkh()


def _run_cppkh_document(
    pd_text: str,
    *,
    encoding: Optional[str] = None,
    threads: Union[str, int] = "1",
    de_r1: bool = False,
    de_k8: bool = False,
    print_simplified_pd: bool = False,
) -> list[str]:
    exe = compile_cppkh()
    with tempfile.NamedTemporaryFile("w", suffix=".pd", encoding="utf-8", delete=False) as handle:
        handle.write(pd_text)
        if pd_text and not pd_text.endswith("\n"):
            handle.write("\n")
        pd_file = handle.name

    command = [
        str(exe),
        "--pd-file",
        pd_file,
        "--quiet",
        "--threads",
        str(threads),
    ]
    command.append("--simplify-r1" if de_r1 else "--no-simplify-r1")
    command.append("--simplify-nugatory" if de_k8 else "--no-simplify-nugatory")
    if print_simplified_pd:
        command.append("--print-simplified-pd")

    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": encoding or "utf-8",
        "errors": "replace",
    }
    env = os.environ.copy()
    runtime_paths = _compiler_runtime_path_entries(_resolve_compiler())
    if runtime_paths:
        env["PATH"] = os.pathsep.join(runtime_paths + [env.get("PATH", "")])
    kwargs["env"] = env
    if platform.system() == "Windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        result = subprocess.run(command, **kwargs)
    finally:
        try:
            os.unlink(pd_file)
        except OSError:
            pass

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise CppkhInterfaceError(detail or f"cppkh exited with code {result.returncode}")

    if print_simplified_pd:
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return [line.split("\t", 1)[-1] for line in lines]

    matches = re.findall(r'"([^"]*)"', result.stdout)
    if not matches:
        raise CppkhInterfaceError(f"result not found in cppkh output: {result.stdout!r}")
    return matches


def _run_cppkh(
    pd_text: str,
    *,
    encoding: Optional[str] = None,
    threads: Union[str, int] = "1",
    de_r1: bool = False,
    de_k8: bool = False,
    print_simplified_pd: bool = False,
) -> str:
    results = _run_cppkh_document(
        pd_text,
        encoding=encoding,
        threads=threads,
        de_r1=de_r1,
        de_k8=de_k8,
        print_simplified_pd=print_simplified_pd,
    )
    if len(results) != 1:
        raise CppkhInterfaceError(f"expected exactly one result, got {len(results)}")
    return results[0]


def _prepare_many_for_cppkh(pd_codes: PdManyInput) -> str:
    if isinstance(pd_codes, str):
        return pd_codes.strip()
    return "\n".join(normalize_pd_code(pd_code) for pd_code in pd_codes)


def _compute_one(
    pd_code: PdInput,
    *,
    encoding: Optional[str],
    de_r1: bool,
    de_k8: bool,
    show_real_pdcode: bool,
    threads: Union[str, int],
) -> str:
    document = normalize_pd_code(pd_code)
    if show_real_pdcode:
        real_pd = _run_cppkh(
            document,
            encoding=encoding,
            threads=threads,
            de_r1=de_r1,
            de_k8=de_k8,
            print_simplified_pd=True,
        )
        display_pd = real_pd if de_r1 and de_k8 else _as_crossings(real_pd)
        print(f"Real PD code after de_r1 and de_k8: {display_pd}")
    return _run_cppkh(
        document,
        encoding=encoding,
        threads=threads,
        de_r1=de_r1,
        de_k8=de_k8,
    )


def solve_khovanov(
    pd_code: PdInput,
    encoding: Optional[str] = None,
    de_r1: bool = True,
    de_k8: bool = True,
    show_real_pdcode: bool = False,
) -> str:
    """Compute Khovanov homology with a javakh-interface compatible signature."""

    return _compute_one(
        pd_code,
        encoding=encoding,
        de_r1=de_r1,
        de_k8=de_k8,
        show_real_pdcode=show_real_pdcode,
        threads="1",
    )


def solve_many_khovanov(
    pd_codes: PdManyInput,
    encoding: Optional[str] = None,
    de_r1: bool = True,
    de_k8: bool = True,
    show_real_pdcode: bool = False,
    threads: Union[str, int] = "1",
) -> list[str]:
    """Compute many PD codes in one cppkh process.

    With the default ``de_r1=True`` and ``de_k8=True`` settings, the raw PD
    document is passed directly to cppkh and the C++ simplifier handles R1 then
    nugatory crossing removal for the whole batch.
    """

    document = _prepare_many_for_cppkh(pd_codes)
    if not document:
        return []
    if show_real_pdcode:
        simplified = _run_cppkh_document(
            document,
            encoding=encoding,
            threads=threads,
            de_r1=de_r1,
            de_k8=de_k8,
            print_simplified_pd=True,
        )
        print(f"Real PD code after de_r1 and de_k8: {simplified}")
    return _run_cppkh_document(
        document,
        encoding=encoding,
        threads=threads,
        de_r1=de_r1,
        de_k8=de_k8,
    )


def compute_pd(
    pd_code: PdInput,
    *,
    encoding: Optional[str] = None,
    de_r1: bool = True,
    de_k8: bool = True,
    show_real_pdcode: bool = False,
    threads: Union[str, int] = "1",
) -> str:
    """Compute Khovanov homology using the same defaults as solve_khovanov."""

    return _compute_one(
        pd_code,
        encoding=encoding,
        de_r1=de_r1,
        de_k8=de_k8,
        show_real_pdcode=show_real_pdcode,
        threads=threads,
    )


def compute_many_pd(
    pd_codes: PdManyInput,
    *,
    encoding: Optional[str] = None,
    de_r1: bool = True,
    de_k8: bool = True,
    show_real_pdcode: bool = False,
    threads: Union[str, int] = "1",
) -> list[str]:
    """Compute many PD codes in one cached cppkh executable invocation."""

    return solve_many_khovanov(
        pd_codes,
        encoding=encoding,
        de_r1=de_r1,
        de_k8=de_k8,
        show_real_pdcode=show_real_pdcode,
        threads=threads,
    )


def simplify_pd(pd_code: PdInput, *, de_r1: bool = True, de_k8: bool = True) -> str:
    """Return the normalized PD string after optional R1 and nugatory simplification."""

    return _run_cppkh(
        normalize_pd_code(pd_code),
        de_r1=de_r1,
        de_k8=de_k8,
        print_simplified_pd=True,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compute Khovanov homology with cppkh-interface.")
    parser.add_argument("pd_code", help="PD code as PD[...] text or a Python-style list of crossings.")
    parser.add_argument("--no-de-r1", action="store_true", help="Disable R1-move removal.")
    parser.add_argument("--no-de-k8", action="store_true", help="Disable nugatory-crossing removal.")
    parser.add_argument("--threads", default="1", help="cppkh --threads value for direct compute_pd mode.")
    args = parser.parse_args(argv)
    print(
        compute_pd(
            args.pd_code,
            de_r1=not args.no_de_r1,
            de_k8=not args.no_de_k8,
            threads=args.threads,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
