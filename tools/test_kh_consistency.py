#!/usr/bin/env python3
"""Cross-platform cppkh vs bundled JavaKh consistency and timing test."""

from __future__ import annotations

import argparse
import ast
import json
import os
import random
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

JAVAKH_INTERFACE_RUNNER = r"""
import re
import sys
import traceback
from pathlib import Path

import javakh_interface


def parse_crossings(text):
    body = text.strip()
    if body.replace(" ", "") == "PD[]":
        return []
    crossings = []
    pattern = r"X\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\]"
    for match in re.finditer(pattern, body):
        crossings.append([int(match.group(i)) for i in range(1, 5)])
    if crossings:
        return crossings
    raise ValueError(f"unsupported prepared PD line: {text!r}")


def main():
    pd_file = Path(sys.argv[1])
    de_r1 = sys.argv[2] == "1"
    de_k8 = sys.argv[3] == "1"
    for line in pd_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        result = javakh_interface.solve_khovanov(parse_crossings(line), de_r1=de_r1, de_k8=de_k8)
        print(f'"{result}"')


try:
    main()
except Exception:
    traceback.print_exc(file=sys.stderr)
    raise SystemExit(1)
"""


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


def write_sample_files(
    pd_file: Path,
    labels_file: Path,
    out_dir: Path,
    sample_size: int,
    seed: int,
) -> Tuple[Path, Path, Path, List[int], List[str]]:
    pd_lines = read_lines(pd_file)
    labels = read_lines(labels_file)
    if sample_size <= 0 or sample_size >= len(pd_lines):
        indices = list(range(len(pd_lines)))
    else:
        indices = sorted(random.Random(seed).sample(range(len(pd_lines)), sample_size))

    sample_lines = [pd_lines[index] for index in indices]
    sample_labels = [labels[index] if index < len(labels) else f"case-{index + 1:06d}" for index in indices]

    sample_pd = out_dir / "javakh_interface_sample.pd"
    sample_labels_file = out_dir / "javakh_interface_sample.labels.txt"
    sample_indices_file = out_dir / "javakh_interface_sample.indices.txt"
    sample_pd.write_text("\n".join(sample_lines) + ("\n" if sample_lines else ""), encoding="utf-8")
    sample_labels_file.write_text("\n".join(sample_labels) + ("\n" if sample_labels else ""), encoding="utf-8")
    sample_indices_file.write_text(
        "\n".join(f"{index + 1}\t{label}" for index, label in zip(indices, sample_labels))
        + ("\n" if indices else ""),
        encoding="utf-8",
    )
    return sample_pd, sample_labels_file, sample_indices_file, indices, sample_labels


def pick_results(results: List[str], indices: List[int]) -> List[str]:
    return [results[index] if index < len(results) else "<missing>" for index in indices]


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


def run_javakh_interface(args: argparse.Namespace, pd_file: Path, out_dir: Path) -> dict:
    command = [
        args.javakh_interface_python,
        "-c",
        JAVAKH_INTERFACE_RUNNER,
        str(pd_file),
        "1" if args.no_external_simplify else "0",
        "1" if args.no_external_simplify else "0",
    ]
    seconds, code, results = run_process(
        "javakh-interface",
        command,
        REPO_ROOT,
        out_dir / "javakh_interface.out",
        out_dir / "javakh_interface.err",
        args.timeout_sec,
    )
    return {
        "name": "javakh-interface",
        "seconds": seconds,
        "exit_code": code,
        "results": results,
        "command": command,
    }


