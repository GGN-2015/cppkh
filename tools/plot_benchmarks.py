#!/usr/bin/env python3
"""Generate benchmark figures for the README and benchmark docs."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = REPO_ROOT / "docs" / "assets"


RUNTIME_ROWS = [
    {
        "label": "First 1000",
        "items": 1000,
        "cppkh_seconds": 4.293649,
        "cppkh_interface_seconds": 4.041444,
        "javakh_seconds": 47.483754,
    },
    {
        "label": "Last 1000",
        "items": 1000,
        "cppkh_seconds": 17.851301,
        "cppkh_interface_seconds": 17.262348,
        "javakh_seconds": 83.403080,
    },
    {
        "label": "Full 8397",
        "items": 8397,
        "cppkh_seconds": 64.185450,
        "cppkh_interface_seconds": 65.405585,
        "javakh_seconds": 298.452713,
    },
]


# Filled from a full 8397-case process-memory run with
# tools/measure_peak_memory.py. Values are peak RSS measurements in MiB.
MEMORY_MIB = {
    "cppkh_peak_rss": 26.046875,
    "cppkh_interface_peak_rss": 60.2265625,
    "javakh_peak_rss": 491.55078125,
}


SERIES = [
    ("cppkh", "cppkh_seconds", "#207567"),
    ("cppkh-interface", "cppkh_interface_seconds", "#536d99"),
    ("patched JavaKh", "javakh_seconds", "#b14a35"),
]


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
    y = np.arange(len(labels))
    height = 0.22

    offsets = [height, 0.0, -height]
    for (name, key, color), offset in zip(SERIES, offsets):
        values = np.array([row[key] / row["items"] for row in RUNTIME_ROWS])
        bars = ax.barh(y + offset, values, height, label=name, color=color)
        annotate_bars(ax, bars, "s/code")

    max_value = max(
        row[key] / row["items"]
        for row in RUNTIME_ROWS
        for _, key, _ in SERIES
    )
    label_x = max_value * 0.68
    for index, row in enumerate(RUNTIME_ROWS):
        cpp_avg = row["cppkh_seconds"] / row["items"]
        java_avg = row["javakh_seconds"] / row["items"]
        interface_avg = row["cppkh_interface_seconds"] / row["items"]
        speedup = java_avg / cpp_avg
        interface_speedup = java_avg / interface_avg
        ax.text(
            label_x,
            index,
            f"Java/cpp {speedup:.2f}x\ncpp-pkg {interface_speedup:.2f}x",
            va="center",
            ha="center",
            fontsize=9,
            fontweight="bold",
            color="#222222",
        )

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("Average seconds per PD code (lower is better)")
    ax.set_title("Khovanov Homology Runtime Per Case")
    ax.grid(axis="x", color="#dddddd", linewidth=0.8)
    ax.legend(
        handles=[Patch(facecolor=color, label=name) for name, _, color in SERIES],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.13),
        ncol=2,
        fontsize=9,
    )


def draw_memory(ax: plt.Axes) -> bool:
    if any(value is None for value in MEMORY_MIB.values()):
        return False

    labels = ["Full 8397 peak RSS"]
    cpp = np.array([MEMORY_MIB["cppkh_peak_rss"]], dtype=float)
    interface = np.array([MEMORY_MIB["cppkh_interface_peak_rss"]], dtype=float)
    java = np.array([MEMORY_MIB["javakh_peak_rss"]], dtype=float)
    y = np.arange(len(labels))
    height = 0.22

    cpp_bars = ax.barh(y + height, cpp, height, label="cppkh", color="#207567")
    interface_bars = ax.barh(y, interface, height, label="cppkh-interface", color="#536d99")
    java_bars = ax.barh(y - height, java, height, label="patched JavaKh", color="#b14a35")
    annotate_bars(ax, cpp_bars, " MiB")
    annotate_bars(ax, interface_bars, " MiB")
    annotate_bars(ax, java_bars, " MiB")

    for index in range(len(labels)):
        ratio = java[index] / cpp[index]
        interface_ratio = java[index] / interface[index]
        ax.text(
            max(cpp[index], java[index]) * 0.60,
            index,
            "full Java/cpp {0:.2f}x\nfull cpp-pkg/cpp {1:.2f}x".format(
                ratio,
                interface_ratio,
            ),
            va="center",
            ha="center",
            fontsize=9,
            fontweight="bold",
            color="#222222",
        )

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("MiB (lower is better)")
    ax.set_title("Peak Memory")
    ax.grid(axis="x", color="#dddddd", linewidth=0.8)
    ax.legend(loc="lower right", fontsize=9)
    return True


def main() -> int:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    has_memory = not any(value is None for value in MEMORY_MIB.values())
    if has_memory:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6.4), constrained_layout=True)
        draw_runtime(axes[0])
        draw_memory(axes[1])
    else:
        fig, ax = plt.subplots(figsize=(9, 5.5), constrained_layout=True)
        draw_runtime(ax)

    fig.suptitle("cppkh, cppkh-interface, and Patched Bundled JavaKh", fontsize=15, fontweight="bold")
    output = ASSET_DIR / "benchmark_runtime_memory.png"
    fig.savefig(output, dpi=180)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
