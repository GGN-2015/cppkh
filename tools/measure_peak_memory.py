#!/usr/bin/env python3
"""Measure peak RSS for cppkh and bundled JavaKh on a prepared PD file."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Sequence

import psutil


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JAVA_ROOT = REPO_ROOT / "reference" / "javakh"


def java_classpath(java_root: Path) -> str:
    jars = [
        java_root / "jars" / "log4j-1.2.12.jar",
        java_root / "jars" / "commons-io-1.2.jar",
        java_root / "jars" / "commons-cli-1.0.jar",
        java_root / "jars" / "commons-logging-1.1.jar",
    ]
    return os.pathsep.join(str(path) for path in [java_root] + jars)


def process_tree_rss(proc: psutil.Process) -> int:
    total = 0
    processes = [proc]
    try:
        processes.extend(proc.children(recursive=True))
    except psutil.Error:
        pass
    for item in processes:
        try:
            total += item.memory_info().rss
        except psutil.Error:
            pass
    return total


def measure(
    name: str,
    command: Sequence[str],
    cwd: Path,
    interval_sec: float,
    env: dict[str, str] | None = None,
) -> dict:
    started = time.perf_counter()
    proc = subprocess.Popen(
        list(command),
        cwd=str(cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    root = psutil.Process(proc.pid)
    peak_rss = 0
    while proc.poll() is None:
        peak_rss = max(peak_rss, process_tree_rss(root))
        time.sleep(interval_sec)
    peak_rss = max(peak_rss, process_tree_rss(root))
    seconds = time.perf_counter() - started
    return {
        "name": name,
        "seconds": seconds,
        "exit_code": proc.returncode,
        "peak_rss_bytes": peak_rss,
        "peak_rss_mib": peak_rss / (1024 * 1024),
        "command": list(command),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-pd", required=True, help="Already simplified PD file.")
    parser.add_argument("--cpp-exe", required=True, help="Path to javakh_cpp executable.")
    parser.add_argument("--java-root", default=str(DEFAULT_JAVA_ROOT), help="Bundled JavaKh directory.")
    parser.add_argument("--java", default="java", help="Java executable.")
    parser.add_argument("--java-xmx", default="4g", help="Java maximum heap.")
    parser.add_argument("--threads", default="1", help="cppkh --threads value.")
    parser.add_argument("--cppkh-interface-python", default="", help="Python executable with cppkh-interface installed.")
    parser.add_argument("--cppkh-interface-cache-dir", default="", help="Cache directory for cppkh-interface.")
    parser.add_argument("--cppkh-interface-cxx", default="", help="Compiler path used to select the cached cppkh-interface executable.")
    parser.add_argument("--interval-sec", type=float, default=0.05, help="RSS polling interval.")
    parser.add_argument("--out", default="", help="Optional JSON output path.")
    return parser.parse_args()


def cppkh_interface_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    if args.cppkh_interface_cache_dir:
        env["CPPKH_INTERFACE_CACHE_DIR"] = str(Path(args.cppkh_interface_cache_dir).resolve())
    if args.cppkh_interface_cxx:
        compiler = Path(args.cppkh_interface_cxx).resolve()
        env["CXX"] = str(compiler)
        if compiler.exists():
            env["PATH"] = os.pathsep.join([str(compiler.parent), env.get("PATH", "")])
    return env


def cppkh_interface_command(args: argparse.Namespace, prepared_pd: Path) -> list[str]:
    code = (
        "from pathlib import Path; import sys; import cppkh_interface; "
        "path=Path(sys.argv[1]); threads=sys.argv[2]; "
        "lines=[line.strip() for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]; "
        "results=cppkh_interface.compute_many_pd(lines, de_r1=False, de_k8=False, threads=threads); "
        "raise SystemExit(0 if len(results)==len(lines) else 1)"
    )
    return [args.cppkh_interface_python, "-c", code, str(prepared_pd), str(args.threads)]


def main() -> int:
    args = parse_args()
    prepared_pd = Path(args.prepared_pd).resolve()
    cpp_exe = Path(args.cpp_exe).resolve()
    java_root = Path(args.java_root).resolve()

    cpp_command = [
        str(cpp_exe),
        "--pd-file",
        str(prepared_pd),
        "--quiet",
        "--threads",
        str(args.threads),
        "--no-simplify-pd",
    ]
    java_command = [
        args.java,
        f"-Xmx{args.java_xmx}",
        "-cp",
        java_classpath(java_root),
        "org.katlas.JavaKh.JavaKh",
        "-f",
        str(prepared_pd),
    ]

    java_work = REPO_ROOT / "benchmark" / "memory-java-work"
    if java_work.exists():
        shutil.rmtree(java_work)
    java_work.mkdir(parents=True, exist_ok=True)

    result = {
        "prepared_pd": str(prepared_pd),
        "cppkh": measure("cppkh", cpp_command, REPO_ROOT, args.interval_sec),
    }
    if args.cppkh_interface_python:
        result["cppkh_interface"] = measure(
            "cppkh-interface",
            cppkh_interface_command(args, prepared_pd),
            REPO_ROOT,
            args.interval_sec,
            env=cppkh_interface_env(args),
        )
    result["javakh"] = measure("javakh", java_command, java_work, args.interval_sec)
    result["javakh_over_cpp_peak_rss_ratio"] = (
        result["javakh"]["peak_rss_mib"] / result["cppkh"]["peak_rss_mib"]
        if result["cppkh"]["peak_rss_mib"]
        else None
    )
    if "cppkh_interface" in result and result["cppkh_interface"]["peak_rss_mib"]:
        result["javakh_over_cppkh_interface_peak_rss_ratio"] = (
            result["javakh"]["peak_rss_mib"] / result["cppkh_interface"]["peak_rss_mib"]
        )

    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        Path(args.out).resolve().write_text(text + "\n", encoding="utf-8")
    ok = result["cppkh"]["exit_code"] == 0 and result["javakh"]["exit_code"] == 0
    if "cppkh_interface" in result:
        ok = ok and result["cppkh_interface"]["exit_code"] == 0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
