"""Prepare the latest FatQat release for the browser build.

- Pin fatqat in the in-browser environment to the release, writing
  lite/try-fatqat-env.pinned.yaml for scripts/jl-build.
- Check that the environment provides every dependency of the release.
- Render the release's tutorials that run without numba into
  lite/files/tutorials/<category>/.

The latest release is the newest final release on PyPI, or the newest
pre-release while there is no final release. Set FATQAT_VERSION to use another
release.

Usage: python scripts/sync_fatqat.py
"""

from __future__ import annotations

import ast
import io
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

import nbformat
import yaml

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "lite" / "try-fatqat-env.yaml"
PINNED_ENV_FILE = ROOT / "lite" / "try-fatqat-env.pinned.yaml"
TUTORIALS = ROOT / "lite" / "files" / "tutorials"

# FatQat dependencies with no WebAssembly build. FatQat runs without them when
# every simulator uses runtime="numpy" and execution stays in one process.
BROWSER_EXCLUDED = {"numba", "loky"}

# Public FatQat classes whose constructor takes ``runtime``, default "numba".
SIMULATORS = {"Simulator", "AtomArraySimulator", "SCQubitSimulator"}


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def _project_name(requirement: str) -> str:
    name = re.split(r"[\s<>=!~;\[@(]", requirement.strip(), maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", name).lower()


def latest_release() -> str:
    # PyPI reports the newest final release, or the newest pre-release while
    # the project has no final release.
    return _get_json("https://pypi.org/pypi/fatqat/json")["info"]["version"]


def check_dependencies(version: str) -> None:
    release = _get_json(f"https://pypi.org/pypi/fatqat/{version}/json")
    required = {
        _project_name(requirement)
        for requirement in release["info"]["requires_dist"] or []
        if not re.search(r"\bextra\s*==", requirement)
    }
    provided = set()
    for dependency in yaml.safe_load(ENV_FILE.read_text())["dependencies"]:
        specs = dependency["pip"] if isinstance(dependency, dict) else [dependency]
        provided.update(_project_name(spec) for spec in specs)
    if missing := sorted(required - provided - BROWSER_EXCLUDED):
        raise SystemExit(
            f"fatqat {version} requires packages missing from {ENV_FILE.name}: "
            f"{', '.join(missing)}. Add them from emscripten-forge, or under pip "
            "if they are pure Python."
        )


def pin_environment(version: str) -> None:
    pinned, count = re.subn(
        r"^(\s*- fatqat)\s*$", rf"\g<1>=={version}", ENV_FILE.read_text(), flags=re.M
    )
    if count != 1:
        raise SystemExit(f"expected one unpinned '- fatqat' line in {ENV_FILE}")
    PINNED_ENV_FILE.write_text(pinned)


def _runs_on_numba(call: ast.Call) -> bool:
    func = call.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    if name not in SIMULATORS:
        return False
    runtime = next((kw.value for kw in call.keywords if kw.arg == "runtime"), None)
    return not (isinstance(runtime, ast.Constant) and runtime.value == "numpy")


def uses_numba(code: str) -> bool:
    """Return whether ``code`` imports numba or creates a simulator that runs on it.

    A simulator runs on numba unless its call passes ``runtime="numpy"``
    literally, so calls that leave the runtime to ``**kwargs`` or a variable
    count as numba.
    """

    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Call) and _runs_on_numba(node):
            return True
        if isinstance(node, ast.Import) and any(
            alias.name.split(".")[0] == "numba" for alias in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and (
            (node.module or "").split(".")[0] == "numba"
        ):
            return True
    return False


def download_source(version: str, directory: str) -> Path:
    url = f"https://github.com/spaceqat/fatqat/archive/refs/tags/v{version}.tar.gz"
    with urllib.request.urlopen(url, timeout=120) as response:
        archive = io.BytesIO(response.read())
    with tarfile.open(fileobj=archive, mode="r:gz") as tar:
        tar.extractall(directory, filter="data")
    (source,) = Path(directory).iterdir()
    return source


def render_tutorials(source: Path, version: str) -> None:
    # Render the same unexecuted notebooks the FatQat docs offer for download.
    # The tool's own entry point also renders the docs pages, which need cached
    # execution results that release tags do not ship.
    sys.path.insert(0, str(source / "docs" / "mkdocs" / "tools"))
    import build_tutorials

    tutorials, skipped = [], []
    for tutorial in build_tutorials.discover_tutorials():
        needs_numba = any(uses_numba(code) for code in tutorial.code_cells)
        (skipped if needs_numba else tutorials).append(tutorial)
    order = list(build_tutorials.GALLERY.get("category_order", []))
    categories = sorted(
        {tutorial.category for tutorial in tutorials},
        key=lambda category: (
            order.index(category) if category in order else len(order),
            category,
        ),
    )

    shutil.rmtree(TUTORIALS, ignore_errors=True)
    index = [
        "# FatQat tutorials",
        "",
        f"The FatQat {version} tutorials that run without numba. Find all of them "
        "in the [FatQat documentation](https://fatqat.readthedocs.io/en/stable/tutorials/).",
        "",
    ]
    for category in categories:
        title, description = build_tutorials._category_label(category)
        index += [f"## {title}", "", description, ""]
        for tutorial in (item for item in tutorials if item.category == category):
            path = TUTORIALS / category / f"{tutorial.slug}.ipynb"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(build_tutorials._render_notebook(tutorial), encoding="utf-8")
            index.append(
                f"- [{tutorial.source.title}]({category}/{tutorial.slug}.ipynb): "
                f"{tutorial.source.description}"
            )
            print(f"Added {path.relative_to(ROOT)}")
        index.append("")
    (TUTORIALS / "README.md").write_text("\n".join(index), encoding="utf-8")
    for tutorial in skipped:
        print(f"Skipped {tutorial.category}/{tutorial.slug}: uses numba")

def main() -> int:
    version = os.environ.get("FATQAT_VERSION") or latest_release()
    print(f"Preparing FatQat {version}")
    check_dependencies(version)
    pin_environment(version)
    with tempfile.TemporaryDirectory() as directory:
        render_tutorials(download_source(version, directory), version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
