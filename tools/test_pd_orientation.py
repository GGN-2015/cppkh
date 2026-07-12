#!/usr/bin/env python3
"""Regression tests for SageMath-compatible PD crossing orientations."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = REPO_ROOT / "tests" / "data" / "pd_orientation_cases.json"
JAVA_ROOT = REPO_ROOT / "reference" / "javakh"
PYTHON_PACKAGE_ROOT = REPO_ROOT / "python_project" / "cppkh-interface"


def run(command: Sequence[str], *, cwd: Path = REPO_ROOT, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(
        list(command),
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        rendered = subprocess.list2cmdline(list(command))
        raise RuntimeError(f"command failed ({proc.returncode}): {rendered}\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout


def find_cpp_exe(explicit: str) -> Path:
    if explicit:
        path = Path(explicit).resolve()
        if path.exists():
            return path
        raise FileNotFoundError(path)
    name = "cppkh.exe" if os.name == "nt" else "cppkh"
    candidates = [
        REPO_ROOT / "build" / "orientation-test" / name,
        REPO_ROOT / "dist" / ("windows" if os.name == "nt" else "linux") / name,
        REPO_ROOT / "build" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError("cppkh executable not found; build it or pass --cpp-exe")


def java_classpath(extra: Path | None = None) -> str:
    entries = [] if extra is None else [extra]
    entries.extend(
        [
            JAVA_ROOT,
            JAVA_ROOT / "jars" / "log4j-1.2.12.jar",
            JAVA_ROOT / "jars" / "commons-io-1.2.jar",
            JAVA_ROOT / "jars" / "commons-cli-1.0.jar",
            JAVA_ROOT / "jars" / "commons-logging-1.1.jar",
        ]
    )
    return os.pathsep.join(str(path) for path in entries)


def compile_java(javac: str, classes_dir: Path) -> None:
    run(
        [
            javac,
            "--release",
            "8",
            "-encoding",
            "UTF-8",
            "-cp",
            java_classpath(),
            "-d",
            str(classes_dir),
            str(JAVA_ROOT / "org" / "katlas" / "JavaKh" / "PDOrientation.java"),
            str(JAVA_ROOT / "org" / "katlas" / "JavaKh" / "JavaKh.java"),
        ]
    )


def parse_sign_lines(output: str) -> list[list[int]]:
    values = []
    for line in output.splitlines():
        match = re.search(r"(\[-?\d+(?:,-?\d+)*\]|\[\])\s*$", line)
        if match:
            values.append(json.loads(match.group(1)))
    return values


def parse_homology(output: str) -> list[str]:
    return re.findall(r'"([^"]*)"', output)


def run_python_interface(python: str, pd_file: Path) -> list[str]:
    runner = r"""
import json
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
import cppkh_interface
codes = [line.strip() for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line.strip()]
print("CPPKH_INTERFACE_RESULTS=" + json.dumps(
    cppkh_interface.compute_many_pd(codes, de_r1=False, de_k8=False, threads="1")
))
"""
    output = run([python, "-c", runner, str(pd_file), str(PYTHON_PACKAGE_ROOT)])
    match = re.search(r"^CPPKH_INTERFACE_RESULTS=(.*)$", output, re.MULTILINE)
    if not match:
        raise RuntimeError(f"cppkh-interface did not emit its result marker:\n{output}")
    return json.loads(match.group(1))


def run_ctypes_interface(python: str, library: Path, pd_file: Path) -> list[str]:
    runner = r"""
import json
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[3])
from cppkh_ctypes import CppKhLibrary
codes = [line.strip() for line in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines() if line.strip()]
kh = CppKhLibrary(sys.argv[1])
print("CPPKH_CTYPES_RESULTS=" + json.dumps(
    kh.compute_many_pd(codes, simplify_pd=False, reorder_crossings=True)
))
"""
    output = run([python, "-c", runner, str(library), str(pd_file), str(REPO_ROOT / "python")])
    match = re.search(r"^CPPKH_CTYPES_RESULTS=(.*)$", output, re.MULTILINE)
    if not match:
        raise RuntimeError(f"cppkh ctypes interface did not emit its result marker:\n{output}")
    return json.loads(match.group(1))


def assert_equal(actual, expected, description: str) -> None:
    if actual != expected:
        raise AssertionError(f"{description}: expected {expected!r}, got {actual!r}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--cpp-exe", default="")
    parser.add_argument("--java", default="java")
    parser.add_argument("--javac", default="javac")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--cpp-library", default="", help="Optional cppkh shared library for ctypes checks.")
    parser.add_argument("--skip-python-interface", action="store_true")
    args = parser.parse_args(argv)

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    expected_signs = [case["signs"] for case in cases]
    cpp_exe = find_cpp_exe(args.cpp_exe)

    with tempfile.TemporaryDirectory(prefix="cppkh_orientation_test_") as temp_text:
        temp = Path(temp_text)
        all_pd = temp / "orientation.pd"
        all_pd.write_text("\n".join(case["pd"] for case in cases) + "\n", encoding="ascii")
        classes = temp / "classes"
        classes.mkdir()
        compile_java(args.javac, classes)

        cpp_signs = parse_sign_lines(
            run([str(cpp_exe), "--pd-file", str(all_pd), "--print-crossing-signs", "--quiet"])
        )
        java_signs = parse_sign_lines(
            run(
                [
                    args.java,
                    "-cp",
                    java_classpath(classes),
                    "org.katlas.JavaKh.JavaKh",
                    "--print-crossing-signs",
                    "--pd-file",
                    str(all_pd),
                ],
                cwd=temp,
            )
        )
        assert_equal(cpp_signs, expected_signs, "CppKh crossing signs")
        assert_equal(java_signs, expected_signs, "JavaKh crossing signs")

        compute_cases = [case for case in cases if case.get("compute", True)]
        compute_pd = temp / "compute.pd"
        compute_pd.write_text("\n".join(case["pd"] for case in compute_cases) + "\n", encoding="ascii")
        cpp_homology = parse_homology(
            run([str(cpp_exe), "--pd-file", str(compute_pd), "--no-simplify-pd", "--quiet"])
        )
        java_homology = parse_homology(
            run(
                [args.java, "-cp", java_classpath(classes), "org.katlas.JavaKh.JavaKh", "--pd-file", str(compute_pd)],
                cwd=temp,
            )
        )
        assert_equal(cpp_homology, java_homology, "CppKh and JavaKh homology")

        if not args.skip_python_interface:
            python_homology = run_python_interface(args.python, compute_pd)
            assert_equal(python_homology, cpp_homology, "cppkh-interface and CppKh homology")
            if args.cpp_library:
                ctypes_homology = run_ctypes_interface(args.python, Path(args.cpp_library).resolve(), compute_pd)
                assert_equal(ctypes_homology, cpp_homology, "cppkh ctypes interface and CppKh homology")

        groups: dict[str, list[int]] = {}
        for index, case in enumerate(compute_cases):
            group = case.get("equivalent_group")
            if group:
                groups.setdefault(group, []).append(index)
        for group, indices in groups.items():
            values = {cpp_homology[index] for index in indices}
            if len(values) != 1:
                raise AssertionError(f"arc relabelling changed homology for {group}: {values!r}")

    interfaces = "CppKh, JavaKh"
    if not args.skip_python_interface:
        interfaces += ", cppkh-interface"
        if args.cpp_library:
            interfaces += ", cppkh ctypes"
    print(f"orientation regression: OK ({len(cases)} sign cases, {len(compute_cases)} homology cases)")
    print(f"interfaces: {interfaces}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
