"""Prepare the latest FatQat release for the browser build.

- Pin fatqat in the in-browser environment to the release, writing
  lite/try-fatqat-env.pinned.yaml for scripts/jl-build.
- Check that the environment provides every dependency of the release.
- Render the release's tutorials into lite/files/tutorials/<category>/, with
  every simulator switched to runtime="numpy".

The latest release is the newest final release on PyPI, or the newest
pre-release while there is no final release. Set FATQAT_VERSION to use another
release.

Usage: python scripts/sync_fatqat.py
"""

from __future__ import annotations

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

from numpy_runtime import to_numpy_runtime

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "lite" / "try-fatqat-env.yaml"
PINNED_ENV_FILE = ROOT / "lite" / "try-fatqat-env.pinned.yaml"
TUTORIALS = ROOT / "lite" / "files" / "tutorials"

# FatQat dependencies with no WebAssembly build. FatQat runs without them when
# every simulator uses runtime="numpy" and execution stays in one process.
BROWSER_EXCLUDED = {"numba", "loky"}

# Tutorials that take long to run in the browser, measured in headless
# Chromium. The note appears in the index and at the top of the notebook.
SLOW = {
    "atom-loss-erasure": "more than 15 minutes",
}


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

    tutorials = build_tutorials.discover_tutorials()
    order = list(build_tutorials.GALLERY.get("category_order", []))
    categories = sorted(
        {tutorial.category for tutorial in tutorials},
        key=lambda category: (
            order.index(category) if category in order else len(order),
            category,
        ),
    )

    shutil.rmtree(TUTORIALS, ignore_errors=True)
    index = ["# FatQat tutorials", "", f"From FatQat {version}.", ""]
    slow = dict(SLOW)
    for category in categories:
        title, description = build_tutorials._category_label(category)
        index += [f"## {title}", "", description, ""]
        for tutorial in (item for item in tutorials if item.category == category):
            source_info = tutorial.source
            notebook = nbformat.reads(
                build_tutorials._render_notebook(tutorial), as_version=4
            )
            entry = (
                f"- [{source_info.title}]({category}/{tutorial.slug}.ipynb): "
                f"{source_info.description}"
            )
            if duration := slow.pop(tutorial.slug, None):
                note = (
                    f"**Slow in the browser:** this tutorial takes {duration} to "
                    "run here. For faster results, install FatQat locally with "
                    "`pip install fatqat`."
                )
                notebook.cells.insert(
                    0, nbformat.v4.new_markdown_cell(note, id="browser-note")
                )
                entry += f" *Slow in the browser: {duration}.*"
            try:
                changed = to_numpy_runtime(notebook)
            except ValueError as error:
                raise SystemExit(f"{tutorial.slug}: {error}") from error
            path = TUTORIALS / category / f"{tutorial.slug}.ipynb"
            path.parent.mkdir(parents=True, exist_ok=True)
            nbformat.write(notebook, path)
            index.append(entry)
            print(f"{path.relative_to(ROOT)}: {changed} cell(s) switched to NumPy")
        index.append("")
    for slug in slow:
        print(f"warning: SLOW names a tutorial that does not exist: {slug}")
    (TUTORIALS / "README.md").write_text("\n".join(index), encoding="utf-8")


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