def compare_results(
    runs: Sequence[Tuple[str, List[str]]],
    labels: List[str],
    out_dir: Path,
    max_show: int,
    report_name: str = "mismatches.txt",
    prefix: str = "compare",
) -> Tuple[bool, int]:
    total = max((len(results) for _, results in runs), default=0)
    mismatches = []
    for index in range(total):
        values = []
        for name, results in runs:
            value = results[index] if index < len(results) else "<missing>"
            values.append((name, value))
        if len({value for _, value in values}) != 1:
            label = labels[index] if index < len(labels) else f"case-{index + 1:06d}"
            mismatches.append((index + 1, label, values))

    if mismatches:
        mismatch_file = out_dir / report_name
        lines = []
        for index, label, values in mismatches:
            lines.append(f"{index}\t{label}")
            for name, value in values:
                lines.append(f"  {name}: {value}")
        mismatch_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{prefix}: MISMATCH ({len(mismatches)} mismatches, details: {mismatch_file})")
        for index, label, values in mismatches[:max_show]:
            rendered = " ".join(f"{name}=[{value}]" for name, value in values)
            print(f"  {index} {label}: {rendered}")
        return False, len(mismatches)
    print(f"{prefix}: OK")
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
        f"cppkh_javakh_full_match: {summary['cppkh_javakh_full_match']}",
        f"cppkh_javakh_full_mismatches: {summary['cppkh_javakh_full_mismatches']}",
        f"match: {summary['match']}",
    ]
    javakh_interface = summary.get("javakh_interface")
    if javakh_interface:
        sample = javakh_interface["sample"]
        lines.extend(
            [
                f"javakh_interface_sample_size: {sample['count']}",
                f"javakh_interface_sample_seed: {sample['seed']}",
                f"javakh_interface_seconds: {javakh_interface['seconds']:.6f}",
                f"javakh_interface_average_seconds: {javakh_interface['average_seconds']:.6f}",
                f"javakh_interface_exit: {javakh_interface['exit_code']}",
                f"javakh_interface_results: {javakh_interface['result_count']}",
                f"javakh_interface_sample_match: {javakh_interface['sample_match']}",
                f"javakh_interface_sample_mismatches: {javakh_interface['sample_mismatches']}",
            ]
        )
    else:
        lines.append("javakh_interface: disabled")
    if summary["cppkh"]["seconds"] > 0:
        lines.append(f"java_over_cpp_speed_ratio: {summary['javakh']['seconds'] / summary['cppkh']['seconds']:.6f}")
    if javakh_interface and summary["cppkh"]["average_seconds"] > 0:
        lines.append(
            "javakh_interface_over_cpp_average_speed_ratio: "
            f"{javakh_interface['average_seconds'] / summary['cppkh']['average_seconds']:.6f}"
        )
    (out_dir / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare cppkh and bundled JavaKh on a PD-code collection, with an optional "
            "fixed-size PyPI javakh-interface sample check."
        )
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="PD-code file. Lines may be PD[...] or label: [[...]].")
    parser.add_argument("--labels", default=str(DEFAULT_LABELS), help="Optional labels file for reports.")
    parser.add_argument("--cpp-exe", default="", help="Path to cppkh executable.")
    parser.add_argument("--build-cpp", action="store_true", help="Run the package script if no cppkh executable is found.")
    parser.add_argument("--java-root", default=str(DEFAULT_JAVA_ROOT), help="Bundled JavaKh reference directory.")
    parser.add_argument("--java", default="java", help="Java command.")
    parser.add_argument("--javac", default="javac", help="javac command used for the batch runner.")
    parser.add_argument("--java-xmx", default="4g", help="Java maximum heap, for example 4g or 16384m.")
    parser.add_argument(
        "--javakh-interface-python",
        default="",
        help="Python executable with the PyPI javakh-interface package installed. Disabled when omitted.",
    )
    parser.add_argument(
        "--javakh-interface-sample-size",
        type=int,
        default=50,
        help="Number of prepared cases sampled for PyPI javakh-interface checks. Use 0 for all selected cases.",
    )
    parser.add_argument(
        "--javakh-interface-sample-seed",
        type=int,
        default=20260712,
        help="Deterministic random seed for the PyPI javakh-interface sample.",
    )
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
    if args.javakh_interface_python:
        print(
            f"PyPI iface: {args.javakh_interface_python} "
            f"(sample={args.javakh_interface_sample_size}, seed={args.javakh_interface_sample_seed})"
        )
    else:
        print("PyPI iface: disabled")
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

    full_match, full_mismatches = compare_results(
        [
            ("cppkh", cpp_run["results"]),
            ("JavaKh", java_run["results"]),
        ],
        labels,
        out_dir,
        args.max_show_mismatches,
        report_name="cppkh_javakh_mismatches.txt",
        prefix="full compare",
    )

    javakh_interface_run = None
    javakh_interface_match = True
    javakh_interface_mismatches = 0
    javakh_interface_sample = None
    if args.javakh_interface_python:
        sample_pd, sample_labels_file, sample_indices_file, sample_indices, sample_labels = write_sample_files(
            pd_file,
            labels_file,
            out_dir,
            args.javakh_interface_sample_size,
            args.javakh_interface_sample_seed,
        )
        javakh_interface_sample = {
            "count": len(sample_indices),
            "seed": args.javakh_interface_sample_seed,
            "indices_file": str(sample_indices_file),
            "pd_file": str(sample_pd),
            "labels_file": str(sample_labels_file),
            "indices_1_based": [index + 1 for index in sample_indices],
        }
        print(
            "stage     : run PyPI javakh-interface sample "
            f"({len(sample_indices)} of {count}, seed={args.javakh_interface_sample_seed})"
        )
        javakh_interface_run = run_javakh_interface(args, sample_pd, out_dir)
        print(
            "PyPI iface: {0:.3f}s, exit={1}, results={2}, avg={3:.6f}s/case".format(
                javakh_interface_run["seconds"],
                javakh_interface_run["exit_code"],
                len(javakh_interface_run["results"]),
                javakh_interface_run["seconds"] / len(sample_indices) if sample_indices else 0.0,
            )
        )
        javakh_interface_match, javakh_interface_mismatches = compare_results(
            [
                ("cppkh", pick_results(cpp_run["results"], sample_indices)),
                ("JavaKh", pick_results(java_run["results"], sample_indices)),
                ("javakh-interface", javakh_interface_run["results"]),
            ],
            sample_labels,
            out_dir,
            args.max_show_mismatches,
            report_name="javakh_interface_sample_mismatches.txt",
            prefix="sample compare",
        )

    if cpp_run["seconds"] > 0:
        print(f"timing    : JavaKh / cppkh = {java_run['seconds'] / cpp_run['seconds']:.3f}x")
    if javakh_interface_run and count > 0:
        cpp_avg = cpp_run["seconds"] / count
        iface_avg = javakh_interface_run["seconds"] / javakh_interface_sample["count"]
        if cpp_avg > 0:
            print(f"timing    : javakh-interface sample avg / cppkh full avg = {iface_avg / cpp_avg:.3f}x")
    print(f"summary   : {out_dir / 'summary.txt'}")

    match = full_match and javakh_interface_match
    summary = {
        "input": str(Path(args.input).resolve()),
        "prepared_pd_file": str(pd_file),
        "items": count,
        "prepare_seconds": prepare_seconds,
        "external_simplify": not args.no_external_simplify,
        "cppkh": {
            "path": str(cpp_exe),
            "seconds": cpp_run["seconds"],
            "average_seconds": cpp_run["seconds"] / count if count else 0.0,
            "exit_code": cpp_run["exit_code"],
            "result_count": len(cpp_run["results"]),
            "command": cpp_run["command"],
        },
        "javakh": {
            "path": str(java_root),
            "seconds": java_run["seconds"],
            "average_seconds": java_run["seconds"] / count if count else 0.0,
            "exit_code": java_run["exit_code"],
            "result_count": len(java_run["results"]),
            "command": java_run["command"],
            "runner": java_run.get("runner", "unknown"),
        },
        "match": match,
        "cppkh_javakh_full_match": full_match,
        "cppkh_javakh_full_mismatches": full_mismatches,
    }
    if javakh_interface_run and javakh_interface_sample:
        sample_count = javakh_interface_sample["count"]
        summary["javakh_interface"] = {
            "python": args.javakh_interface_python,
            "seconds": javakh_interface_run["seconds"],
            "average_seconds": javakh_interface_run["seconds"] / sample_count if sample_count else 0.0,
            "exit_code": javakh_interface_run["exit_code"],
            "result_count": len(javakh_interface_run["results"]),
            "command": javakh_interface_run["command"],
            "sample": javakh_interface_sample,
            "sample_match": javakh_interface_match,
            "sample_mismatches": javakh_interface_mismatches,
        }
    write_summary(out_dir, summary)

    if cpp_run["exit_code"] != 0 or java_run["exit_code"] != 0 or not match:
        return 1
    if javakh_interface_run and javakh_interface_run["exit_code"] != 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
