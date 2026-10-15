"""Recheck the useful workflow with integer validation and balanced core pairs."""
from __future__ import annotations

import argparse
import ast
import gc
import hashlib
import inspect
import json
import platform
import sys
import subprocess
import textwrap
import time
import tracemalloc
from pathlib import Path
from statistics import median

import xlsxwriter_uniform_rows_probe as probe
from benchmark_cpu import RotatingCores

ROOT = Path(__file__).resolve().parent


def proposal():
    tree = ast.parse(textwrap.dedent(inspect.getsource(probe.ORIGINAL)))
    hits = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Attribute) and node.test.attr == 'row_size_changed':
            branch = ast.parse('if not self.row_sizes:\n    y_abs += self.default_row_height * len(range(row_start))\nelse:\n    pass').body[0]
            branch.orelse = node.body
            node.body = [branch]
            hits += 1
    assert hits == 1
    namespace = dict(probe.ORIGINAL.__globals__)
    exec(compile(ast.fix_missing_locations(tree), '<uniform rows recheck>', 'exec'), namespace)
    return namespace[probe.ORIGINAL.__name__]


def save(report):
    (ROOT / 'xlsxwriter_uniform_rows_recheck.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    lines = ['Uniform row-height focused recheck', '',
             'Real taxi data, complete 6,433 x 14 workbook creation, 333 comments.',
             '20 timing runs/version/case: five on each rotating two-physical-core pair.',
             'Five separate allocation runs/version/case. Repository source unchanged.',
             'Each archive member matches byte-for-byte. Setup, patch installation and checks are outside timing.',
             'This is a constructed report using public records, not a benchmark of a deployed application.', '',
             '| Custom header height | CPU mask | Base time | Proposed time | Speed |',
             '|---|---|---:|---:|---|']
    for row in report['results']:
        for mask in sorted(set(row['masks'])):
            selected = [i for i, value in enumerate(row['masks']) if value == mask]
            bt, nt = [median(row[n]['time_ns'][i] for i in selected) for n in ('base', 'proposal')]
            speed = f'{bt/nt:.3f}x faster' if bt >= nt else f'{nt/bt:.3f}x slower'
            lines.append(f"| {row['custom_row']} | {mask} | {bt/1e6:.3f} ms | {nt/1e6:.3f} ms | {speed} |")
        bm, nm = [median(row[n]['peak_bytes']) for n in ('base', 'proposal')]
        lines.append(f"\nPeak allocation, custom header height={row['custom_row']}: base {bm/1048576:.6f} MiB; proposed {nm/1048576:.6f} MiB.\n")
    (ROOT / 'xlsxwriter_uniform_rows_recheck.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tests', action='store_true')
    parser.add_argument('--base', action='store_true')
    args = parser.parse_args()
    changed = proposal()
    cores = RotatingCores()
    try:
        cores.rotate()
        if args.tests:
            import pytest
            probe.Worksheet._position_object_pixels = probe.ORIGINAL if args.base else changed

            class Rotation:
                count = 0

                def pytest_runtest_setup(self, item):
                    if self.count % 200 == 0:
                        cores.rotate()
                    self.count += 1

            raise SystemExit(pytest.main(['-q', 'xlsxwriter/test', '--tb=short'], plugins=[Rotation()]))
        data = probe.load_data()
        report = {'metadata': {'python': platform.python_version(), 'repeats': 20, 'memory_repeats': 5,
                               'data_url': probe.URL, 'data_sha256': data[3],
                               'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=probe.REPO, text=True).strip(),
                               'proposal_transform': inspect.getsource(proposal),
                               'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
                  'geometry_comparisons': probe.verify_geometry(changed), 'error_comparisons': 0, 'results': []}
        methods = {'base': probe.ORIGINAL, 'proposal': changed}
        for custom in (False, True):
            sheet = probe.Worksheet()
            sheet.set_default_row(24)
            if custom:
                sheet.set_row(0, 25)
            for row_start in (None, '3', 5.25, [], {}, (1,), True, False, -3, 0, 5):
                outcomes = []
                for method in methods.values():
                    try:
                        outcomes.append(('return', method(sheet, 1, row_start, 0, 0, 128, 74, 0)))
                    except Exception as error:
                        outcomes.append((type(error).__name__, str(error)))
                assert outcomes[0] == outcomes[1], (custom, row_start, outcomes)
                report['error_comparisons'] += 1
        for custom in (False, True):
            case = {'rows': len(data[1]), 'height': 24, 'comments': True, 'custom_row': custom}
            probe.Worksheet._position_object_pixels = probe.ORIGINAL
            expected = probe.content(probe.build(case, data))
            row = {**case, 'masks': [], 'base': {'time_ns': [], 'peak_bytes': []},
                   'proposal': {'time_ns': [], 'peak_bytes': []}}
            for repeat in range(20):
                row['masks'].append(cores.rotate())
                # Flip order on successive visits to each pair, not on every core rotation.
                order = ('base', 'proposal') if (repeat // len(cores.pairs)) % 2 == 0 else ('proposal', 'base')
                for name in order:
                    probe.Worksheet._position_object_pixels = methods[name]
                    gc.collect()
                    gc.disable()
                    try:
                        start = time.perf_counter_ns()
                        raw = probe.build(case, data)
                        elapsed = time.perf_counter_ns() - start
                    finally:
                        gc.enable()
                    assert probe.content(raw) == expected
                    row[name]['time_ns'].append(elapsed)
                if repeat < 5:
                    for name in order:
                        probe.Worksheet._position_object_pixels = methods[name]
                        gc.collect()
                        tracemalloc.start()
                        try:
                            raw = probe.build(case, data)
                            peak = tracemalloc.get_traced_memory()[1]
                        finally:
                            tracemalloc.stop()
                        assert probe.content(raw) == expected
                        row[name]['peak_bytes'].append(peak)
                print(f'custom header={custom}; timing repeat {repeat+1}/20; cores {row["masks"][-1]}', flush=True)
            report['results'].append(row)
            save(report)
        print((ROOT / 'xlsxwriter_uniform_rows_recheck.txt').read_text(), flush=True)
    finally:
        probe.Worksheet._position_object_pixels = probe.ORIGINAL
        cores.restore()


if __name__ == '__main__':
    main()
