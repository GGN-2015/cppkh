#!/usr/bin/env python3
"""Standalone cppkh-interface regression using only the Python standard library."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
LOCAL_PACKAGE_ROOT = ROOT / "python_project" / "cppkh-interface"
sys.path.insert(0, str(LOCAL_PACKAGE_ROOT))


TREFOIL = [[1, 5, 2, 4], [3, 1, 4, 6], [5, 3, 6, 2]]
TREFOIL_RESULT = (
    "q^1*t^0*Z[0] + q^3*t^0*Z[0] + q^5*t^2*Z[0] + "
    "q^7*t^3*Z[2] + q^9*t^3*Z[0]"
)
UNKNOT_RESULT = "q^-1*t^0*Z[0] + q^1*t^0*Z[0]"
R1 = [[1, 1, 2, 2]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", help="C++ compiler command passed to compile_cppkh().")
    parser.add_argument("--cache-dir", help="Override CPPKH_INTERFACE_CACHE_DIR.")
    parser.add_argument("--force-compile", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.cache_dir:
        os.environ["CPPKH_INTERFACE_CACHE_DIR"] = str(Path(args.cache_dir).resolve())

    import cppkh_interface as kh

    executable = kh.compile_cppkh(force=args.force_compile, cxx=args.cxx)
    assert executable.is_file(), executable
    assert kh.compute_many_pd([], show_real_pdcode=True) == []

    for de_r1 in (False, True):
        for de_k8 in (False, True):
            expected_r1 = "PD[X[1,1,2,2]]" if not de_r1 and not de_k8 else "PD[]"
            actual_r1 = kh.simplify_pd(R1, de_r1=de_r1, de_k8=de_k8)
            assert actual_r1 == expected_r1, (de_r1, de_k8, actual_r1)

            single = kh.compute_pd(TREFOIL, de_r1=de_r1, de_k8=de_k8)
            batch = kh.compute_many_pd([TREFOIL, []], de_r1=de_r1, de_k8=de_k8)
            assert single == TREFOIL_RESULT, (de_r1, de_k8, single)
            assert batch == [TREFOIL_RESULT, UNKNOT_RESULT], (de_r1, de_k8, batch)

    try:
        kh.compute_pd([[1, 2, 3, 4]], de_r1=False, de_k8=False)
    except kh.CppkhInterfaceError:
        pass
    else:
        raise AssertionError("invalid PD code was accepted")

    print(f"cppkh-interface standalone regression: OK ({executable})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
