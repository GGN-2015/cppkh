# Testing cppkh Against JavaKh

`tools/test_kh_consistency.py` is the cross-platform consistency and timing
test runner. It compares `cppkh` against the bundled JavaKh reference runtime
in `reference/javakh/`.

## Data Format

The default input is:

```text
tests/data/test_pdcode.txt
```

Each line is already normalized to standard `PD[...]` form, for example:

```text
PD[X[1,5,2,4],X[3,1,4,6],X[5,3,6,2]]
```

The file currently contains 8397 cases:

- 6614 cases from the original `javakh_ori/test_pdcode.txt`.
- 1783 cases parsed from
  <https://github.com/TopologicalKnotIndexer/com_pd_code_list/blob/main/data/com_pd_code_list.txt>.

The converter removed original prefixes such as `0000001.txt:` and
`[K3a1|...]`, then added `PD` and `X` wrappers. Original labels are preserved in
`tests/data/test_pdcode.labels.txt`.

The test script can also read raw files with these forms:

```text
0000001.txt: [[2, 3, 1, 4], [3, 2, 4, 1]]
[K3a1|[[1, 5, 2, 4], [3, 1, 4, 6], [5, 3, 6, 2]]]
PD[X[1,5,2,4],X[3,1,4,6],X[5,3,6,2]]
```

## Requirements

- Python 3.
- A built `cppkh` executable, or pass `--build-cpp`.
- A Java runtime available as `java`.
- A JDK with `javac` is only needed for `--java-runner batch`.
- For default preprocessing, install the external simplifiers:

```sh
python -m pip install pd-code-de-r1 pd-code-delete-nugatory
```

Pass `--no-external-simplify` to test raw PD codes without the R1 then nugatory
preprocessing step.

## Quick Test

Same command on Windows, Linux, and macOS:

```sh
python tools/test_kh_consistency.py --build-cpp --limit 10
```

The runner prints stage timings:

```text
prepared  : 10 cases in 0.018s
cppkh     : 0.012s, exit=0, results=10
JavaKh    : 0.812s, exit=0, results=10, runner=native
compare: OK
```

## Full Test

Run every default case:

```sh
python tools/test_kh_consistency.py --build-cpp --out-dir benchmark/full
```

Useful slices:

```sh
python tools/test_kh_consistency.py --limit 1000 --out-dir benchmark/first1000
python tools/test_kh_consistency.py --last 1000 --out-dir benchmark/last1000
python tools/test_kh_consistency.py --start 6615 --limit 100 --out-dir benchmark/com100
```

## Important Options

```text
--input FILE              Input PD-code collection.
--labels FILE             Optional labels file for mismatch reports.
--cpp-exe PATH            Path to javakh_cpp / javakh_cpp.exe.
--build-cpp               Build cppkh automatically if no executable is found.
--java-root DIR           Bundled JavaKh reference directory.
--java COMMAND            Java command, default: java.
--javac COMMAND           javac command for the batch runner.
--java-xmx SIZE           Java heap, default: 4g.
--java-runner MODE        auto, native, batch, or process.
--java-keep-cache         Keep JavaKh's cache between PD codes.
--limit N                 Run at most N cases.
--start N                 Start at 1-based case N.
--last N                  Run the last N cases.
--threads N               Value passed to cppkh --threads.
--timeout-sec N           Per-program timeout.
--no-external-simplify    Disable external R1/nugatory simplification.
--out-dir DIR             Directory for outputs and reports.
```

## Java Runner Modes

`--java-runner auto` is the default. It uses the patched bundled JavaKh entry
point directly:

```sh
java -cp reference/javakh org.katlas.JavaKh.JavaKh -f prepared.pd
```

That patched entry point reads one PD code per non-empty line, clears JavaKh's
work `cache/` between PD codes by default, and prints a single-line `ERROR`
record for any PD code that fails without stopping later cases.

Use `--java-runner batch` to compile and run
`reference/javakh/CppkhJavaKhBatchRunner.java`. This mode is kept for comparing
against the older helper path and requires `javac`.

Use `--java-runner process` when you want the most isolated behavior. It starts
a new Java process for every PD code, which is much slower.

Use `--java-keep-cache` only when you explicitly want to test JavaKh's disk
cache behavior. The original cache can be unsafe across unrelated PD codes, so
the default test clears it between cases.

## Outputs

The output directory contains:

```text
prepared.pd        Normalized PD codes actually sent to both programs.
labels.txt         Labels used in mismatch reports.
cppkh.out          Raw cppkh stdout.
cppkh.err          Raw cppkh stderr.
javakh.out         Raw JavaKh stdout.
javakh.err         Raw JavaKh stderr.
summary.txt        Human-readable timing and result summary.
summary.json       Machine-readable summary.
mismatches.txt     Written only when outputs differ.
```

The script exits with status `0` only when both programs exit successfully and
all quoted homology strings match.
