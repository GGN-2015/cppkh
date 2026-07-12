# Command-Line Interface

`cppkh` accepts PD code from a literal command-line string, a file, or every
`.txt` / `.pd` file in a directory.

## Inputs

Compute one PD code:

```sh
cppkh --pd-code "PD[X[1,5,2,4],X[3,1,4,6],X[5,3,6,2]]"
```

Compute one file:

```sh
cppkh --pd-file PD.txt
```

Compute every `.txt` and `.pd` file in a directory:

```sh
cppkh --pd-dir samples
```

If no input is given, the CLI tries to read `PD.txt` from the current working
directory for compatibility with JavaKh-style workflows.

Each input file may contain one or more standard `PD[...]` lines. Labels before
a colon are allowed when the text after the colon is the PD payload used by the
benchmark helper.

## Options

```text
--pd-code CODE          Compute a literal PD[...] string.
--pd-file FILE          Read one input file.
--pd-dir DIR            Read every .txt and .pd file in a directory.
--ordered, -O           Keep the crossing order, like JavaKh -O.
--quiet, -q             Suppress progress messages.
--profile               Print per-PD timing counters to stderr.
--threads N             Accepted for compatibility; the core algorithm is serial.
--threads auto          Accepted for compatibility; the core algorithm is serial.
--simplify-pd           Enable PD simplification (default).
--no-simplify-pd        Disable default PD simplification.
--raw-pd                Alias for --no-simplify-pd.
--print-simplified-pd   Print the simplified PD code instead of homology.
--help, -h              Show CLI help.
```

## PD Simplification

R1-move removal and then nugatory-crossing removal are enabled by default.
The order is intentional:

1. Remove R1 moves.
2. Remove nugatory crossings.
3. Compute Khovanov homology.

Use `--no-simplify-pd` only when the input has already been simplified outside
`cppkh`. For JavaKh comparisons, the benchmark script can run the external
Python simplifiers first and then pass `--no-simplify-pd` to `cppkh`, ensuring
both programs receive the same simplified PD code.

See [Algorithm Notes](ALGORITHM.md) for the distinction between diagram-level
PD simplification and algebraic Khovanov-complex reduction.

## Output

For one PD code, the CLI prints one quoted polynomial:

```text
"q^1*t^0*Z[0] + q^3*t^0*Z[0] + q^5*t^2*Z[0] + q^7*t^3*Z[2] + q^9*t^3*Z[0]"
```

For multiple jobs, each line starts with the input label followed by a tab and
the quoted polynomial.
