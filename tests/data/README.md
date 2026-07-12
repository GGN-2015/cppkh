# Test PD-Code Data

`test_pdcode.txt` contains one normalized `PD[...]` code per line.
`pd_codes_10_3_links.txt` contains normalized `PD[...]` codes for the
10_3 link test set.

Data sources:

- Lines 1-6614 come from the original `javakh_ori/test_pdcode.txt`. The original
  `0000001.txt: [[...]]` prefix format was normalized by removing the prefix
  and rewriting each crossing as `X[...]`.
- Lines 6615-8397 come from
  <https://github.com/TopologicalKnotIndexer/com_pd_code_list/blob/main/data/com_pd_code_list.txt>.
  The original `[knot-name|[[...]]]` format was normalized to `PD[X[...],...]`.

`test_pdcode.labels.txt` has the same number of lines and preserves the
original labels for mismatch reports.

`pd_codes_10_3_links.labels.txt` preserves the original labels from
`pd_codes_10_3.txt`, whose source lines use `label: [[...]]` format with the
PD payload after the colon.
