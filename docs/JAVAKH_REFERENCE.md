# Bundled JavaKh Reference

`cppkh` includes a bundled JavaKh class-file runtime under:

```text
reference/javakh/
```

This runtime is only used as a reference implementation for compatibility
checks. The normal `cppkh` executable does not require Java.

## Patched Entry Point

The bundled `org.katlas.JavaKh.JavaKh` class is patched from the original
JavaKh entry point in four ways:

- It reads input files one PD code per non-empty line.
- It accepts an input path from the command line.
- If one PD code fails, it prints a single-line error and continues with later
  PD codes.
- It resolves crossing signs by tracing directed PD edge incidences with the
  same convention as SageMath instead of comparing `b` and `d` numerically.

The patched source is kept at:

```text
reference/javakh/org/katlas/JavaKh/JavaKh.java
reference/javakh/org/katlas/JavaKh/PDOrientation.java
```

The compiled Java 8-compatible class file is:

```text
reference/javakh/org/katlas/JavaKh/JavaKh.class
reference/javakh/org/katlas/JavaKh/PDOrientation.class
```

Pass `--print-crossing-signs` / `-S` to print the resolved sign list for each
input instead of constructing its Khovanov complex.

## Running JavaKh Directly

From the repository root, build the classpath from `reference/javakh` and its
four jar dependencies.

Windows PowerShell:

```powershell
$javaRoot = Resolve-Path reference\javakh
$cp = ($javaRoot,
  "$javaRoot\jars\log4j-1.2.12.jar",
  "$javaRoot\jars\commons-io-1.2.jar",
  "$javaRoot\jars\commons-cli-1.0.jar",
  "$javaRoot\jars\commons-logging-1.1.jar") -join [IO.Path]::PathSeparator
java -Xmx4g -cp $cp org.katlas.JavaKh.JavaKh -f path\to\codes.pd
```

Linux / macOS:

```sh
JAVA_ROOT=reference/javakh
CP="$JAVA_ROOT:$JAVA_ROOT/jars/log4j-1.2.12.jar:$JAVA_ROOT/jars/commons-io-1.2.jar:$JAVA_ROOT/jars/commons-cli-1.0.jar:$JAVA_ROOT/jars/commons-logging-1.1.jar"
java -Xmx4g -cp "$CP" org.katlas.JavaKh.JavaKh -f path/to/codes.pd
```

## Input File Rules

If no input path is supplied, JavaKh reads `PD.txt` from the current working
directory:

```sh
java -Xmx4g -cp "$CP" org.katlas.JavaKh.JavaKh
```

These forms are equivalent:

```sh
java -Xmx4g -cp "$CP" org.katlas.JavaKh.JavaKh -f path/to/codes.pd
java -Xmx4g -cp "$CP" org.katlas.JavaKh.JavaKh --pd-file path/to/codes.pd
java -Xmx4g -cp "$CP" org.katlas.JavaKh.JavaKh path/to/codes.pd
```

Each non-empty line should be a standard PD code:

```text
PD[X[1,5,2,4],X[3,1,4,6],X[5,3,6,2]]
PD[]
```

Blank lines are ignored.

## Output Rules

Successful computations print JavaKh's quoted homology polynomial, for example:

```text
"q^1*t^0*Z[0] + q^3*t^0*Z[0] + q^5*t^2*Z[0] + q^7*t^3*Z[2] + q^9*t^3*Z[0]"
```

JavaKh also prints progress text on stdout. Test scripts should extract quoted
strings when comparing results.

If a PD code fails, the patched entry point prints one error line and continues:

```text
ERROR line=2 pd=this-is-not-pd error=java.lang.StringIndexOutOfBoundsException: Range [0, -1) out of bounds for length 14
```

The error line contains the 1-based input line number, the original one-line PD
text, and the Java exception summary.

## Cache Behavior

JavaKh's disk cache is local to the process working directory and is not safe to
reuse across unrelated PD codes. The patched entry point clears `cache/` before
each PD code when disk caching is enabled.

## Use In The Test Runner

`tools/test_kh_consistency.py` uses this patched multiline JavaKh reader by
default:

```sh
python tools/test_kh_consistency.py --build-cpp --limit 10
```

The default `--java-runner auto` mode runs:

```text
org.katlas.JavaKh.JavaKh -f prepared.pd
```

Use `--java-runner batch` only when you explicitly want to compare against the
older helper-based path. Use `--java-runner process` for the slowest but most
isolated mode, which starts a new JVM for each PD code.
