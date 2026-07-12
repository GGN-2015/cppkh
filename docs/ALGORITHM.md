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
