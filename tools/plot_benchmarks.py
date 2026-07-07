#!/usr/bin/env python3
"""Generate benchmark figures for the README and benchmark docs."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = REPO_ROOT / "docs" / "assets"


RUNTIME_ROWS = [
    {
        "label": "First 1000",
        "items": 1000,
        "cppkh_seconds": 4.642398,
        "javakh_seconds": 49.132353,
    },
    {
        "label": "Last 1000",
        "items": 1000,
        "cppkh_seconds": 18.451239,
        "javakh_seconds": 88.057673,
    },
    {
        "label": "Full 8397",
        "items": 8397,
        "cppkh_seconds": 62.970849,
        "javakh_seconds": 467.016071,
    },
]


# Filled from a full 8397-case process-memory run with
# tools/measure_peak_memory.py. Values are peak RSS measurements in MiB.
MEMORY_MIB = {
    "cppkh_peak_rss": 25.8671875,
    "javakh_peak_rss": 483.35546875,
}


def annotate_bars(ax: plt.Axes, bars, suffix: str = "") -> None:
    for bar in bars:
        width = bar.get_width()
        ax.text(
            width,
            bar.get_y() + bar.get_height() / 2,
            f" {width:.3g}{suffix}",
            va="center",
            ha="left",
            fontsize=9,
        )


def draw_runtime(ax: plt.Axes) -> None:
    labels = [row["label"] for row in RUNTIME_ROWS]
    cpp = np.array([row["cppkh_seconds"] for row in RUNTIME_ROWS])
    java = np.array([row["javakh_seconds"] for row in RUNTIME_ROWS])
    y = np.arange(len(labels))
    height = 0.34

    cpp_bars = ax.barh(y + height / 2, cpp, height, label="cppkh", color="#207567")
    java_bars = ax.barh(y - height / 2, java, height, label="patched JavaKh", color="#b14a35")
    annotate_bars(ax, cpp_bars, "s")
    annotate_bars(ax, java_bars, "s")

    label_x = max(java) * 0.72
    for index, row in enumerate(RUNTIME_ROWS):
        speedup = row["javakh_seconds"] / row["cppkh_seconds"]
        ax.text(
            label_x,
            index,
            f"{speedup:.2f}x faster",
            va="center",
            ha="center",
            fontsize=10,
            fontweight="bold",
            color="#222222",
        )

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("Runtime (seconds, lower is better)")
    ax.set_title("Khovanov Homology Runtime")
    ax.grid(axis="x", color="#dddddd", linewidth=0.8)
    ax.legend(loc="lower right")


def draw_memory(ax: plt.Axes) -> bool:
    if any(value is None for value in MEMORY_MIB.values()):
        return False

    labels = ["Full 8397 peak RSS"]
    cpp = np.array([MEMORY_MIB["cppkh_peak_rss"]], dtype=float)
    java = np.array([MEMORY_MIB["javakh_peak_rss"]], dtype=float)
    y = np.arange(len(labels))
    height = 0.34

    cpp_bars = ax.barh(y + height / 2, cpp, height, label="cppkh", color="#207567")
    java_bars = ax.barh(y - height / 2, java, height, label="patched JavaKh", color="#b14a35")
    annotate_bars(ax, cpp_bars, " MiB")
    annotate_bars(ax, java_bars, " MiB")

    for index in range(len(labels)):
        ratio = java[index] / cpp[index]
        ax.text(
            max(cpp[index], java[index]) * 0.60,
            index,
            f"{ratio:.2f}x Java/C++",
            va="center",
            ha="center",
            fontsize=10,
            fontweight="bold",
            color="#222222",
        )

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("MiB (lower is better)")
    ax.set_title("Full 8397-Case Peak Memory")
    ax.grid(axis="x", color="#dddddd", linewidth=0.8)
    ax.legend(loc="lower right")
    return True


def main() -> int:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    has_memory = not any(value is None for value in MEMORY_MIB.values())
    if has_memory:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
        draw_runtime(axes[0])
        draw_memory(axes[1])
    else:
        fig, ax = plt.subplots(figsize=(9, 5.5), constrained_layout=True)
        draw_runtime(ax)

    fig.suptitle("cppkh vs Patched Bundled JavaKh", fontsize=15, fontweight="bold")
    output = ASSET_DIR / "benchmark_runtime_memory.png"
    fig.savefig(output, dpi=180)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
