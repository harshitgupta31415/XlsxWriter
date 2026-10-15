"""Benchmark the pinned base against the actual uniform-height positioning fix."""

from __future__ import annotations

import ast
import gc
import hashlib
import inspect
import json
import platform
import subprocess
import textwrap
import time
import tracemalloc
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import xlsxwriter_uniform_rows_probe as fixture
from benchmark_cpu import RotatingCores

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent / "XlsxWriter"
BASE = "5d4606d89a955226d2d0825a0f44309043ae7251"
SOURCE = REPO / "xlsxwriter/worksheet.py"
MEMORY_REPEATS = 5


def methods():
    current = fixture.Worksheet._position_object_pixels
    assert Path(inspect.getfile(current)).resolve() == SOURCE
    source = subprocess.check_output(
        ["git", "show", f"{BASE}:xlsxwriter/worksheet.py"],
        cwd=REPO,
        text=True,
        encoding="utf-8",
    )
    worksheet = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == "Worksheet"
    )
    node = next(
        node
        for node in worksheet.body
        if isinstance(node, ast.FunctionDef) and node.name == current.__name__
    )
    namespace = dict(current.__globals__)
    exec(
        compile(ast.Module(body=[node], type_ignores=[]), "<base positioning>", "exec"),
        namespace,
    )
    baseline = namespace[node.name]
    # Check that the only method-body change is the uniform-height shortcut.
    changed = ast.Module(body=[node], type_ignores=[])
    hits = 0
    for statement in ast.walk(changed):
        if (
            isinstance(statement, ast.If)
            and isinstance(statement.test, ast.Attribute)
            and statement.test.attr == "row_size_changed"
        ):
            branch = ast.parse(
                "if not self.row_sizes:\n    y_abs += self.default_row_height * len(range(row_start))\nelse:\n    pass"
            ).body[0]
            branch.orelse = statement.body
            statement.body = [branch]
            hits += 1
    assert hits == 1
    actual = ast.parse(textwrap.dedent(inspect.getsource(current)))
    assert ast.dump(changed, include_attributes=False) == ast.dump(
        actual, include_attributes=False
    )
    return {"base": baseline, "pr": current}


def verify(pair, data):
    fixture.ORIGINAL = pair["base"]
    comparisons = fixture.verify_geometry(pair["pr"])
    for custom in (False, True):
        sheet = fixture.Worksheet()
        sheet.set_default_row(24)
        if custom:
            sheet.set_row(0, 25)
        for row in (None, "3", 5.25, [], {}, (1,), True, False, -3, 0, 5):
            outcomes = []
            for method in pair.values():
                try:
                    outcomes.append(("return", method(sheet, 1, row, 0, 0, 128, 74, 0)))
                except Exception as error:
                    outcomes.append((type(error).__name__, str(error)))
            assert outcomes[0] == outcomes[1]
            comparisons += 1
    # 100 complete workbooks exercise realistic combinations, not just geometry.
    for rows in (0, 1, 20, 100, 500):
        for height in (None, 15, 17.25, 24, 36):
            for custom in (False, True):
                for comments in (False, True):
                    case = {
                        "rows": rows,
                        "height": height,
                        "custom_row": custom,
                        "comments": comments,
                    }
                    outputs = []
                    for method in pair.values():
                        fixture.Worksheet._position_object_pixels = method
                        outputs.append(fixture.content(fixture.build(case, data)))
                    assert outputs[0] == outputs[1], case
                    comparisons += 1
    return {
        "geometry_and_error_comparisons": comparisons - 100,
        "matching_workbooks": 100,
    }


def speed(base, pr):
    return f"{base / pr:.3f}× faster" if base >= pr else f"{pr / base:.3f}× slower"


