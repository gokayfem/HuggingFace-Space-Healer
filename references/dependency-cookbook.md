# Hugging Face Spaces Dependency Cookbook

Load this reference when the failure is a resolver conflict, import error, CUDA ABI issue, Gradio launch error, or model-stack incompatibility. These pins are heuristics from successful repairs, not permanent truth. Always prefer the current Hugging Face error message when ZeroGPU or base images change.

## Table of Contents

- General rule
- Gradio families
- Python runtime
- ZeroGPU and torch companions
- Diffusers and transformers families
- Florence and flash-attn
- Hub download reliability
- Real-ESRGAN and legacy packages
- Requirements cleanup
- Resolver checks

## General Rule

Avoid this dependency shape:

```text
torch
torchvision
diffusers
transformers==old-version
gradio
huggingface_hub
```

It lets pip compose a new stack around old application code. Instead, pin the family that the app actually targets.

When changing dependencies, preserve intent:

- If the model code is old, pin compatible old libraries.
- If the runtime demands a new torch, update companion wheels too.
- If the component requires Gradio 4, downgrade the Space SDK instead of forcing Gradio 5.
- If a package is duplicated, remove the duplicate.
- If a package is only present because a previous runtime image needed it, remove it when it now causes resolver conflicts.

## Gradio Families

### Older Gradio 4 Custom Components

Use when custom components or launch traces point to Gradio 4:

```yaml
sdk: gradio
sdk_version: 4.36.1
python_version: "3.10"
app_file: app.py
```

Useful requirements:

```text
huggingface_hub<1.0
pydantic==2.10.6
```

Common matching symptoms:

- component requires `gradio<5`
- `HfFolder` import failure from old Gradio or Gradio client
- schema or Jinja errors during launch
- unsupported component kwarg after downgrading

Try `4.36.1` first for older apps. Try `4.44.1` when the component or app code needs a later Gradio 4 API. Do not assume Gradio 5 is an upgrade for Spaces with custom components.

### Gradio 5

Use Gradio 5 when:

- the custom component supports it
- the app was written for the newer component API
- the traceback points to an old Gradio bug already fixed upstream

If the app was auto-updated to Gradio 5 and broke, check component requirements before patching app code.

## Python Runtime

Use `python_version: "3.10"` when old audio, Gradio, torch, or binary packages fail under newer Python.

Signals:

- `audioop` or `pyaudioop` missing
- old torch wheels unavailable for the default Python
- Gradio 4 dependency expects older stdlib behavior

Always quote:

```yaml
python_version: "3.10"
```

Unquoted `3.10` can be parsed as a number by YAML tooling.

## ZeroGPU and Torch Companions

For ZeroGPU, the platform may reject unsupported torch pins with `CONFIG_ERROR`. Use the versions listed by the current runtime error. These pairs have been useful starting points:

```text
torch==2.10.0
torchvision==0.25.0
torchaudio==2.10.0
```

```text
torch==2.11.0
torchvision==0.26.0
torchaudio==2.11.0
```

If `xformers` is used, pin it with the torch family rather than floating it. A mismatch can build but crash at import or runtime.

Always:

- Pin `torchvision` with torch.
- Pin `torchaudio` with torch if present.
- Keep `spaces` installed when using `@spaces.GPU`.
- Remove duplicate `spaces` entries.
- Avoid `torch<=...` when the runtime requires one exact supported version.

If source-built packages need torch during setup, install torch first through the Space's existing preinstall mechanism, such as `pre-requirements.txt`, when present.

## Diffusers and Transformers Families

Symptoms of mismatch:

- `cannot import name 'Dinov2WithRegistersConfig'`
- autoencoder imports fail inside diffusers
- scheduler, pipeline, or model class imports fail after pip selects latest diffusers
- app pins `transformers` but leaves `diffusers` floating

Old SDXL, Kolors, and similar apps:

```text
transformers==4.43.2
diffusers==0.31.0
```

Some image-generation apps from the same era:

```text
transformers==4.45.2
diffusers==0.31.0
```

Newer Flux or TRELLIS-style apps:

```text
transformers==4.46.3
diffusers==0.32.2
```

Do not upgrade both libraries blindly. Check imports used by `app.py` and model custom code.

## Florence and Flash-Attn

Florence remote code may list `flash_attn` as an import even when the inference path works without it. Runtime installing `flash-attn` is slow and fragile on Spaces.

Safer pattern:

```python
from unittest.mock import patch
from transformers.dynamic_module_utils import get_imports

def fixed_get_imports(filename):
    if not str(filename).endswith("/modeling_florence2.py"):
        return get_imports(filename)
    imports = get_imports(filename)
    if "flash_attn" in imports:
        imports.remove("flash_attn")
    return imports

with patch("transformers.dynamic_module_utils.get_imports", fixed_get_imports):
    model = AutoModelForCausalLM.from_pretrained(model_dir, trust_remote_code=True)
    processor = AutoProcessor.from_pretrained(model_dir, trust_remote_code=True)
```

Common Florence requirements:

```text
timm
einops
huggingface_hub<1.0
```

Add `einops` only when the traceback asks for it. If the custom code truly requires flash attention for correctness, do not remove it; instead use a compatible wheel/build path.

## Hub Download Reliability

Large Spaces often fail because the first download times out during import.

Use:

```text
huggingface_hub<1.0
```

when old Gradio or old code expects pre-1.0 APIs.

Use timeout env vars and retries:

```python
import os
import time
from huggingface_hub import snapshot_download

os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "60")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")

def snapshot_download_with_retries(repo_id, retries=3):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return snapshot_download(repo_id=repo_id, etag_timeout=60, max_workers=2)
        except Exception as exc:
            last_error = exc
            if attempt == retries:
                raise
            print(f"Snapshot download failed for {repo_id} on attempt {attempt}: {exc}")
            time.sleep(5 * attempt)
    raise last_error
```

Load from the returned local path when possible. This separates network failures from model import failures.

## Real-ESRGAN and Legacy Packages

Signals:

- `pkg_resources` missing
- GitHub install of Real-ESRGAN fails
- app installs Real-ESRGAN unconditionally on every launch

Useful requirements:

```text
setuptools<81
```

Conditional install:

```python
import importlib.util
import subprocess
import sys

if importlib.util.find_spec("RealESRGAN") is None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "git+https://github.com/inference-sh/Real-ESRGAN.git",
            "--no-deps",
            "--no-build-isolation",
        ],
        check=True,
    )
```

Keep runtime installs rare. If the package can be installed reproducibly at build time, prefer `requirements.txt`.

## Requirements Cleanup

Before pushing dependency fixes, scan for:

- duplicate package names
- both broad and exact pins for the same package
- unpinned `torchvision` next to pinned `torch`
- unpinned `diffusers` next to old `transformers`
- stale `triton`
- `gradio` in `requirements.txt` fighting README `sdk_version`
- `share=True` or runtime Gradio launch flags that mask the actual issue
- generated lock/cache files that do not belong in the Space

Prefer comments only when they explain a non-obvious pin. Do not annotate every package.

## Resolver Checks

Useful local checks:

```powershell
python -m pip install --dry-run -r requirements.txt
python -m pip check
```

Linux/Python wheel availability:

```powershell
python -m pip install --dry-run --only-binary=:all: --platform manylinux_2_28_x86_64 --python-version 3.10 --implementation cp --abi cp310 -r requirements.txt
```

If local Windows cannot reproduce Linux CUDA resolution, use the check only for obvious conflicts and rely on Hub build logs for final truth.
