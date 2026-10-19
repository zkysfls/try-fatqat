"""Make the FatQat simulators in notebooks use the NumPy runtime.

numba has no WebAssembly build, and FatQat simulators default to
``runtime="numba"``. This rewrites each simulator call that does not choose a
runtime so it passes ``runtime="numpy"``, then checks that every simulator call
in the notebook runs on NumPy. Notebooks are rewritten in place.

Usage: python scripts/numpy_runtime.py NOTEBOOK...
"""

from __future__ import annotations

import ast
import sys

import nbformat

# Public FatQat classes whose constructor takes ``runtime`` (default "numba").
SIMULATORS = {"Simulator", "AtomArraySimulator", "SCQubitSimulator"}
KEYWORD = 'runtime="numpy"'


def _simulator_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name in SIMULATORS:
            yield node


def _index(lines: list[str], lineno: int, col_offset: int) -> int:
    # ast column offsets count UTF-8 bytes, not characters.
    line = lines[lineno - 1]
    column = len(line.encode()[:col_offset].decode())
    return sum(len(previous) for previous in lines[: lineno - 1]) + column


def rewrite(source: str) -> str:
    """Return ``source`` with ``runtime="numpy"`` added to simulator calls."""

    lines = source.splitlines(keepends=True)
    inserts = []
    for call in _simulator_calls(ast.parse(source)):
        if any(keyword.arg == "runtime" for keyword in call.keywords):
            continue
        if any(keyword.arg is None for keyword in call.keywords):
            raise ValueError(
                f"line {call.lineno}: cannot tell whether **kwargs sets runtime"
            )
        arguments = [*call.args, *call.keywords]
        if arguments:
            last = max(arguments, key=lambda node: (node.end_lineno, node.end_col_offset))
            position = _index(lines, last.end_lineno, last.end_col_offset)
            inserts.append((position, f", {KEYWORD}"))
        else:
            # Just before the closing parenthesis.
            position = _index(lines, call.end_lineno, call.end_col_offset) - 1
            inserts.append((position, KEYWORD))
    for position, text in sorted(inserts, reverse=True):
        source = source[:position] + text + source[position:]
    return source


def check(source: str) -> None:
    """Raise ``ValueError`` if a simulator call does not run on NumPy."""

    for call in _simulator_calls(ast.parse(source)):
        runtime = next(
            (keyword.value for keyword in call.keywords if keyword.arg == "runtime"),
            None,
        )
        if not (isinstance(runtime, ast.Constant) and runtime.value == "numpy"):
            raise ValueError(f"line {call.lineno}: simulator does not use runtime='numpy'")


def main(paths: list[str]) -> int:
    for path in paths:
        notebook = nbformat.read(path, as_version=4)
        changed = 0
        for index, cell in enumerate(notebook.cells):
            if cell.cell_type != "code":
                continue
            try:
                source = rewrite(cell.source)
                check(source)
            except (SyntaxError, ValueError) as error:
                raise SystemExit(f"{path}: code cell {index}: {error}") from error
            if source != cell.source:
                cell.source = source
                changed += 1
        nbformat.write(notebook, path)
        print(f"{path}: {changed} cell(s) switched to runtime='numpy'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
