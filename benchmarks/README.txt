Uniform-height worksheet object positioning
===========================================

Issue: https://github.com/jmcnamara/XlsxWriter/issues/1210
Code branch: harshitgupta31415/speed-up-object-positioning-on-uniform-height-sheets
Base: 5d4606d89a955226d2d0825a0f44309043ae7251
Code commit: a3b410ce09323e58b0c42dbe1a94259a2f4c7803

The upstream PR only changes the positioning method and its regression tests.
These benchmark files are kept in a separate fork branch.

The main results are xlsxwriter_uniform_rows_results.json and .md. They compare
the pinned base method against the actual method in the code checkout. Both
versions use the same remaining workbook code. The runner checks the changed
method body before starting and records the source and runner SHA256 hashes.

What was measured
-----------------

This creates a complete data-review workbook from 6,433 public taxi records,
with 14 columns and 333 comments on missing or non-positive values. It is a
constructed reporting workflow using real data, not a measurement of a
deployed pandas, Polars or Data Stewardship Wizard application.

One case uses a uniform custom default row height. The other adds a custom
header-row height, which keeps the original positioning loop. All results,
including slower cases, are kept. There is no claim of a general speedup.

The timing covers creating the workbook, writing every cell/comment and
closing/compressing it. CSV loading, installing each method, and comparing
output are outside the timer. Each uncompressed archive member is compared
byte-for-byte. ZIP container metadata is not part of that equality check.

The recorded run used Python 3.15.0 on Windows 11. There is one process,
restricted to two physical CPU cores at a time, with rotating pairs. Each
pair gets five timing runs per version per case (20 here), with order
alternating on successive visits. Five separate traced-allocation runs per
version per case measure memory. Peak means newly traced Python allocations
during workbook creation, not total process RAM. Per-case memory medians are
repeated in the table's per-core rows; they are not separate per-core memory
measurements. Every individual sample is in the JSON.

The runner also compares 1,050 geometry cases, 22 output/error cases, and
100 complete workbooks using different sizes, heights, row overrides and
comment settings. These are correctness checks, not 100 timed benchmarks.

How to run it again
-------------------

The affinity helper is Windows-specific and requires at least two available
physical cores. It discovers the core pairs rather than hardcoding masks.
The recorded masks are in the JSON. No GPU or parallel worker pool is used.

Keep two sibling folders:

  C:/xlsx-position-benchmark/XlsxWriter/  code checkout
  C:/xlsx-position-benchmark/benchmarks/  files from this directory

Copy xlsxwriter_uniform_rows.py, xlsxwriter_uniform_rows_probe.py and
benchmark_cpu.py into benchmarks. The probe file supplies the fixture loader
and report builder; importing it does not run the historical benchmark.
The CSV is downloaded from a pinned public commit on the first run; internet
access is needed then. Its URL and SHA256 are recorded in the results.

PowerShell commands:

git clone --branch harshitgupta31415/speed-up-object-positioning-on-uniform-height-sheets https://github.com/harshitgupta31415/XlsxWriter.git C:/xlsx-position-benchmark/XlsxWriter
git -C C:/xlsx-position-benchmark/XlsxWriter checkout a3b410ce09323e58b0c42dbe1a94259a2f4c7803
Set-Location C:/xlsx-position-benchmark/XlsxWriter
python -m venv .venv
& ./.venv/Scripts/python.exe -m pip install -e . pytest
& ./.venv/Scripts/python.exe -X utf8 ../benchmarks/xlsxwriter_uniform_rows.py

Use Python 3.15.0 to match the recorded version. The runner overwrites local
result files, so keep the recorded JSON/MD elsewhere if you want to compare
them with a fresh run.

For tests, also copy run_xlsxwriter_tests.py:

& ./.venv/Scripts/python.exe -X utf8 ../benchmarks/run_xlsxwriter_tests.py
& ./.venv/Scripts/python.exe -X utf8 ../benchmarks/run_xlsxwriter_tests.py --base

The base command injects only the pinned original method and excludes the
new regression-test file, whose lookup-count assertion intentionally fails
on the original algorithm. It reruns the original 1,787 tests. The PR command
runs the new tests too. Test setup rotates core pairs every 200 tests.

Earlier screening
-----------------

The probe and recheck scripts/results are retained as historical evidence,
including all smaller-case losses and mixed controls. They used in-process
prototypes on the original checkout; they are NOT current-commit timings.
The recheck prototype has the same method body as the final fix. The probe
used a different condition for negative row indexes. Only the main runner
compares the actual changed source with the pinned base.

To replay those historical runs, first check out the base commit above in
the sibling XlsxWriter folder, then run the corresponding script. Restore
the code commit before running the main benchmark again. Their JSON files
record all samples and the original environment/fixture details available
at the time. Do not combine historical and final samples into one median.
