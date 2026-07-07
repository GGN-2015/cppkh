#!/usr/bin/env python3
import argparse
import ast
import re
from pathlib import Path


def parse_crossings(text):
    body = text.strip()
    if ":" in body:
        body = body.split(":", 1)[1].strip()

    if "X[" in body or body.startswith("PD["):
        crossings = []
        for match in re.finditer(r"X\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\]", body):
            crossings.append([int(match.group(i)) for i in range(1, 5)])
        if crossings:
            return crossings

    value = ast.literal_eval(body)
    crossings = []
    for crossing in value:
        if len(crossing) != 4:
            raise ValueError(f"crossing does not have four entries: {crossing!r}")
        crossings.append([int(x) for x in crossing])
    return crossings


def to_pd_line(crossings):
    return "PD[" + ",".join(
        "X[{},{},{},{}]".format(*crossing) for crossing in crossings
    ) + "]"


def simplify_external(crossings):
    try:
        import pd_code_de_r1
        import pd_code_delete_nugatory
    except ImportError as exc:
        raise SystemExit(
            "Missing external simplifier package. Install with:\n"
            "  python -m pip install pd-code-de-r1 pd-code-delete-nugatory"
        ) from exc

    crossings = pd_code_de_r1.de_r1(crossings)
    crossings = pd_code_delete_nugatory.erase_all_nugatory(crossings)
    return crossings


def main():
    parser = argparse.ArgumentParser(description="Prepare PD code batches for cppkh/JavaKh benchmarks.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--pd-out", required=True)
    parser.add_argument("--labels-out", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--simplify", choices=["none", "external"], default="external")
    args = parser.parse_args()

    pd_lines = []
    labels = []
    input_path = Path(args.input)
    for raw_line in input_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if args.limit > 0 and len(pd_lines) >= args.limit:
            break
        label = line.split(":", 1)[0].strip() if ":" in line else f"#{len(pd_lines) + 1}"
        crossings = parse_crossings(line)
        if args.simplify == "external":
            crossings = simplify_external(crossings)
        pd_lines.append(to_pd_line(crossings))
        labels.append(label)

    Path(args.pd_out).write_text("\n".join(pd_lines) + ("\n" if pd_lines else ""), encoding="utf-8")
    Path(args.labels_out).write_text("\n".join(labels) + ("\n" if labels else ""), encoding="utf-8")
    print(len(pd_lines))


if __name__ == "__main__":
    main()
