# Bundled JavaKh Reference

This directory contains the bundled JavaKh class-file runtime used as the
reference implementation for cross-checking `cppkh`.

Included runtime pieces:

- `org/katlas/JavaKh/**/*.class`
- supporting `com/`, `gnu/`, and `net/` class files
- the four jar dependencies under `jars/`
- `CppkhJavaKhBatchRunner.java`, a tiny test helper that invokes the original
  `org.katlas.JavaKh.JavaKh.main()` for many prepared PD codes.

The batch runner does not reimplement JavaKh. It rewrites `PD.txt` for each
case and calls the original JavaKh entry point. The Python test script compiles
the helper into its benchmark output directory when `javac` is available. It
clears JavaKh's work `cache/` between cases by default because the original
disk cache is not safe to reuse across unrelated PD codes.
