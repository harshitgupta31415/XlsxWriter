"""Screen a uniform-row-height fast path without changing the checkout."""

from __future__ import annotations

import argparse
import ast
import cProfile
import csv
import gc
import hashlib
import inspect
import io
import json
import platform
import pstats
import subprocess
import sys
import textwrap
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from urllib.request import urlopen
from zipfile import ZipFile

from benchmark_cpu import RotatingCores

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent / 'XlsxWriter'
sys.path.insert(0, str(REPO))
import xlsxwriter
from xlsxwriter.worksheet import Worksheet

URL = ('https://raw.githubusercontent.com/mwaskom/seaborn-data/'
       '71e2436a092d714350de0fc409ca8a8714e7e78f/taxis.csv')
ORIGINAL = Worksheet._position_object_pixels


def proposal():
    tree = ast.parse(textwrap.dedent(inspect.getsource(ORIGINAL)))
    hits = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Attribute) and node.test.attr == 'row_size_changed':
            node.test = ast.parse('self.row_size_changed and (self.row_sizes or row_start < 0)', mode='eval').body
            hits += 1
    assert hits == 1
    namespace = dict(ORIGINAL.__globals__)
    exec(compile(ast.fix_missing_locations(tree), '<uniform row proposal>', 'exec'), namespace)
    return namespace[ORIGINAL.__name__]


def load_data():
    fixture = ROOT / 'taxis.csv'
    if not fixture.exists():
        with urlopen(URL, timeout=30) as response:
            fixture.write_bytes(response.read())
    raw = fixture.read_bytes()
    records = list(csv.reader(io.StringIO(raw.decode('utf-8'))))
    headers, rows = records[0], records[1:]
    # Flag actual missing fields, zero passengers, zero distance and non-positive fare.
    comments = []
    for index, row in enumerate(rows, 1):
        for col, value in enumerate(row):
            if not value:
                comments.append((index, col, 'Missing value: please check the source record.'))
        for col in (2, 3, 4):
            if row[col] and float(row[col]) <= 0:
                comments.append((index, col, 'Non-positive value: please check the source record.'))
    return headers, rows, comments, hashlib.sha256(raw).hexdigest()


def build(case, data):
    headers, records, comments, _ = data
    output = io.BytesIO()
    book = xlsxwriter.Workbook(output, {'in_memory': True, 'strings_to_urls': False})
    book.set_properties({'created': datetime(2026, 1, 1, tzinfo=timezone.utc)})
    sheet = book.add_worksheet('Taxi data review')
    if case['height'] is not None:
        sheet.set_default_row(case['height'])
    if case['custom_row']:
        sheet.set_row(0, 30)
    sheet.freeze_panes(1, 0)
    sheet.set_column(0, 13, 19)
    header_format = book.add_format({'bold': True})
    sheet.write_row(0, 0, headers, header_format)
    for index, row in enumerate(records[:case['rows']], 1):
        sheet.write_row(index, 0, row)
    if case['comments']:
        for row, col, text in comments:
            if row <= case['rows']:
                sheet.write_comment(row, col, text)
    sheet.autofilter(0, 0, case['rows'], len(headers) - 1)
    book.close()
    return output.getvalue()


