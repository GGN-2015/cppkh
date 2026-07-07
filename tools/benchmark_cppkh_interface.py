#!/usr/bin/env python3
"""Benchmark cppkh-interface against prepared cppkh outputs."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional, Sequence

import cpp_simple_interface
import cppkh_interface

try:
    import psutil
except ImportError:  # pragma: no cover - benchmark helper dependency.
    psutil = None


REPO_ROOT = Path(__file__).resolve().parents[1]


def read_pd_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_quoted_results(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return re.findall(r'"([^"]*)"', text)


def select_slice(values: list[str], start: int, limit: int, last: int) -> list[str]:
    if last > 0:
        return values[-last:]
    offset = max(0, start - 1)
    values = values[offset:]
    if limit > 0:
        values = values[:limit]
    return values


class PeakSampler:
    def __init__(self, root_pid: int, interval_sec: float):
        self.root_pid = root_pid
        self.interval_sec = interval_sec
        self.peak_rss = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._stop.set()
        self._thread.join()
        self._sample()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._sample()
            time.sleep(self.interval_sec)

    def _sample(self) -> None:
        if psutil is None:
            return
        try:
            root = psutil.Process(self.root_pid)
            processes = [root] + root.children(recursive=True)
        except psutil.Error:
            return
        total = 0
        for proc in processes:
            try:
                total += proc.memory_info().rss
            except psutil.Error:
                pass
        self.peak_rss = max(self.peak_rss, total)


def timed_with_peak(fn: Callable[[], tuple[int, list[str]]], interval_sec: float) -> dict:
    start = time.perf_counter()
    if psutil is None:
        exit_code, results = fn()
        peak = None
    else:
        with PeakSampler(os.getpid(), interval_sec) as sampler:
            exit_code, results = fn()
        peak = sampler.peak_rss
    return {
        "seconds": time.perf_counter() - start,
        "exit_code": exit_code,
        "results": results,
        "peak_rss_bytes": peak,
        "peak_rss_mib": None if peak is None else peak / (1024 * 1024),
    }


def run_api(lines: Sequence[str]) -> tuple[int, list[str]]:
    results = []
    for line in lines:
        results.append(cppkh_interface.solve_khovanov(line, de_r1=False, de_k8=False))
    return 0, results


def compiler_parts(command: str) -> list[str]:
    command = command.strip()
    if not command:
        return []
    unquoted = command
    if len(unquoted) >= 2 and unquoted[0] == unquoted[-1] and unquoted[0] in ("'", '"'):
        unquoted = unquoted[1:-1]
    if Path(unquoted).exists() or not any(char.isspace() for char in unquoted):
        return [unquoted]
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return []


def compiler_dumpmachine(command: str) -> str:
    parts = compiler_parts(command)
    if not parts:
        return ""
    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if platform.system() == "Windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run([*parts, "-dumpmachine"], timeout=10, **kwargs)
    except Exception:
        return ""
    return (result.stdout or result.stderr or "").strip().lower()


def is_64bit_compiler(command: str) -> bool:
    machine = compiler_dumpmachine(command)
    return any(token in machine for token in ("x86_64", "amd64", "aarch64", "arm64"))


def where_commands(name: str) -> list[str]:
    command = ["where.exe", name] if platform.system() == "Windows" else ["which", "-a", name]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False)
    except Exception:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def benchmark_compiler_candidates() -> list[str]:
    candidates = []
    for env_name in ("CPPKH_BENCHMARK_CXX", "CPPKH_INTERFACE_CXX", "CXX"):
        value = os.environ.get(env_name, "").strip()
        if value:
            candidates.append(value)

    if platform.system() == "Windows":
        search_roots = [
            REPO_ROOT.parent / "toolchains",
            Path("C:/msys64"),
            Path("C:/mingw64"),
            Path.home() / "scoop",
        ]
        for root in search_roots:
            if root.exists():
                candidates.extend(str(path) for path in root.rglob("g++.exe"))
    candidates.extend(where_commands("g++"))
    candidates.extend(["g++", "clang++", "c++"])

    seen = set()
    unique = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def select_benchmark_compiler() -> str:
    candidates = benchmark_compiler_candidates()
    for candidate in candidates:
        if is_64bit_compiler(candidate):
            cpp_simple_interface.set_gpp_filepath(candidate)
            return candidate
    for candidate in candidates:
        try:
            cpp_simple_interface.set_gpp_filepath(candidate)
            return candidate
        except Exception:
            continue
    return cpp_simple_interface.get_gpp_filepath()


def compiler_runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    compiler = cpp_simple_interface.get_gpp_filepath().strip()
    candidates = [compiler]
    if len(compiler) >= 2 and compiler[0] == compiler[-1] and compiler[0] in ("'", '"'):
        candidates.append(compiler[1:-1])
    runtime_paths = []
    for candidate in candidates:
        path = Path(candidate)
        if path.exists() and path.is_file():
            parent = str(path.resolve().parent)
            if parent not in runtime_paths:
                runtime_paths.append(parent)
    if runtime_paths:
        env["PATH"] = os.pathsep.join(runtime_paths + [env.get("PATH", "")])
    return env


def run_cached_exe(lines: Sequence[str], threads: str) -> tuple[int, list[str]]:
    exe = cppkh_interface.get_cppkh_executable()
    with tempfile.NamedTemporaryFile("w", suffix=".pd", encoding="utf-8", delete=False) as handle:
        handle.write("\n".join(lines))
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
    try:
        proc = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            env=compiler_runtime_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    finally:
        try:
            os.unlink(pd_file)
        except OSError:
            pass
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
    return proc.returncode, re.findall(r'"([^"]*)"', proc.stdout)


def run_batch_api(lines: Sequence[str], threads: str) -> tuple[int, list[str]]:
    try:
        return 0, cppkh_interface.compute_many_pd(lines, de_r1=False, de_k8=False, threads=threads)
    except Exception as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1, []


def compare(actual: Sequence[str], expected: Sequence[str]) -> tuple[bool, int]:
    mismatches = 0
    total = max(len(actual), len(expected))
    for index in range(total):
        left = actual[index] if index < len(actual) else "<missing>"
        right = expected[index] if index < len(expected) else "<missing>"
        if left != right:
            mismatches += 1
    return mismatches == 0, mismatches


def add_comparison(run: dict, expected: Sequence[str]) -> dict:
    ok, mismatches = compare(run["results"], expected)
    return {
        "seconds": run["seconds"],
        "exit_code": run["exit_code"],
        "result_count": len(run["results"]),
        "peak_rss_mib": run["peak_rss_mib"],
        "match": ok,
        "mismatches": mismatches,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-pd", default=str(REPO_ROOT / "benchmark" / "run-test-full8397" / "prepared.pd"))
    parser.add_argument("--expected-out", default=str(REPO_ROOT / "benchmark" / "run-test-full8397" / "cppkh.out"))
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--last", type=int, default=0)
    parser.add_argument("--threads", default="1")
    parser.add_argument("--interval-sec", type=float, default=0.02)
    parser.add_argument("--include-per-item-api", action="store_true")
    parser.add_argument("--skip-batch-api", action="store_true")
    parser.add_argument("--skip-cached-exe", action="store_true")
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pd_lines = select_slice(read_pd_lines(Path(args.prepared_pd)), args.start, args.limit, args.last)
    expected = select_slice(parse_quoted_results(Path(args.expected_out)), args.start, args.limit, args.last)
    selected_compiler = select_benchmark_compiler()
    output = {
        "prepared_pd": str(Path(args.prepared_pd).resolve()),
        "items": len(pd_lines),
        "start": args.start,
        "limit": args.limit,
        "last": args.last,
        "threads": args.threads,
        "compiler": selected_compiler,
        "compiler_machine": compiler_dumpmachine(cpp_simple_interface.get_gpp_filepath()),
        "psutil_available": psutil is not None,
        "cppkh_interface_executable": str(cppkh_interface.get_cppkh_executable()),
    }

    if args.include_per_item_api:
        api_run = timed_with_peak(lambda: run_api(pd_lines), args.interval_sec)
        output["cppkh_interface_per_item_api"] = add_comparison(api_run, expected)

    if not args.skip_batch_api:
        batch_run = timed_with_peak(lambda: run_batch_api(pd_lines, args.threads), args.interval_sec)
        output["cppkh_interface_batch_api"] = add_comparison(batch_run, expected)

    if not args.skip_cached_exe:
        exe_run = timed_with_peak(lambda: run_cached_exe(pd_lines, args.threads), args.interval_sec)
        output["cppkh_interface_cached_exe"] = add_comparison(exe_run, expected)

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))

    for key in ("cppkh_interface_per_item_api", "cppkh_interface_batch_api", "cppkh_interface_cached_exe"):
        if key in output and (output[key]["exit_code"] != 0 or not output[key]["match"]):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
