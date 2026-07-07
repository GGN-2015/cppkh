# Bundled JavaKh Reference

This directory contains the bundled JavaKh class-file runtime used as the
reference implementation for cross-checking `cppkh`.

Included runtime pieces:

- `org/katlas/JavaKh/**/*.class`
- supporting `com/`, `gnu/`, and `net/` class files
- the four jar dependencies under `jars/`
- `CppkhJavaKhBatchRunner.java`, a tiny test helper that invokes the bundled
  `org.katlas.JavaKh.JavaKh.main()` for many prepared PD codes.

The bundled `org/katlas/JavaKh/JavaKh.class` is patched from the original class
so `PD.txt` is read line by line: each non-empty line is treated as one
independent PD code. The source used for that patched entry point is kept at
`org/katlas/JavaKh/JavaKh.java`.

The batch runner does not reimplement JavaKh. It rewrites `PD.txt` for each
case and calls the JavaKh entry point. The Python test script compiles the
helper into its benchmark output directory when `javac` is available. It clears
JavaKh's work `cache/` between cases by default because JavaKh's disk cache is
not safe to reuse across unrelated PD codes.

## Input file behavior

The patched `org.katlas.JavaKh.JavaKh` entry point reads one PD code per
non-empty line. It defaults to `PD.txt` in the current working directory. A
different input file can be selected with `-f <path>`, `--pd-file <path>`, or a
positional `[PD_FILE]` argument.

If one PD code fails, JavaKh prints a single-line
`ERROR line=<n> pd=<code> error=<message>` record and continues with later PD
codes.