def content(raw):
    with ZipFile(io.BytesIO(raw)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def verify_geometry(changed):
    checks = 0
    for height in (None, 15, 17.25, 24, 32):
        for custom in (False, True):
            sheet = Worksheet()
            if height is not None:
                sheet.set_default_row(height)
            if custom:
                sheet.set_row(0, 27)
                sheet.set_row_pixels(4, 12.25)
                sheet.set_row(7, 0)
            sheet.set_column_pixels(1, 2, 71.5)
            for row in (-1, 0, 1, 4, 8, 100, 9999):
                for offset in (-25, 0, 50):
                    for anchor in (0, 1, 2, 3, 4):
                        args = (3, row, 5, offset, 128, 74, anchor)
                        assert ORIGINAL(sheet, *args) == changed(sheet, *args), (height, custom, args)
                        checks += 1
    return checks


def save(report):
    (ROOT / 'xlsxwriter_uniform_rows_probe.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    lines = ['XlsxWriter uniform-row-height screening', '',
             'Complete XLSX creation from the pinned taxi dataset, not just positioning.',
             'Each workbook archive member is compared byte-for-byte outside measurement.',
             'Synthetic report workflow using real records; not a deployed-application measurement.',
             'Peak is newly traced Python allocation during creation, not process RAM.', '',
             '| Rows x columns | Comments | Default height | Custom header height | Base time | Proposed time | Speed | Base peak | Proposed peak | Memory |',
             '|---|---:|---:|---|---:|---:|---|---:|---:|---|']
    for row in report['results']:
        base, new = row['base'], row['proposal']
        bt, nt = median(base['time_ns']), median(new['time_ns'])
        bm, nm = median(base['peak_bytes']), median(new['peak_bytes'])
        speed = f'{bt / nt:.3f}x faster' if bt >= nt else f'{nt / bt:.3f}x slower'
        memory = f'{nm / bm:.3f}x more' if nm >= bm else f'{bm / nm:.3f}x less'
        lines.append(f"| {row['rows']} x 14 | {row['comment_count']} | {row['height']} | {row['custom_row']} | {bt / 1e6:.3f} ms | {nt / 1e6:.3f} ms | {speed} | {bm / 1048576:.3f} MiB | {nm / 1048576:.3f} MiB | {memory} |")
    (ROOT / 'xlsxwriter_uniform_rows_probe.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    assert args.repeats >= 5
    changed = proposal()
    data = load_data()
    methods = {'base': ORIGINAL, 'proposal': changed}
    cores = RotatingCores()
    report = {'metadata': {'python': platform.python_version(), 'platform': platform.platform(),
                           'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
                           'data_url': URL, 'data_sha256': data[3], 'repeats': args.repeats,
                           'cores': [hex(mask) for mask in cores.pairs],
                           'started_utc': datetime.now(timezone.utc).isoformat()},
              'geometry_comparisons': 0, 'results': []}
    try:
        cores.rotate()
        report['geometry_comparisons'] = verify_geometry(changed)
        cases = [{'rows': n, 'height': 24, 'comments': True, 'custom_row': False} for n in (1000, 3000, len(data[1]))]
        cases += [{'rows': len(data[1]), 'height': height, 'comments': comments, 'custom_row': custom}
                  for height, comments, custom in ((None, True, False), (24, False, False), (24, True, True))]
        for index, case in enumerate(cases, 1):
            cores.rotate()
            expected = None
            for name, method in methods.items():
                Worksheet._position_object_pixels = method
                raw = build(case, data)
                if expected is None:
                    expected = content(raw)
                else:
                    assert content(raw) == expected
            row = {**case, 'comment_count': sum(r <= case['rows'] for r, _, _ in data[2]) if case['comments'] else 0,
                   'output_sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in expected.items()},
                   'base': {'time_ns': [], 'peak_bytes': []}, 'proposal': {'time_ns': [], 'peak_bytes': []}, 'masks': []}
            for repeat in range(args.repeats):
                row['masks'].append(cores.rotate())
                order = ('base', 'proposal') if repeat % 2 == 0 else ('proposal', 'base')
                for name in order:
                    Worksheet._position_object_pixels = methods[name]
                    gc.collect()
                    gc.disable()
                    try:
                        start = time.perf_counter_ns()
                        raw = build(case, data)
                        elapsed = time.perf_counter_ns() - start
                    finally:
                        gc.enable()
                    assert content(raw) == expected
                    row[name]['time_ns'].append(elapsed)
                for name in order:
                    Worksheet._position_object_pixels = methods[name]
                    gc.collect()
                    tracemalloc.start()
                    try:
                        raw = build(case, data)
                        peak = tracemalloc.get_traced_memory()[1]
                    finally:
                        tracemalloc.stop()
                    assert content(raw) == expected
                    row[name]['peak_bytes'].append(peak)
                print(f"case {index}/{len(cases)} run {repeat + 1}/{args.repeats}: {(index - 1 + (repeat + 1) / args.repeats) / len(cases):.1%} complete", flush=True)
            report['results'].append(row)
            save(report)
        Worksheet._position_object_pixels = ORIGINAL
        profiler = cProfile.Profile()
        profiler.runcall(build, cases[2], data)
        stream = io.StringIO()
        pstats.Stats(profiler, stream=stream).sort_stats('cumulative').print_stats(22)
        report['base_profile'] = stream.getvalue()
        report['metadata']['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save(report)
        print((ROOT / 'xlsxwriter_uniform_rows_probe.txt').read_text(), flush=True)
    finally:
        Worksheet._position_object_pixels = ORIGINAL
        cores.restore()


if __name__ == '__main__':
    main()
