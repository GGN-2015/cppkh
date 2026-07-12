#!/usr/bin/env python3
"""Cross-platform build and packaging script for cppkh."""

from __future__ import annotations

import argparse
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parent
SOURCE = REPO_ROOT / "src" / "main.cpp"


def host_platform() -> tuple[str, str, str]:
    if sys.platform.startswith("win"):
        return "windows", ".exe", ".dll"
    if sys.platform == "darwin":
        return "macos", "", ".dylib"
    if sys.platform.startswith("linux"):
        return "linux", "", ".so"
    return sys.platform.lower(), "", ".so"


PLATFORM_ID, EXE_EXT, SHARED_EXT = host_platform()


def split_words(value: str) -> list[str]:
    if not value or not value.strip():
        return []
    return shlex.split(value, posix=os.name != "nt")


def command_parts(command: str | Path) -> list[str]:
    text = str(command)
    if Path(text).exists():
        return [text]
    parts = split_words(text)
    return parts if parts else [text]


def run_quiet(command: list[str], cwd: Path | None = None) -> bool:
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False
    return proc.returncode == 0


class Builder:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.tmp = tempfile.TemporaryDirectory(prefix="cppkh_build_")
        self.tmpdir = Path(self.tmp.name)
        self.compiler = self.resolve_compiler()
        self.backend = self.resolve_backend()

    def close(self) -> None:
        self.tmp.cleanup()

    def test_compile(
        self,
        flags: Iterable[str] = (),
        source: str = "int main(){return 0;}\n",
        post_flags: Iterable[str] = (),
    ) -> bool:
        src = self.tmpdir / "test.cpp"
        out = self.tmpdir / ("test" + EXE_EXT)
        src.write_text(source, encoding="ascii")
        command = self.compiler + ["-std=c++14", *flags, str(src), "-o", str(out), *post_flags]
        return run_quiet(command)

    def flag_supported(self, flag: str) -> bool:
        return self.test_compile([flag])

    def compiler_usable(self, candidate: str | Path) -> bool:
        compiler = command_parts(candidate)
        if not run_quiet(compiler + ["--version"]):
            return False
        old = getattr(self, "compiler", None)
        self.compiler = compiler
        try:
            return self.test_compile()
        finally:
            if old is not None:
                self.compiler = old

    def resolve_compiler(self) -> list[str]:
        explicit = self.args.cxx or os.environ.get("CXX", "")
        if explicit:
            if self.compiler_usable(explicit):
                return command_parts(explicit)
            raise SystemExit(f"C++ compiler '{explicit}' is not usable.")

        candidates: list[str] = []
        toolchain_root = REPO_ROOT.parent / "toolchains"
        if toolchain_root.exists():
            candidates.extend(
                str(path)
                for path in sorted(
                    toolchain_root.glob("winlibs-*/mingw64/bin/g++.exe"),
                    reverse=True,
                )
            )
        for name in ("g++", "clang++", "c++", "g++.exe", "clang++.exe", "c++.exe"):
            found = shutil.which(name)
            if found and found not in candidates:
                candidates.append(found)

        for candidate in candidates:
            if self.compiler_usable(candidate):
                return command_parts(candidate)
        raise SystemExit("No usable C++14 compiler found. Install g++ or pass --cxx <compiler>.")

    def backend_supported(self, backend: str) -> bool:
        if backend == "pthread":
            return self.test_compile(
                ["-DKH_THREAD_BACKEND_PTHREAD"],
                "#include <pthread.h>\nint main(){pthread_t t; (void)t; return 0;}\n",
                ["-pthread"],
            )
        if backend == "std":
            post = [] if PLATFORM_ID == "windows" else ["-pthread"]
            return self.test_compile(
                ["-DKH_THREAD_BACKEND_STD"],
                "#include <thread>\nint main(){return 0;}\n",
                post,
            )
        if backend == "boost":
            post = ["-lboost_thread", "-lboost_system"]
            if PLATFORM_ID != "windows":
                post.append("-pthread")
            return self.test_compile(
                ["-DKH_THREAD_BACKEND_BOOST"],
                "#include <boost/thread.hpp>\nint main(){return 0;}\n",
                post,
            )
        if backend == "win32":
            return self.test_compile(
                ["-DKH_THREAD_BACKEND_WIN32"],
                "#include <windows.h>\n"
                "int main(){CRITICAL_SECTION cs; InitializeCriticalSection(&cs); "
                "DeleteCriticalSection(&cs); return 0;}\n",
            )
        if backend == "single":
            return self.test_compile(["-DKH_THREAD_BACKEND_SINGLE"])
        return False

    def resolve_backend(self) -> str:
        if self.args.backend != "auto":
            if self.backend_supported(self.args.backend):
                return self.args.backend
            raise SystemExit(
                f"Requested backend '{self.args.backend}' is not supported by compiler '{self.compiler_display}'."
            )

        if PLATFORM_ID == "windows":
            order = ["win32", "pthread", "std", "single"] if self.args.shared else ["pthread", "win32", "std", "single"]
        else:
            order = ["pthread", "std", "single"]
        for backend in order:
            if self.backend_supported(backend):
                return backend
        raise SystemExit(f"No supported thread backend found for compiler '{self.compiler_display}'.")

    @property
    def compiler_display(self) -> str:
        return " ".join(self.compiler)

    def output_path(self) -> Path:
        out_dir = Path(self.args.out) if self.args.out else REPO_ROOT / "dist" / PLATFORM_ID
        out_dir.mkdir(parents=True, exist_ok=True)
        if self.args.shared:
            stem = self.args.name
            if PLATFORM_ID != "windows" and not stem.startswith("lib"):
                stem = "lib" + stem
            return out_dir / (stem + SHARED_EXT)
        return out_dir / (self.args.name + EXE_EXT)

    def compile_flags(self) -> tuple[list[str], list[str], list[str]]:
        cxxflags = ["-std=c++14", "-O3", "-DNDEBUG", "-Isrc"]
        ldflags: list[str] = []
        libs: list[str] = []

        if self.args.shared:
            cxxflags.append("-DCPPKH_SHARED_LIBRARY")
            if PLATFORM_ID != "windows" and self.flag_supported("-fPIC"):
                cxxflags.append("-fPIC")
            ldflags.append("-dynamiclib" if PLATFORM_ID == "macos" else "-shared")

        if self.backend == "pthread":
            cxxflags.append("-DKH_THREAD_BACKEND_PTHREAD")
            libs.append("-pthread")
        elif self.backend == "std":
            cxxflags.append("-DKH_THREAD_BACKEND_STD")
            if PLATFORM_ID != "windows":
                libs.append("-pthread")
        elif self.backend == "boost":
            cxxflags.append("-DKH_THREAD_BACKEND_BOOST")
            libs.extend(["-lboost_thread", "-lboost_system"])
            if PLATFORM_ID != "windows":
                libs.append("-pthread")
        elif self.backend == "win32":
            cxxflags.append("-DKH_THREAD_BACKEND_WIN32")
        elif self.backend == "single":
            cxxflags.append("-DKH_THREAD_BACKEND_SINGLE")
        else:
            raise SystemExit(f"Unknown backend '{self.backend}'.")

        if self.args.lto and self.flag_supported("-flto"):
            cxxflags.append("-flto")
            ldflags.append("-flto")
        if self.args.native and self.flag_supported("-march=native"):
            cxxflags.append("-march=native")
        if self.args.static:
            if self.args.shared:
                print("warning: --static is ignored when --shared is used", file=sys.stderr)
            elif PLATFORM_ID == "macos":
                print("warning: --static is not supported by normal macOS toolchains; ignoring", file=sys.stderr)
            elif self.flag_supported("-static"):
                if self.flag_supported("-static-libstdc++"):
                    ldflags.append("-static-libstdc++")
                if self.flag_supported("-static-libgcc"):
                    ldflags.append("-static-libgcc")
                ldflags.append("-static")
            else:
                print("warning: full static linking is not supported by this compiler", file=sys.stderr)

        cxxflags.extend(split_words(self.args.extra_cxxflags or os.environ.get("CXXFLAGS", "")))
        ldflags.extend(split_words(self.args.extra_ldflags or os.environ.get("LDFLAGS", "")))
        return cxxflags, ldflags, libs

    def find_tool(self, names: Iterable[str]) -> str | None:
        compiler_path = Path(self.compiler[0])
        search_dirs = []
        if compiler_path.exists():
            search_dirs.append(compiler_path.resolve().parent)
        for directory in search_dirs:
            for name in names:
                candidate = directory / name
                if candidate.exists():
                    return str(candidate)
        for name in names:
            found = shutil.which(name)
            if found:
                return found
        return None

    def strip_target(self, target: Path) -> None:
        if self.args.no_strip:
            return
        names = ["strip.exe", "strip"] if PLATFORM_ID == "windows" else ["strip"]
        strip = self.find_tool(names)
        if strip:
            run_quiet([strip, str(target)])

    def list_dependency_specs(self, file_path: Path) -> list[str]:
        if PLATFORM_ID == "windows":
            objdump = self.find_tool(["objdump.exe", "objdump"])
            if not objdump:
                print(f"warning: objdump was not found; cannot scan DLL dependencies for {file_path}", file=sys.stderr)
                return []
            proc = subprocess.run([objdump, "-p", str(file_path)], text=True, capture_output=True, check=False)
            return [match.group(1).strip() for match in re.finditer(r"DLL Name:\s*(.+)", proc.stdout)]
        if PLATFORM_ID == "macos":
            otool = self.find_tool(["otool"])
            if not otool:
                print(f"warning: otool was not found; cannot scan dylib dependencies for {file_path}", file=sys.stderr)
                return []
            proc = subprocess.run([otool, "-L", str(file_path)], text=True, capture_output=True, check=False)
            return [line.split()[0] for line in proc.stdout.splitlines()[1:] if line.split()]
        ldd = self.find_tool(["ldd"])
        if not ldd:
            print(f"warning: ldd was not found; cannot scan shared-library dependencies for {file_path}", file=sys.stderr)
            return []
        proc = subprocess.run([ldd, str(file_path)], text=True, capture_output=True, check=False)
        specs: list[str] = []
        for line in proc.stdout.splitlines():
            match = re.search(r"=>\s*(/[^ ]+)", line)
            if not match:
                match = re.search(r"^\s*(/[^ ]+)", line)
            if match:
                specs.append(match.group(1))
        return specs

    def is_system_dependency(self, spec: str) -> bool:
        name = Path(spec).name.lower()
        if PLATFORM_ID == "windows":
            if name.startswith(("api-ms-", "ext-ms-")):
                return True
            if re.match(
                r"^(kernel32|user32|gdi32|advapi32|shell32|ole32|oleaut32|ntdll|msvcrt|ucrtbase|"
                r"vcruntime.*|ws2_32|secur32|bcrypt|crypt32|rpcrt4|comdlg32|comctl32|shlwapi|"
                r"imm32|winmm|version|normaliz)\.dll$",
                name,
            ):
                return True
            try:
                windir = os.environ.get("WINDIR", "")
                return bool(windir and str(Path(spec).resolve()).lower().startswith(str(Path(windir).resolve()).lower()))
            except OSError:
                return False
        if PLATFORM_ID == "macos":
            return spec.startswith("/System/Library/") or spec.startswith("/usr/lib/") or name == "libsystem.b.dylib"
        return bool(re.match(r"^(linux-vdso|ld-linux|ld-musl|libc\.so|libm\.so|libpthread\.so|librt\.so|libdl\.so)", name))

    def search_dirs(self, target: Path, out_dir: Path) -> list[Path]:
        dirs: list[Path] = [target.parent.resolve(), out_dir.resolve()]
        compiler_path = Path(self.compiler[0])
        if compiler_path.exists():
            dirs.append(compiler_path.resolve().parent)
        for env_name in ("PATH", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
            for item in os.environ.get(env_name, "").split(os.pathsep):
                if item:
                    path = Path(item)
                    if path.exists():
                        dirs.append(path.resolve())
        unique: list[Path] = []
        seen: set[str] = set()
        for directory in dirs:
            key = str(directory).lower() if PLATFORM_ID == "windows" else str(directory)
            if key not in seen:
                seen.add(key)
                unique.append(directory)
        return unique

    def resolve_dependency(self, spec: str, search_dirs: list[Path]) -> Path | None:
        path = Path(spec)
        if path.exists():
            return path.resolve()
        name = path.name
        for directory in search_dirs:
            candidate = directory / name
            if candidate.exists():
                return candidate.resolve()
        return None

    def copy_runtime_dependencies(self, target: Path) -> None:
        if self.args.static and not self.args.shared:
            return
        out_dir = target.parent
        search_dirs = self.search_dirs(target, out_dir)
        queue = [target.resolve()]
        seen: set[str] = set()
        copied = 0

        while queue:
            current = queue.pop(0)
            key = str(current).lower() if PLATFORM_ID == "windows" else str(current)
            if key in seen:
                continue
            seen.add(key)
            for spec in self.list_dependency_specs(current):
                if self.is_system_dependency(spec):
                    continue
                dep = self.resolve_dependency(spec, search_dirs)
                if not dep:
                    print(f"warning: dependency not found: {spec}", file=sys.stderr)
                    continue
                if self.is_system_dependency(str(dep)):
                    continue
                dest = out_dir / dep.name
                if dep.resolve() != dest.resolve():
                    shutil.copy2(dep, dest)
                    copied += 1
                    print(f"Copied runtime dependency: {dest}")
                if dest.exists():
                    queue.append(dest.resolve())
        print(f"Runtime dependency scan complete: copied {copied} file(s).")

    def build(self) -> Path:
        target = self.output_path()
        cxxflags, ldflags, libs = self.compile_flags()
        print(f"Compiler : {self.compiler_display}")
        print(f"Platform : {PLATFORM_ID}")
        print(f"Backend  : {self.backend}")
        print(f"Kind     : {'shared library' if self.args.shared else 'executable'}")
        print(f"Output   : {target}")

        command = self.compiler + cxxflags + [str(SOURCE), "-o", str(target)] + ldflags + libs
        proc = subprocess.run(command, cwd=str(REPO_ROOT), check=False)
        if proc.returncode != 0:
            raise SystemExit(proc.returncode)
        self.strip_target(target)
        self.copy_runtime_dependencies(target)
        print(f"Packaged {'shared library' if self.args.shared else 'executable'}: {target}")
        return target


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["auto", "pthread", "std", "boost", "win32", "single"], default="auto")
    parser.add_argument("--cxx", default="", help="C++ compiler command, defaulting to CXX or auto-detection.")
    parser.add_argument("--out", default="", help="Output directory, defaulting to dist/<platform>.")
    parser.add_argument("--name", default="cppkh", help="Executable or library base name.")
    parser.add_argument("--shared", action="store_true", help="Build a shared library instead of an executable.")
    parser.add_argument("--static", action="store_true", help="Try to link statically where the platform supports it.")
    parser.add_argument("--native", dest="native", action="store_true", default=True, help="Add -march=native when supported.")
    parser.add_argument("--no-native", "--portable", dest="native", action="store_false", help="Disable -march=native.")
    parser.add_argument("--lto", dest="lto", action="store_true", default=True, help="Try -flto when supported.")
    parser.add_argument("--no-lto", dest="lto", action="store_false", help="Disable -flto.")
    parser.add_argument("--no-strip", action="store_true", help="Do not strip symbols.")
    parser.add_argument("--extra-cxxflags", default="", help="Append extra compiler flags.")
    parser.add_argument("--extra-ldflags", default="", help="Append extra linker flags.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    builder = Builder(args)
    try:
        builder.build()
    finally:
        builder.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
