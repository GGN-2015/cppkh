#!/usr/bin/env python3
"""Run three-way core checks and optional legacy-interface sampling on the 10_3 link PD set."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence

import test_kh_consistency


REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT = REPO_ROOT / "tests" / "data" / "pd_codes_10_3_links.txt"
LABELS = REPO_ROOT / "tests" / "data" / "pd_codes_10_3_links.labels.txt"
OUT_DIR = REPO_ROOT / "benchmark" / "links-10-3-consistency"


def main(argv: Optional[Sequence[str]] = None) -> int:
    defaults = [
        "--input",
        str(INPUT),
        "--labels",
        str(LABELS),
        "--out-dir",
        str(OUT_DIR),
    ]
    return test_kh_consistency.main(defaults + list(argv or ()))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
