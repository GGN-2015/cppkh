# Test PD-Code Data

`test_pdcode.txt` contains one normalized `PD[...]` code per line.

Data sources:

- Lines 1-6614 come from the original `javakh_ori/test_pdcode.txt`. The original
  `0000001.txt: [[...]]` prefix format was normalized by removing the prefix
  and rewriting each crossing as `X[...]`.
- Lines 6615-8397 come from
  <https://github.com/TopologicalKnotIndexer/com_pd_code_list/blob/main/data/com_pd_code_list.txt>.
  The original `[knot-name|[[...]]]` format was normalized to `PD[X[...],...]`.

`test_pdcode.labels.txt` has the same number of lines and preserves the
original labels for mismatch reports.
