"""Run XlsxWriter tests on rotating pairs of physical CPU cores."""

import argparse
import ast
import os
import subprocess
import sys
from pathlib import Path

from benchmark_cpu import RotatingCores

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent / "XlsxWriter"
BASE = "5d4606d89a955226d2d0825a0f44309043ae7251"
sys.path.insert(0, str(REPO))

import pytest
from xlsxwriter.worksheet import Worksheet

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--base", action="store_true")
args = parser.parse_args()
os.chdir(REPO)
if args.base:
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
    method = next(
        node
        for node in worksheet.body
        if isinstance(node, ast.FunctionDef) and node.name == "_position_object_pixels"
    )
    namespace = dict(Worksheet._position_object_pixels.__globals__)
    exec(
        compile(ast.Module(body=[method], type_ignores=[]), "<base worksheet>", "exec"),
        namespace,
    )
    Worksheet._position_object_pixels = namespace[method.name]

cores = RotatingCores()


class Rotation:
    count = 0

    def pytest_runtest_setup(self, item):
        if self.count % 200 == 0:
            cores.rotate()
        self.count += 1


extra = (
    ["--ignore=xlsxwriter/test/worksheet/test_position_object_pixels.py"]
    if args.base
    else []
)
try:
    result = pytest.main(
        ["-q", "xlsxwriter/test", "--tb=short", *extra], plugins=[Rotation()]
    )
finally:
    cores.restore()
raise SystemExit(result)
