from __future__ import annotations

import argparse
import ast
import hashlib
import os
import pathlib
import platform
import re
import shlex
import subprocess
import sys
import tempfile
from importlib import resources
from typing import Optional, Sequence, Union

import cpp_simple_interface
import pd_code_de_r1
import pd_code_delete_nugatory
import pd_code_sanity


PathLike = Union[str, os.PathLike]
PdInput = Union[str, Sequence[Sequence[int]]]
UNKNOT_RESULT = "q^-1*t^0*Z[0] + q^1*t^0*Z[0]"


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
    if crossings == []:
        return
    if not pd_code_sanity.sanity(crossings):
        raise TypeError("pd_code does not satisfy PD-code sanity checks")


def normalize_pd_code(pd_code: PdInput) -> str:
    """Normalize a supported PD-code value into standard ``PD[X[...],...]`` text."""

    return _format_pd(_as_crossings(pd_code))


def _resource_source_path():
    source = resources.files("cppkh_interface") / "data" / "src" / "main.cpp"
    return resources.as_file(source)


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


def _compiler_runtime_path_entries() -> list[str]:
    compiler = cpp_simple_interface.get_gpp_filepath().strip()
    if not compiler:
        return []

    candidates = []
    unquoted = compiler
    if len(unquoted) >= 2 and unquoted[0] == unquoted[-1] and unquoted[0] in ("'", '"'):
        unquoted = unquoted[1:-1]
    candidates.append(unquoted)

    try:
        candidates.extend(shlex.split(compiler, posix=True))
    except ValueError:
        pass

    paths = []
    for candidate in candidates:
        path = pathlib.Path(candidate)
        if path.exists() and path.is_file():
            parent = str(path.resolve().parent)
            if parent not in paths:
                paths.append(parent)
    return paths


def _cache_key(source_bytes: bytes, flags: Sequence[str]) -> str:
    digest = hashlib.sha256()
    digest.update(source_bytes)
    digest.update("\0".join(flags).encode("utf-8"))
    digest.update(cpp_simple_interface.get_gpp_filepath().encode("utf-8"))
    digest.update(platform.platform().encode("utf-8"))
    return digest.hexdigest()[:20]


def compile_cppkh(
    *,
    force: bool = False,
    cxx: Optional[str] = None,
    extra_flags: Optional[Sequence[str]] = None,
) -> pathlib.Path:
    """Compile the packaged C++ source with cpp-simple-interface and return the executable path."""

    if cxx:
        cpp_simple_interface.set_gpp_filepath(cxx)

    with _resource_source_path() as source:
        source_path = pathlib.Path(source)
        source_bytes = source_path.read_bytes()
        flags = _default_compile_flags()
        if extra_flags:
            flags.extend(str(flag) for flag in extra_flags)

        cache = _cache_dir()
        exe = cache / f"cppkh-{_cache_key(source_bytes, flags)}{_exe_suffix()}"
        if exe.exists() and not force:
            return exe

        tmp_exe = cache / f"{exe.name}.tmp-{os.getpid()}{_exe_suffix()}"
        if tmp_exe.exists():
            tmp_exe.unlink()

        success, message = cpp_simple_interface.compile_cpp_files(
            [str(source_path)],
            str(tmp_exe),
            other_flags=flags,
        )
        if not success and "-march=native" in flags:
            fallback_flags = [flag for flag in flags if flag != "-march=native"]
            success, message = cpp_simple_interface.compile_cpp_files(
                [str(source_path)],
                str(tmp_exe),
                other_flags=fallback_flags,
            )

        if not success:
            raise CppkhInterfaceError(message)
        if not tmp_exe.exists():
            raise CppkhInterfaceError(f"compiled executable was not created: {tmp_exe}")
        os.replace(tmp_exe, exe)
        try:
            exe.chmod(exe.stat().st_mode | 0o755)
        except OSError:
            pass
        return exe


def get_cppkh_executable() -> pathlib.Path:
    """Return the cached executable path, compiling it first when necessary."""

    return compile_cppkh()


def _run_cppkh(
    pd_text: str,
    *,
    encoding: Optional[str] = None,
    threads: Union[str, int] = "1",
    print_simplified_pd: bool = False,
) -> str:
    exe = compile_cppkh()
    with tempfile.NamedTemporaryFile("w", suffix=".pd", encoding="utf-8", delete=False) as handle:
        handle.write(pd_text)
        handle.write("\n")
        pd_file = handle.name

    command = [
        str(exe),
        "--pd-file",
        pd_file,
        "--quiet",
        "--threads",
        str(threads),
        "--no-simplify-pd",
    ]
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
    runtime_paths = _compiler_runtime_path_entries()
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
        return result.stdout.strip()

    matches = re.findall(r'"([^"]*)"', result.stdout)
    if not matches:
        raise CppkhInterfaceError(f"result not found in cppkh output: {result.stdout!r}")
    return matches[-1]


def _prepare_crossings(pd_code: PdInput, de_r1: bool, de_k8: bool) -> list[list[int]]:
    crossings = _as_crossings(pd_code)
    _check_sanity(crossings)
    if de_r1:
        crossings = pd_code_de_r1.de_r1(crossings)
    if de_k8:
        crossings = pd_code_delete_nugatory.erase_all_nugatory(crossings)
    return crossings


def solve_khovanov(
    pd_code: PdInput,
    encoding: Optional[str] = None,
    de_r1: bool = True,
    de_k8: bool = True,
    show_real_pdcode: bool = False,
) -> str:
    """Compute Khovanov homology with a javakh-interface compatible signature."""

    crossings = _prepare_crossings(pd_code, de_r1=de_r1, de_k8=de_k8)
    if show_real_pdcode:
        print(f"Real PD code after de_r1 and de_k8: {crossings}")
    if crossings == []:
        return UNKNOT_RESULT
    return _run_cppkh(_format_pd(crossings), encoding=encoding)


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

    crossings = _prepare_crossings(pd_code, de_r1=de_r1, de_k8=de_k8)
    if show_real_pdcode:
        print(f"Real PD code after de_r1 and de_k8: {crossings}")
    if crossings == []:
        return UNKNOT_RESULT
    return _run_cppkh(_format_pd(crossings), encoding=encoding, threads=threads)


def simplify_pd(pd_code: PdInput, *, de_r1: bool = True, de_k8: bool = True) -> str:
    """Return the normalized PD string after optional R1 and nugatory simplification."""

    return _format_pd(_prepare_crossings(pd_code, de_r1=de_r1, de_k8=de_k8))


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