def save(report):
    (ROOT / "xlsxwriter_uniform_rows_results.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    lines = [
        "# Uniform-height object positioning",
        "",
        "Complete 6,433 × 14 workbook generation with 333 data-review comments.",
        f"{report['metadata']['repeats']} timing runs per version/case, five per rotating physical-core pair.",
        "Five separate memory runs per version/case. Memory is peak newly traced Python allocation, not process RAM.",
        "The two workbook cases use public taxi records. This is a constructed workflow, not a measurement of a deployed application.",
        "Every archive member is compared byte-for-byte outside the measurement.",
        "",
        "<details>",
        "<summary>Show every measured case and core pair</summary>",
        "",
        "| Row overrides | Core mask | Base time | PR time | Speed | Base peak | PR peak | Memory |",
        "|---|---|---:|---:|---|---:|---:|---|",
    ]
    for row in report["results"]:
        bm, pm = [median(row[name]["peak_bytes"]) for name in ("base", "pr")]
        memory = f"{pm / bm:.6f}× more" if pm >= bm else f"{bm / pm:.6f}× less"
        for mask in sorted(set(row["masks"])):
            selected = [
                index for index, value in enumerate(row["masks"]) if value == mask
            ]
            bt, pt = [
                median(row[name]["time_ns"][i] for i in selected)
                for name in ("base", "pr")
            ]
            label = (
                "custom header (original path)"
                if row["custom_row"]
                else "none (uniform height)"
            )
            lines.append(
                f"| {label} | {mask} | {bt / 1e6:.3f} ms | {pt / 1e6:.3f} ms | {speed(bt, pt)} | {bm / 1048576:.6f} MiB | {pm / 1048576:.6f} MiB | {memory} |"
            )
    lines += [
        "",
        "</details>",
        "",
        "Memory medians belong to each workbook case, not to each individual core pair.",
        "All samples, fixture hashes and source hashes are in the JSON.",
        "",
    ]
    (ROOT / "xlsxwriter_uniform_rows_results.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def main():
    pair = methods()
    data = fixture.load_data()
    cores = RotatingCores()
    repeats = 5 * len(cores.pairs)
    report = {
        "metadata": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "base_commit": BASE,
            "repeats": repeats,
            "memory_repeats": MEMORY_REPEATS,
            "data_url": fixture.URL,
            "data_sha256": data[3],
            "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "core_masks": [hex(mask) for mask in cores.pairs],
            "started_utc": datetime.now(timezone.utc).isoformat(),
        },
        "results": [],
    }
    try:
        cores.rotate()
        report["verification"] = verify(pair, data)
        print(f"Compatibility checks: {report['verification']}", flush=True)
        for custom in (False, True):
            case = {
                "rows": len(data[1]),
                "height": 24,
                "comments": True,
                "custom_row": custom,
            }
            fixture.Worksheet._position_object_pixels = pair["base"]
            expected = fixture.content(fixture.build(case, data))
            row = {
                **case,
                "comment_count": sum(r <= case["rows"] for r, _, _ in data[2]),
                "masks": [],
                "archive_members": {
                    name: hashlib.sha256(value).hexdigest()
                    for name, value in expected.items()
                },
                "base": {"time_ns": [], "peak_bytes": []},
                "pr": {"time_ns": [], "peak_bytes": []},
            }
            for repeat in range(repeats):
                row["masks"].append(cores.rotate())
                order = (
                    ("base", "pr")
                    if (repeat // len(cores.pairs)) % 2 == 0
                    else ("pr", "base")
                )
                for name in order:
                    fixture.Worksheet._position_object_pixels = pair[name]
                    gc.collect()
                    gc.disable()
                    try:
                        start = time.perf_counter_ns()
                        raw = fixture.build(case, data)
                        elapsed = time.perf_counter_ns() - start
                    finally:
                        gc.enable()
                    assert fixture.content(raw) == expected
                    row[name]["time_ns"].append(elapsed)
                if repeat < MEMORY_REPEATS:
                    for name in order:
                        fixture.Worksheet._position_object_pixels = pair[name]
                        gc.collect()
                        tracemalloc.start()
                        try:
                            raw = fixture.build(case, data)
                            peak = tracemalloc.get_traced_memory()[1]
                        finally:
                            tracemalloc.stop()
                        assert fixture.content(raw) == expected
                        row[name]["peak_bytes"].append(peak)
                print(
                    f"row overrides={custom}; run {repeat + 1}/{repeats}; cores {row['masks'][-1]}; "
                    f"{(int(custom) * repeats + repeat + 1) / (2 * repeats):.1%} complete",
                    flush=True,
                )
            assert sorted(Counter(row["masks"]).values()) == [5] * len(cores.pairs)
            report["results"].append(row)
            save(report)
        report["metadata"]["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save(report)
        print("Finished. All measured workbook contents matched.", flush=True)
    finally:
        fixture.Worksheet._position_object_pixels = pair["pr"]
        cores.restore()


if __name__ == "__main__":
    main()
