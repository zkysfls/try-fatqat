# try-fatqat

[FatQat](https://github.com/spaceqat/fatqat) running in the browser through
[JupyterLite](https://jupyterlite.readthedocs.io/) and the
[xeus-python](https://github.com/jupyter-xeus/xeus-python) kernel, with
packages from [emscripten-forge](https://emscripten-forge.org/). Modeled on
[qutip/try-qutip](https://github.com/qutip/try-qutip).

Visitors need no installation and no server: the site is static and every
computation runs in the visitor's browser. Performance is not a goal.

## How FatQat runs in the browser

- numba has no WebAssembly build, so `jupyterlite-xeus` installs FatQat with
  pip's `--no-deps`, and the remaining dependencies (NumPy, SciPy, Matplotlib,
  QuTiP) come from emscripten-forge. See `lite/try-fatqat-env.yaml`.
- FatQat simulators default to `runtime="numba"`. `scripts/numpy_runtime.py`
  rewrites the tutorial notebooks so every `Simulator`, `AtomArraySimulator`,
  and `SCQubitSimulator` passes `runtime="numpy"`, and fails the build if one
  does not.
- The tutorials are rendered from the FatQat release tag that matches the
  pinned `fatqat==<version>` in `lite/try-fatqat-env.yaml`, so notebooks and
  the installed package always agree. To upgrade, change that pin.

## Build locally

```bash
conda env create -f environment.yml
conda activate try-fatqat-build
./scripts/fetch-tutorials   # render tutorials into lite/files/tutorials
./scripts/jl-build          # build the site into _output
./scripts/jl-serve          # serve it at http://localhost:8000
```

## Deployment

`.github/workflows/build_github_pages.yaml` builds the site on every push and
pull request and deploys `main` to GitHub Pages. In the repository settings,
set **Pages > Build and deployment > Source** to **GitHub Actions**.
