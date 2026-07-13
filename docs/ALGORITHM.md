# Algorithm Notes

This document records the computation path implemented by `src/main.cpp`.
`cppkh` follows the integer JavaKh / Bar-Natan cobordism-complex workflow and
then formats the resulting homology in JavaKh-compatible notation.

## Input And Diagram Simplification

PD codes are parsed into zero-based arc labels internally. A valid PD code must
have four entries per crossing and every arc label must occur exactly twice.

### Oriented crossing signs

Crossing signs follow the SageMath PD convention. For `X[a,b,c,d]`, `a` is the
incoming under-edge and `c` is the outgoing under-edge. `cppkh` propagates that
orientation through matching edge incidences and opposite slots at every
crossing. Components which never pass under are oriented deterministically from
their lowest-labelled unassigned edge. The sign is then determined from the
actual incoming/outgoing over-edge incidence, including repeated-label R1
crossings.

This preprocessing is linear in the number of crossings. It does not compare
the numeric values of `b` and `d`, so arc relabelling cannot change the signs.
The bundled JavaKh patch uses the same traversal in `PDOrientation.java`.

By default, `cppkh` simplifies the diagram before constructing the Khovanov
complex:

1. Remove R1 crossings until none remain.
2. Renumber the remaining arcs in a deterministic traversal order.
3. Detect nugatory crossings by removing one crossing and checking whether the
   underlying incidence graph gains a connected component.
4. Splice out each detected nugatory crossing and renumber again.

Signs are computed on the original oriented PD code and carried alongside
surviving crossings during simplification. Renumbering therefore cannot reverse
a component or change a surviving crossing sign.

This is a diagram-level simplification. It reduces the input before the complex
is built. It is separate from the algebraic simplification of the Khovanov
complex described below.

Use `--no-simplify-pd` or `--raw-pd` when another tool has already prepared the
exact PD code that should be sent to the core algorithm. The JavaKh consistency
tests use this mode after the Python-side simplifiers have prepared the same
input for both runtimes.

The CLI also exposes independent `--[no-]simplify-r1` and
`--[no-]simplify-nugatory` switches. Nugatory removal starts with R1 cleanup,
which preserves the established `pd-code-delete-nugatory` semantics when only
that operation is requested.

## Crossing Order

The default algorithm does not keep the input crossing order. It builds the
diagram as a growing tangle and chooses the next crossing with a bounded
lookahead heuristic:

- Prefer crossings that share more boundary arcs with the current tangle.
- For ties, look ahead up to three future additions and prefer the order that
  keeps future attachment counts larger.
- Reject candidates that would violate the simply connected prefix condition
  required by the tangle-composition step.

The purpose is to reduce intermediate girth and the size of intermediate
complexes. It does not change the homology result. Use `--ordered` / `-O` to
keep the input order for JavaKh-style comparisons.

## Complex Construction

For a non-empty diagram, `generateFast` starts from the one-crossing positive or
negative complex and then composes one additional crossing at a time. After each
composition it immediately reduces the intermediate complex before adding the
next crossing.

For an empty `PD[]`, `cppkh` builds the one-circle complex directly and reduces
it, producing the unknot result.

## Complex Simplification

The complex reduction pass is algebraic and independent from PD-code
simplification:

1. `deLoop` replaces each smoothing with closed circles by the direct sum of
   circle-free smoothings, shifting the quantum grading by the usual
   plus/minus circle contributions and composing the adjacent differentials
   through the de-looping cobordisms.
2. `LCCC::reduce` applies the local cobordism relations used by JavaKh,
   including killing impossible closed components, multiplying torus
   contributions by `2`, moving dots to boundary components, and expanding
   multi-boundary components by neck-cutting.
3. `blockReductionLemma` finds row/column-disjoint isomorphism entries with
   coefficient `+/-1` and cancels them as a block. This is the same reduction
   lemma used by JavaKh, batched to avoid repeated full scans when independent
   cancellations are available.
4. Matrix rows remain sparse and sorted. Cache tables canonicalize caps and
   cobordisms so repeated compositions share objects instead of rebuilding the
   same topology.

The runtime `--profile` flag reports timings for the main parts of this path:
generation, composition, de-looping, matrix reduction, block cancellation, and
cobordism/LCCC reductions.

## Homology Extraction

After the cobordism complex is reduced, `KhForZ` converts each remaining
cobordism differential into an integer matrix and computes Smith normal form.
Free summands are printed as `Z[0]`; torsion summands are printed as
`Z[n]`. Terms are grouped by quantum degree `q` and homological degree `t` to
match JavaKh's quoted output format.

## Threading Boundary

Builds may use different thread backends for platform compatibility, but the
validated core Khovanov computation intentionally runs one PD code serially.
The accepted `--threads` option is retained for CLI and Python-package
compatibility. Benchmarking showed row-level parallelism was slower for the
current implementation and data set.

## Bundled JavaKh Modifications And Debugging Record

The Java runtime under `reference/javakh/` is not an untouched JavaKh binary.
It is a compatibility reference patched for repeatable batch testing and for
the corrected oriented-link crossing convention. This section is the source of
truth for every intentional difference from the bundled upstream classes.

### Mathematical algorithm change: crossing orientation

The original `Komplex.getSigns(int[][])` infers the sign of
`X[a,b,c,d]` from numeric comparisons between `b` and `d`. That works only when
arc numbering happens to encode the over-strand direction and fails for general
link PD codes. It can also make an equivalent arc relabelling change the
absolute `q,t` grading.

The patched entry point no longer calls that method. It calls
`PDOrientation.getSigns(pd)`, which performs the following linear traversal:

1. Record the two crossing incidences of every arc label.
2. Mark slot `0` of each crossing as the incoming under-edge and slot `2` as
   the outgoing under-edge, following the SageMath PD convention.
