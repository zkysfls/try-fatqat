# Try FatQat

[FatQat](https://github.com/spaceqat/fatqat) runs here entirely in your
browser, compiled to WebAssembly. Nothing is installed on your computer and
nothing runs on a server. The first start downloads the Python environment,
so it can take a minute; later visits reuse the browser cache.

- Start with [quickstart.ipynb](quickstart.ipynb): build, draw, and run a
  Bell-state Program.
- Then open the [tutorials](tutorials/README.md), the same case studies as the
  [FatQat documentation](https://fatqat.readthedocs.io/en/latest/tutorials/).

## Differences from a local installation

- Simulators use `runtime="numpy"`. The default `runtime="numba"` needs a
  just-in-time compiler that cannot run in the browser, so the tutorials here
  pass `runtime="numpy"` explicitly. Results are the same; large programs are
  slower.
- Everything runs in a single thread; leave the parallel execution options
  at their defaults.
- Files you create or edit are kept only in this browser. Use **Download** in
  the notebook toolbar to keep a copy.
