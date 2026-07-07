# Benchmarks

The benchmark helper converts `test_pdcode.txt`, applies the external
R1/nugatory simplifiers when requested, runs `cppkh` and the bundled JavaKh
reference, and compares quoted homology strings.

Install the external simplifiers used for JavaKh comparison:

```sh
python -m pip install pd-code-de-r1 pd-code-delete-nugatory
```

Run a benchmark:

```sh
python tools/test_kh_consistency.py --build-cpp --out-dir benchmark/full
```

The default Java runner is the patched bundled JavaKh entry point, which reads
one PD code per non-empty line:

```text
org.katlas.JavaKh.JavaKh -f prepared.pd
```

## Current Local Benchmark

Machine-local benchmark on Windows, 2026-07-07:

- C++ compiler: WinLibs GCC 16.1.0 x86_64 UCRT POSIX SEH.
- Java VM: Java HotSpot 64-Bit Server VM 21.0.5.
- `cppkh` executable: `benchmark\bench-triad-cpp\cppkh.exe`.
- `cppkh-interface` package: local `cppkh-interface 0.1.1` wheel installed
  into `benchmark\venv-cppkh-interface-011`.
- `cppkh-interface` timing excludes first-use C++ compilation. The benchmark
  used the already cached executable under
  `benchmark\cppkh-interface-cache-011`.
- Java runner: patched bundled JavaKh native multiline reader
  (`--java-runner native`).
- Input: 8397 normalized PD codes in `tests\data\test_pdcode.txt`.
- Preprocessing: R1 removal, then nugatory-crossing removal. Runtime columns
  below report only core program time after the prepared PD file has been
  written.

| Input set | Items | prepare | cppkh | cppkh-interface | patched JavaKh | Java/cppkh | Java/interface | compare |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| First 1000 lines | 1000 | 1.249s | 4.294s | 4.041s | 47.484s | 11.059x | 11.750x | OK |
| Last 1000 lines | 1000 | 1.587s | 17.851s | 17.262s | 83.403s | 4.672x | 4.831x | OK |
| Full `test_pdcode.txt` | 8397 | 11.057s | 61.596s | 61.392s | 466.562s | 7.575x | 7.600x | OK |

![cppkh benchmark runtime and memory chart](assets/benchmark_runtime_memory.png)

Average milliseconds per PD code, lower is better:

```text
First 1000
cppkh             | ## 4.294 ms
cppkh-interface   | ## 4.041 ms
patched JavaKh    | #################### 47.484 ms

Last 1000
cppkh             | #### 17.851 ms
cppkh-interface   | #### 17.262 ms
patched JavaKh    | #################### 83.403 ms

Full 8397
cppkh             | ### 7.336 ms
cppkh-interface   | ### 7.311 ms
patched JavaKh    | #################### 55.563 ms
```

The full-run summary was:

```text
items: 8397
cppkh_seconds: 61.596
cppkh_interface_seconds: 61.392
javakh_seconds: 466.562
cppkh_results: 8397
cppkh_interface_results: 8397
javakh_results: 8397
match: True
mismatches: 0
java_over_cpp_speed_ratio: 7.575
java_over_cppkh_interface_speed_ratio: 7.600
```

## Peak Memory

Peak resident memory was measured separately on the same prepared full input
with `tools/measure_peak_memory.py`. The measurement discards stdout/stderr and
samples process-tree RSS with `psutil`, so it is intended to compare memory
pressure rather than to validate output again. The `cppkh-interface` row
includes the Python wrapper process plus the cached child `cppkh` executable,
and still excludes first-use compilation.

| Input set | Metric | cppkh | cppkh-interface | patched JavaKh | Java/cppkh | Java/interface |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Full `test_pdcode.txt` | Peak RSS | 26.04 MiB | 68.08 MiB | 453.57 MiB | 17.42x | 6.66x |

The memory-measurement run completed successfully:

```text
cppkh_seconds: 62.425
cppkh_interface_seconds: 63.848
javakh_seconds: 457.233
cppkh_peak_rss_mib: 26.035
cppkh_interface_peak_rss_mib: 68.078
javakh_peak_rss_mib: 453.570
javakh_over_cpp_peak_rss_ratio: 17.421
javakh_over_cppkh_interface_peak_rss_ratio: 6.662
```

## Regenerating The Figure

Install the plotting and memory-measurement helpers:

```sh
python -m pip install matplotlib psutil
```

Regenerate the chart:

```sh
python tools/plot_benchmarks.py
```

Rerun the peak-RSS measurement on an already prepared full PD file:

```sh
python tools/measure_peak_memory.py \
  --prepared-pd benchmark/triad-full8397-011/prepared.pd \
  --cpp-exe benchmark/bench-triad-cpp/cppkh.exe \
  --cppkh-interface-python benchmark/venv-cppkh-interface-011/Scripts/python.exe \
  --cppkh-interface-cache-dir benchmark/cppkh-interface-cache-011 \
  --cppkh-interface-cxx /path/to/g++ \
  --out benchmark/triad-full8397-memory-011.json
```
