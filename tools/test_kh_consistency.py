#!/usr/bin/env python3
"""Cross-platform cppkh vs bundled JavaKh consistency and timing test."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "tests" / "data" / "test_pdcode.txt"
DEFAULT_LABELS = REPO_ROOT / "tests" / "data" / "test_pdcode.labels.txt"
DEFAULT_JAVA_ROOT = REPO_ROOT / "reference" / "javakh"


def parse_crossings(text: str) -> List[List[int]]:
    body = text.strip()
    if not body:
        raise ValueError("empty PD line")
    if ":" in body:
        body = body.split(":", 1)[1].strip()
    elif "|" in body:
        if body.startswith("[") and body.endswith("]"):
            body = body[1:-1].strip()
        body = body.split("|", 1)[1].strip()

    if body.startswith("PD[") or "X[" in body:
        crossings = []
        pattern = r"X\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\]"
        for match in re.finditer(pattern, body):
            crossings.append([int(match.group(i)) for i in range(1, 5)])
        if crossings or body.replace(" ", "") == "PD[]":
            return crossings

    value = ast.literal_eval(body)
    crossings = []
    for crossing in value:
        if len(crossing) != 4:
            raise ValueError(f"crossing does not have four entries: {crossing!r}")
        crossings.append([int(x) for x in crossing])
    return crossings


def format_pd(crossings: Sequence[Sequence[int]]) -> str:
    return "PD[" + ",".join("X[{},{},{},{}]".format(*crossing) for crossing in crossings) + "]"


def read_lines(path: Path) -> List[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def raw_label(line: str, index: int) -> str:
    if ":" in line:
        return line.split(":", 1)[0].strip()
    if "|" in line:
        body = line[1:-1].strip() if line.startswith("[") and line.endswith("]") else line
        return body.split("|", 1)[0].strip()
    return f"case-{index:06d}"


def selected_items(lines: List[str], labels: List[str], start: int, limit: int, last: int) -> Tuple[List[str], List[str]]:
    if start < 1:
        raise ValueError("--start is 1-based and must be >= 1")
    if last > 0:
        lines = lines[-last:]
        labels = labels[-last:]
    else:
        offset = start - 1
        lines = lines[offset:]
        labels = labels[offset:]
        if limit > 0:
            lines = lines[:limit]
            labels = labels[:limit]
    return lines, labels


def load_labels(input_path: Path, lines: List[str], labels_path: Optional[Path]) -> List[str]:
    if labels_path and labels_path.exists():
        labels = read_lines(labels_path)
        if len(labels) >= len(lines):
            return labels[: len(lines)]
    return [raw_label(line, i + 1) for i, line in enumerate(lines)]


def simplify_crossings(crossings: List[List[int]]) -> List[List[int]]:
    try:
        import pd_code_de_r1
        import pd_code_delete_nugatory
    except ImportError as exc:
        raise RuntimeError(
            "External simplifiers are missing. Install them with:\n"
            "  python -m pip install pd-code-de-r1 pd-code-delete-nugatory\n"
            "or pass --no-external-simplify."
        ) from exc
    crossings = pd_code_de_r1.de_r1(crossings)
    crossings = pd_code_delete_nugatory.erase_all_nugatory(crossings)
    return crossings


def prepare_pd_file(args: argparse.Namespace, out_dir: Path) -> Tuple[Path, Path, int, float]:
    start_time = time.perf_counter()
    input_path = Path(args.input).resolve()
    raw_lines = read_lines(input_path)
    labels_path = Path(args.labels).resolve() if args.labels else None
    labels = load_labels(input_path, raw_lines, labels_path)
    raw_lines, labels = selected_items(raw_lines, labels, args.start, args.limit, args.last)

    pd_lines = []
    prepared_labels = []
    for index, line in enumerate(raw_lines, 1):
        crossings = parse_crossings(line)
        if not args.no_external_simplify:
            crossings = simplify_crossings(crossings)
        pd_lines.append(format_pd(crossings))
        prepared_labels.append(labels[index - 1] if index - 1 < len(labels) else f"case-{index:06d}")

    pd_file = out_dir / "prepared.pd"
    labels_file = out_dir / "labels.txt"
    pd_file.write_text("\n".join(pd_lines) + ("\n" if pd_lines else ""), encoding="utf-8")
    labels_file.write_text("\n".join(prepared_labels) + ("\n" if prepared_labels else ""), encoding="utf-8")
    return pd_file, labels_file, len(pd_lines), time.perf_counter() - start_time


def candidate_cpp_exes() -> List[Path]:
    names = ["cppkh.exe"] if os.name == "nt" else ["cppkh"]
    roots = [
        REPO_ROOT / "dist" / "windows",
        REPO_ROOT / "dist" / "linux",
        REPO_ROOT / "dist" / "macos",
        REPO_ROOT / "dist" / "win64-gcc16-static",
        REPO_ROOT / "build",
        REPO_ROOT,
    ]
    candidates = [root / name for root in roots for name in names]
    candidates.extend(sorted((REPO_ROOT / "dist").glob("**/cppkh.exe")))
    candidates.extend(sorted((REPO_ROOT / "dist").glob("**/cppkh")))
    return candidates


def build_cpp() -> None:
    if os.name == "nt":
        script = REPO_ROOT / "package.bat"
        subprocess.run([str(script)], cwd=str(REPO_ROOT), check=True)
    else:
        script = REPO_ROOT / "package.sh"
        subprocess.run(["sh", str(script)], cwd=str(REPO_ROOT), check=True)


def find_cpp_exe(path_arg: str, build_if_missing: bool) -> Path:
    if path_arg:
        path = Path(path_arg).resolve()
        if not path.exists():
            raise FileNotFoundError(f"cppkh executable not found: {path}")
        return path
    for candidate in candidate_cpp_exes():
        if candidate.exists():
            return candidate.resolve()
    if build_if_missing:
        build_cpp()
        for candidate in candidate_cpp_exes():
            if candidate.exists():
                return candidate.resolve()
    raise FileNotFoundError("cppkh executable was not found. Build first or pass --cpp-exe.")


def java_classpath(java_root: Path) -> str:
    jars = [
        java_root / "jars" / "log4j-1.2.12.jar",
        java_root / "jars" / "commons-io-1.2.jar",
        java_root / "jars" / "commons-cli-1.0.jar",
        java_root / "jars" / "commons-logging-1.1.jar",
    ]
    return os.pathsep.join(str(path) for path in [java_root] + jars)


def parse_quoted_results(path: Path) -> List[str]:
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    return re.findall(r'"([^"]*)"', text)


def run_process(
    name: str,
    command: Sequence[str],
    cwd: Path,
    out_file: Path,
    err_file: Path,
    timeout_sec: int,
) -> Tuple[float, int, List[str]]:
    start = time.perf_counter()
    with out_file.open("w", encoding="utf-8", errors="replace") as stdout, err_file.open(
        "w", encoding="utf-8", errors="replace"
    ) as stderr:
        try:
            proc = subprocess.run(
                command,
                cwd=str(cwd),
                stdout=stdout,
                stderr=stderr,
                timeout=timeout_sec if timeout_sec > 0 else None,
                check=False,
            )
            code = proc.returncode
        except subprocess.TimeoutExpired:
            code = 124
            stderr.write(f"\n{name} timed out after {timeout_sec} seconds\n")
    seconds = time.perf_counter() - start
    return seconds, code, parse_quoted_results(out_file)


def compile_java_batch_runner(args: argparse.Namespace, java_root: Path, out_dir: Path) -> Optional[Path]:
    if args.java_runner != "batch":
        return None
    javac = shutil.which(args.javac)
    if not javac:
        raise FileNotFoundError("javac was not found; use --java-runner native or --java-runner process.")

    source = java_root / "CppkhJavaKhBatchRunner.java"
    if not source.exists():
        raise FileNotFoundError(f"batch runner source not found: {source}")

    classes_dir = out_dir / "java-helper-classes"
    classes_dir.mkdir(parents=True, exist_ok=True)
    class_file = classes_dir / "CppkhJavaKhBatchRunner.class"
    if class_file.exists() and class_file.stat().st_mtime >= source.stat().st_mtime:
        return classes_dir

    command = [
        javac,
        "-encoding",
        "UTF-8",
        "-cp",
        java_classpath(java_root),
        "-d",
        str(classes_dir),
        str(source),
    ]
    proc = subprocess.run(command, cwd=str(java_root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"javac failed:\n{proc.stdout}\n{proc.stderr}")
    return classes_dir


def run_cpp(args: argparse.Namespace, cpp_exe: Path, pd_file: Path, out_dir: Path) -> dict:
    command = [
        str(cpp_exe),
        "--pd-file",
        str(pd_file),
        "--quiet",
        "--threads",
        str(args.threads),
    ]
    if not args.no_external_simplify:
        command.append("--no-simplify-pd")
    seconds, code, results = run_process(
        "cppkh",
        command,
        REPO_ROOT,
        out_dir / "cppkh.out",
        out_dir / "cppkh.err",
        args.timeout_sec,
    )
    return {"name": "cppkh", "seconds": seconds, "exit_code": code, "results": results, "command": command}


def run_java(args: argparse.Namespace, java_root: Path, pd_file: Path, out_dir: Path) -> dict:
    if not (java_root / "org" / "katlas" / "JavaKh" / "JavaKh.class").exists():
        raise FileNotFoundError(f"JavaKh.class not found under {java_root}")
    java_work = out_dir / "java-work"
    if java_work.exists() and not args.keep_work:
        shutil.rmtree(java_work)
    java_work.mkdir(parents=True, exist_ok=True)

    if args.java_runner in ("auto", "native"):
        command = [
            args.java,
            f"-Xmx{args.java_xmx}",
            "-cp",
            java_classpath(java_root),
            "org.katlas.JavaKh.JavaKh",
            "-f",
            str(pd_file),
        ]
        seconds, code, results = run_process(
            "JavaKh",
            command,
            java_work,
            out_dir / "javakh.out",
            out_dir / "javakh.err",
            args.timeout_sec,
        )
        return {
            "name": "javakh",
            "seconds": seconds,
            "exit_code": code,
            "results": results,
            "command": command,
            "runner": "native",
        }

    helper_dir = compile_java_batch_runner(args, java_root, out_dir)
    if helper_dir is not None:
        command = [
            args.java,
            f"-Xmx{args.java_xmx}",
            "-cp",
            os.pathsep.join([str(helper_dir), java_classpath(java_root)]),
            "CppkhJavaKhBatchRunner",
            str(pd_file),
        ]
        if args.java_keep_cache:
            command.append("--keep-cache")
        seconds, code, results = run_process(
            "JavaKh",
            command,
            java_work,
            out_dir / "javakh.out",
            out_dir / "javakh.err",
            args.timeout_sec,
        )
        return {
            "name": "javakh",
            "seconds": seconds,
            "exit_code": code,
            "results": results,
            "command": command,
            "runner": "batch",
        }

    pd_lines = read_lines(pd_file)
    command = [
        args.java,
        f"-Xmx{args.java_xmx}",
        "-cp",
        java_classpath(java_root),
        "org.katlas.JavaKh.JavaKh",
    ]
    out_file = out_dir / "javakh.out"
    err_file = out_dir / "javakh.err"
    out_file.write_text("", encoding="utf-8")
    err_file.write_text("", encoding="utf-8")
    start = time.perf_counter()
    exit_code = 0
    with out_file.open("a", encoding="utf-8", errors="replace") as stdout, err_file.open(
        "a", encoding="utf-8", errors="replace"
    ) as stderr:
        for index, line in enumerate(pd_lines, 1):
            (java_work / "PD.txt").write_text(line + "\n", encoding="utf-8")
            if not args.java_keep_cache:
                shutil.rmtree(java_work / "cache", ignore_errors=True)
            try:
                proc = subprocess.run(
                    command,
                    cwd=str(java_work),
                    stdout=stdout,
                    stderr=stderr,
                    timeout=args.timeout_sec if args.timeout_sec > 0 else None,
                    check=False,
                )
                if proc.returncode != 0:
                    exit_code = proc.returncode
                    stderr.write(f"\nJavaKh failed at item {index}\n")
                    break
            except subprocess.TimeoutExpired:
                exit_code = 124
                stderr.write(f"\nJavaKh timed out at item {index} after {args.timeout_sec} seconds\n")
                break
    seconds = time.perf_counter() - start
    return {
        "name": "javakh",
        "seconds": seconds,
        "exit_code": exit_code,
        "results": parse_quoted_results(out_file),
        "command": command,
        "runner": "process",
    }


def compare_results(cpp: List[str], java: List[str], labels: List[str], out_dir: Path, max_show: int) -> Tuple[bool, int]:
    total = max(len(cpp), len(java))
    mismatches = []
    for index in range(total):
        cpp_value = cpp[index] if index < len(cpp) else "<missing>"
        java_value = java[index] if index < len(java) else "<missing>"
        if cpp_value != java_value:
            label = labels[index] if index < len(labels) else f"case-{index + 1:06d}"
            mismatches.append((index + 1, label, cpp_value, java_value))

    if mismatches:
        mismatch_file = out_dir / "mismatches.txt"
        lines = []
        for index, label, cpp_value, java_value in mismatches:
            lines.append(f"{index}\t{label}")
            lines.append(f"  cppkh : {cpp_value}")
            lines.append(f"  JavaKh: {java_value}")
        mismatch_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"compare: MISMATCH ({len(mismatches)} mismatches, details: {mismatch_file})")
        for index, label, cpp_value, java_value in mismatches[:max_show]:
            print(f"  {index} {label}: cppkh=[{cpp_value}] JavaKh=[{java_value}]")
        return False, len(mismatches)
    print("compare: OK")
    return True, 0


def write_summary(out_dir: Path, summary: dict) -> None:
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        f"input: {summary['input']}",
        f"items: {summary['items']}",
        f"prepare_seconds: {summary['prepare_seconds']:.6f}",
        f"external_simplify: {summary['external_simplify']}",
        f"cppkh_seconds: {summary['cppkh']['seconds']:.6f}",
        f"javakh_seconds: {summary['javakh']['seconds']:.6f}",
        f"cppkh_exit: {summary['cppkh']['exit_code']}",
        f"javakh_exit: {summary['javakh']['exit_code']}",
        f"javakh_runner: {summary['javakh'].get('runner', 'unknown')}",
        f"cppkh_results: {summary['cppkh']['result_count']}",
        f"javakh_results: {summary['javakh']['result_count']}",
        f"match: {summary['match']}",
        f"mismatches: {summary['mismatches']}",
    ]
    if summary["cppkh"]["seconds"] > 0:
        lines.append(f"java_over_cpp_speed_ratio: {summary['javakh']['seconds'] / summary['cppkh']['seconds']:.6f}")
    (out_dir / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare cppkh and bundled JavaKh on a PD-code collection.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="PD-code file. Lines may be PD[...] or label: [[...]].")
    parser.add_argument("--labels", default=str(DEFAULT_LABELS), help="Optional labels file for reports.")
    parser.add_argument("--cpp-exe", default="", help="Path to cppkh executable.")
    parser.add_argument("--build-cpp", action="store_true", help="Run the package script if no cppkh executable is found.")
    parser.add_argument("--java-root", default=str(DEFAULT_JAVA_ROOT), help="Bundled JavaKh reference directory.")
    parser.add_argument("--java", default="java", help="Java command.")
    parser.add_argument("--javac", default="javac", help="javac command used for the batch runner.")
    parser.add_argument("--java-xmx", default="4g", help="Java maximum heap, for example 4g or 16384m.")
    parser.add_argument(
        "--java-runner",
        choices=["auto", "native", "batch", "process"],
        default="auto",
        help="auto/native runs the patched JavaKh multiline reader; batch uses the helper; process starts Java once per PD.",
    )
    parser.add_argument("--java-keep-cache", action="store_true", help="Do not delete JavaKh's work cache between PDs.")
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "benchmark" / "kh-test"), help="Output directory.")
    parser.add_argument("--limit", type=int, default=0, help="Run at most N cases after --start.")
    parser.add_argument("--start", type=int, default=1, help="1-based first case to run.")
    parser.add_argument("--last", type=int, default=0, help="Run only the last N cases.")
    parser.add_argument("--threads", default="1", help="Runtime cppkh --threads value.")
    parser.add_argument("--timeout-sec", type=int, default=0, help="Per-program timeout; 0 disables timeout.")
    parser.add_argument("--no-external-simplify", action="store_true", help="Do not run R1/nugatory simplifiers first.")
    parser.add_argument("--keep-work", action="store_true", help="Keep and reuse the Java work directory.")
    parser.add_argument("--max-show-mismatches", type=int, default=5, help="Print at most N mismatches.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    cpp_exe = find_cpp_exe(args.cpp_exe, args.build_cpp)
    java_root = Path(args.java_root).resolve()

    print(f"input     : {Path(args.input).resolve()}")
    print(f"cppkh     : {cpp_exe}")
    print(f"JavaKh    : {java_root}")
    print(f"out       : {out_dir}")
    print("stage     : prepare PD codes")
    pd_file, labels_file, count, prepare_seconds = prepare_pd_file(args, out_dir)
    labels = read_lines(labels_file)
    print(f"prepared  : {count} cases in {prepare_seconds:.3f}s -> {pd_file}")
    print(f"simplify  : {'disabled' if args.no_external_simplify else 'R1 then nugatory'}")

    print("stage     : run cppkh")
    cpp_run = run_cpp(args, cpp_exe, pd_file, out_dir)
    print(
        "cppkh     : {0:.3f}s, exit={1}, results={2}".format(
            cpp_run["seconds"], cpp_run["exit_code"], len(cpp_run["results"])
        )
    )

    print("stage     : run bundled JavaKh")
    java_run = run_java(args, java_root, pd_file, out_dir)
    print(
        "JavaKh    : {0:.3f}s, exit={1}, results={2}, runner={3}".format(
            java_run["seconds"], java_run["exit_code"], len(java_run["results"]), java_run.get("runner", "unknown")
        )
    )

    match, mismatches = compare_results(
        cpp_run["results"],
        java_run["results"],
        labels,
        out_dir,
        args.max_show_mismatches,
    )
    if cpp_run["seconds"] > 0:
        print(f"timing    : JavaKh / cppkh = {java_run['seconds'] / cpp_run['seconds']:.3f}x")
    print(f"summary   : {out_dir / 'summary.txt'}")

    summary = {
        "input": str(Path(args.input).resolve()),
        "prepared_pd_file": str(pd_file),
        "items": count,
        "prepare_seconds": prepare_seconds,
        "external_simplify": not args.no_external_simplify,
        "cppkh": {
            "path": str(cpp_exe),
            "seconds": cpp_run["seconds"],
            "exit_code": cpp_run["exit_code"],
            "result_count": len(cpp_run["results"]),
            "command": cpp_run["command"],
        },
        "javakh": {
            "path": str(java_root),
            "seconds": java_run["seconds"],
            "exit_code": java_run["exit_code"],
            "result_count": len(java_run["results"]),
            "command": java_run["command"],
            "runner": java_run.get("runner", "unknown"),
        },
        "match": match,
        "mismatches": mismatches,
    }
    write_summary(out_dir, summary)

    if cpp_run["exit_code"] != 0 or java_run["exit_code"] != 0 or not match:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