3. Propagate directions through the opposite slot of each crossing and through
   the matching incidence of each arc.
4. Deterministically orient a component which never passes under from the first
   occurrence of its lowest-labelled unassigned edge.
5. Determine the crossing sign from the actual direction at over-edge slot
   `3`, with the SageMath repeated-label rules for R1 crossings.
6. Reject malformed PD incidence data instead of silently guessing a sign.

The implementation uses preallocated arrays and an integer queue. For standard
compact PD labels its time and memory costs are linear in the crossing count.
It does not add a shared cache or any inter-process synchronization.

The original `Komplex.getSigns` method still exists inside the historical
`Komplex.class`; replacing that large upstream class was intentionally avoided.
The supported patched JavaKh executable path is
`org.katlas.JavaKh.JavaKh`, which always bypasses the legacy method. Code which
calls `Komplex.getSigns` directly is still calling the legacy algorithm and is
not the patched reference path.

No other JavaKh chain-complex mathematics was changed. `Komplex.generateFast`,
composition, de-looping, cobordism relations, cancellation, Smith form, and
JavaKh output formatting remain the bundled upstream implementation; only the
crossing-sign array supplied to `generateFast` is corrected.

### Entry-point reliability and batch behavior

`reference/javakh/org/katlas/JavaKh/JavaKh.java` also contains operational
patches needed for deterministic comparisons:

| Area | Patched behavior | Reason |
| --- | --- | --- |
| Input | Reads one PD code from every non-empty line | Avoid one JVM start per case |
| Input path | Accepts `-f`, `--pd-file`, or a positional path | Test arbitrary prepared data files |
| Failure isolation | Catches failures per line and continues | Preserve later results in long runs |
| Error output | Prints one-line `ERROR line=... pd=... error=...` records | Make the failing input reproducible |
| Disk cache | Clears the working-directory `cache/` before each PD code and after failures | Prevent stale JavaKh cache data crossing job boundaries |
| Logging | Keeps `-i` and `-d` as explicit INFO/DEBUG controls | Keep normal comparison output parseable |
| Sign diagnostics | Adds `-S` / `--print-crossing-signs` | Inspect orientation without constructing a complex |
| Build target | Commits Java 8-compatible `JavaKh.class` and `PDOrientation.class` | Run the same patched entry point without recompiling |

The cache cleanup is process-local filesystem hygiene. It is not a shared
runtime cache and does not introduce a cross-process lock.

### Matching CppKh and Python changes

CppKh implements the same incidence traversal in `getSigns`. When diagram
simplification is enabled, CppKh computes signs on the original oriented PD
code and erases sign entries alongside removed crossings. Surviving signs are
therefore not recomputed from renumbered arcs. The `cppkh-interface` package and
the ctypes wrapper call this C++ implementation and contain no independent sign
algorithm.

Both native programs expose `--print-crossing-signs`. The focused test compares
these lists directly before comparing homology, so two implementations cannot
pass merely by reproducing the same final text through unrelated grading
conventions.

### Debugging evidence and regression coverage

The minimal two-component regression is:

```text
PD[X[1,4,2,3],X[2,4,1,3]]
```

The numeric-label algorithm assigns `[1,1]`; incidence tracing assigns
`[-1,1]`. The regression set also includes a three-component SageMath example,
an arbitrary relabelling of that example, and both repeated-label R1 sign
forms. The relabelled and original diagrams must have identical signs and
homology.

Run the focused diagnostics with:

```sh
python tools/test_pd_orientation.py --cpp-exe path/to/cppkh
```

Before releasing `cppkh-interface 0.1.2`, the focused sign and homology tests
passed for CppKh, patched JavaKh, `cppkh-interface`, and the ctypes wrapper. The
full prepared collection then produced exact matching output on all `8397`
cases for CppKh, patched JavaKh, and `cppkh-interface`.

PyPI `javakh-interface` still bundles legacy JavaKh. Its differences are kept
as informational reports and do not gate the patched three-way comparison.
Tests which claim patched JavaKh compatibility must use the classes in
`reference/javakh/`, not the JavaKh copy embedded in that external package.

### cppkh-interface 0.1.3 dependency removal

Release `0.1.3` removes the runtime dependencies on `cpp-simple-interface`,
`pd-code-sanity`, `pd-code-de-r1`, and `pd-code-delete-nugatory`. The package
uses the Python standard library to discover and invoke a C++14 compiler. R1
and nugatory simplification, including mixed option combinations and PD
validation, now run in the packaged copy of the canonical `src/main.cpp`.

Compiled executables remain content-addressed by source, compiler identity,
flags, and platform. Competing processes compile to distinct temporary files
and atomically publish the same immutable cache entry; there is no global lock
or cross-process mutable algorithm cache. Before release, all four
`de_r1`/`de_k8` combinations were compared on all 8397 default PD cases against
the former Python simplifiers with zero differences. A clean wheel installation
also matched CppKh and patched JavaKh on the homology output of all 8397 cases.

## Correctness Tests

The main compatibility runner is:

```sh
python tools/test_kh_consistency.py --javakh-interface-python path/to/python
```

It requires `cppkh`, bundled patched JavaKh, and local `cppkh-interface` to
match on the selected input, then checks the PyPI `javakh-interface` package on
a deterministic random sample.
The default `javakh-interface` sample size is 100 with seed `20260712`. Since
that external package still bundles legacy JavaKh, its differences are
informational and do not determine the runner's exit status.

The focused orientation regression is:

```sh
python tools/test_pd_orientation.py --cpp-exe path/to/cppkh
```

It checks SageMath-derived crossing signs, invariance under arc relabelling,
and matching homology from CppKh, bundled JavaKh, and the local
`cppkh-interface` package.
