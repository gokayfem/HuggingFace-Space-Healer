---
name: fix-huggingface-spaces
description: Diagnose, repair, and verify public or private Hugging Face Spaces across Gradio, Streamlit, Docker, static, CPU, GPU, and ZeroGPU runtimes. Use when an AI coding agent is asked to fix failing Spaces, clone Space repos, inspect build/runtime errors, update README frontmatter, resolve requirements issues, handle ZeroGPU compatibility, patch Gradio app startup failures, stabilize model downloads, or safely push fixes to Hugging Face without leaking tokens or accidentally waking or modifying out-of-scope Spaces.
---

# Fix Hugging Face Spaces

## Core Rule

Treat a Space repair as a production debugging job:

1. Identify the exact Space and its current runtime state.
2. Clone safely without storing credentials.
3. Read the Space metadata, requirements, and app entrypoint.
4. Reproduce the smallest useful failure locally or through Hub logs.
5. Patch one root cause at a time.
6. Push only scoped commits.
7. Poll the Hugging Face runtime until the Space is actually healthy.
8. Support both public and private Spaces, but require explicit authorization before using private credentials or touching private repos.

Prefer official Hugging Face docs when a config field, runtime behavior, or API shape may have changed. The Spaces config reference defines README frontmatter such as `sdk`, `sdk_version`, `python_version`, and `app_file`, and `python_version` is a string field. Quote values like `"3.10"` so YAML does not parse them as numbers.

## Safety Boundaries

### Tokens

Treat Hugging Face tokens as secrets.

- Do not echo a token in final answers, logs, filenames, remotes, commits, scripts, or comments.
- Do not put tokens in `git remote` URLs.
- Prefer short-lived in-memory auth:

```powershell
$token = $env:HF_TOKEN
$basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("__token__:$token"))
git -c http.extraheader="Authorization: Basic $basic" push origin main
```

- For REST calls, use an in-memory header:

```powershell
$headers = @{ Authorization = "Bearer $env:HF_TOKEN" }
Invoke-RestMethod -Uri "https://huggingface.co/api/spaces/user/space/runtime" -Headers $headers
```

- If a token was pasted into chat, finish the task and then recommend rotation.

### Public and Private Spaces

This skill works for public and private Spaces. Choose the operating mode from the user's request:

- Public mode: use anonymous Hub APIs and public Git clones.
- Private mode: use authenticated Hub APIs and authenticated Git clone/push commands.
- Mixed mode: separate public and private work in the plan and status output.

Safety rules:

- Private Spaces require explicit user permission.
- Sleeping private Spaces are not broken by default. Do not wake, clone, push, restart, or inspect them unless the user specifically asks.
- If the user says "do not touch private Spaces", stop all private work immediately, including status polling.
- If the user excludes a Space by name, exclude it even if it is in `RUNTIME_ERROR`.
- If a user asks to fix private Spaces generally, private Spaces already in `BUILD_ERROR`, `RUNTIME_ERROR`, or `CONFIG_ERROR` are in scope; sleeping private Spaces are still out of scope unless the user explicitly includes sleeping Spaces.

Useful state interpretation:

- `RUNNING`: Container is up. Still verify the page or endpoint if the user reported an internal server error.
- `APP_STARTING`: Build passed, app is importing/loading. Poll again, and inspect startup logs if it stays there.
- `BUILDING`: Build is in progress. Wait before patching again unless logs show a deterministic failure.
- `BUILD_ERROR`: Dependency, system package, Docker, README config, or build-time install problem.
- `RUNTIME_ERROR`: App imported then crashed, or request/startup code failed.
- `CONFIG_ERROR`: README/frontmatter/runtime compatibility problem, often unsupported ZeroGPU torch.
- `SLEEPING`: Not a failure unless the user explicitly wants it awakened or checked.

### Git and Local Workspace

- Clone each Space into a separate directory, preferably under a `spaces/` folder.
- Set `GIT_LFS_SKIP_SMUDGE=1` before cloning unless large assets are required for the specific diagnosis.
- Check `git status --short` before editing.
- Use small commits with direct messages.
- Never revert user changes you did not make.
- Use `apply_patch` for manual edits.
- Clean local `__pycache__` or generated files before committing.
- Do not commit downloaded model caches, outputs, temporary videos, generated images, or secrets.

## Quick Workflow

### 1. Discover Exact Space IDs

The UI title is often not the repo slug. Resolve exact IDs first.

Public list:

```powershell
Invoke-RestMethod -Uri "https://huggingface.co/api/spaces?author=USER&full=false"
```

Authenticated list, only when private scope is authorized:

```powershell
$headers = @{ Authorization = "Bearer $env:HF_TOKEN" }
Invoke-RestMethod -Uri "https://huggingface.co/api/spaces?author=USER&full=false" -Headers $headers
```

Use runtime endpoint per Space:

```powershell
Invoke-RestMethod -Uri "https://huggingface.co/api/spaces/USER/SPACE/runtime"
```

The bundled helper can scan public or explicit Spaces from the skill directory:

```powershell
python scripts/space_status.py --author USER
python scripts/space_status.py --ids USER/SPACE USER/OTHER
```

Use private listing only when private inspection is explicitly authorized:

```powershell
$env:HF_TOKEN = "hf_..."
python scripts/space_status.py --author USER --include-private --token-env HF_TOKEN
```

For an explicitly named private Space, pass the id and a token:

```powershell
$env:HF_TOKEN = "hf_..."
python scripts/space_status.py --ids USER/PRIVATE-SPACE --token-env HF_TOKEN
```

### 2. Clone Safely

Public:

```powershell
$env:GIT_LFS_SKIP_SMUDGE = "1"
git clone --depth 1 https://huggingface.co/spaces/USER/SPACE C:\work\spaces\SPACE
```

Private, with explicit authorization:

```powershell
$env:GIT_LFS_SKIP_SMUDGE = "1"
$token = $env:HF_TOKEN
$basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("__token__:$token"))
git -c http.extraheader="Authorization: Basic $basic" clone --depth 1 https://huggingface.co/spaces/USER/SPACE C:\work\spaces\SPACE
```

After cloning:

```powershell
git remote -v
git status --short
rg --files
Get-Content -Raw README.md
Get-Content -Raw requirements.txt
Get-Content -Raw app.py
```

### 3. Read README Frontmatter First

The README frontmatter controls the Space runtime. Common fields:

```yaml
---
title: My Space
sdk: gradio
sdk_version: 4.36.1
python_version: "3.10"
app_file: app.py
hardware: zero-a10g
---
```

Repair checks:

- Quote `python_version`.
- Match `sdk_version` to custom components and app API usage.
- For Gradio 4 apps, pin compatible `huggingface_hub<1.0` if imports fail on `HfFolder`.
- For Python 3.13 errors around `audioop` or `pyaudioop`, pin `python_version: "3.10"` or upgrade the dependent stack if safer.
- For ZeroGPU, verify torch pins are supported by the current runtime error message.
- Do not assume latest Gradio is always best. Custom Gradio components frequently pin `gradio<5`.

### 4. Classify the Failure

Use the runtime stage plus logs:

- `BUILD_ERROR`: inspect pip resolver conflicts, unsupported wheels, missing build deps, README config.
- `CONFIG_ERROR`: check ZeroGPU supported torch versions and YAML frontmatter.
- `RUNTIME_ERROR` at import: inspect top-level model loading, missing packages, version incompatibilities.
- `RUNTIME_ERROR` after page request: inspect Gradio/Jinja/API compatibility, lazy-load request paths, unsupported component kwargs.
- `APP_STARTING` for many minutes: top-level model download/load is likely blocking the server.
- `RUNNING` but page returns 500: check page fetch and request logs; runtime API alone is insufficient.

Public page check:

```powershell
$r = Invoke-WebRequest -Uri "https://USER-SPACE.hf.space/" -UseBasicParsing -TimeoutSec 60
[PSCustomObject]@{
  StatusCode = $r.StatusCode
  Length = $r.Content.Length
  Title = ([regex]::Match($r.Content, "<title>(.*?)</title>").Groups[1].Value)
}
```

## High-Value Failure Patterns

### Gradio Custom Component Conflicts

Symptoms:

- Pip resolver says a component requires `gradio<5`.
- Build fails after SDK moved to Gradio 5.
- Components like `gradio_pannellum`, `gradio_litmodel3d`, or older `gradio-imageslider` are involved.

Fix:

- Use a Gradio 4 SDK compatible with the component, often `4.36.1`, `4.38.1`, or `4.44.1`.
- Pin `huggingface_hub<1.0`.
- Pin `pydantic==2.10.6` if Gradio 4 JSON schema generation fails.
- Remove component kwargs unsupported by the chosen version, for example `gr.Video(loop=True)` on older Gradio.

### Gradio 4 and Python 3.13

Symptoms:

- `ModuleNotFoundError: No module named 'audioop'`
- `ModuleNotFoundError: No module named 'pyaudioop'`
- Error occurs while importing `gradio`, `pydub`, or `processing_utils`.

Fix:

```yaml
python_version: "3.10"
```

Quote the value.

### Gradio JSON Schema / Jinja Launch Errors

Symptoms:

- `TypeError: argument of type 'bool' is not iterable`
- `TypeError: unhashable type: 'dict'`
- `ValueError: When localhost is not accessible, a shareable link must be created`
- Happens during `demo.launch()` before the page fully starts.

Fix options:

- Try a known stable Gradio 4 SDK such as `4.36.1` for older apps.
- Pin `pydantic==2.10.6`.
- Remove unsupported component kwargs.
- Avoid forcing `share=True` on Spaces unless there is no better fix; Spaces should serve through the platform.

### ZeroGPU Torch Compatibility

Symptoms:

- `CONFIG_ERROR`: torch version not compatible with ZeroGPU.
- Runtime message lists supported versions.
- Pip build layer injects `torch<=...`.

Fix:

- Use one of the versions in the runtime error.
- Pin matching `torchvision` and `torchaudio`.
- Avoid unpinned `torchvision` and `torchaudio`; pip may select incompatible companion wheels.
- Keep `spaces` package present for `@spaces.GPU`.

Common pair examples, verify against current runtime:

```text
torch==2.10.0 / torchvision==0.25.0 / torchaudio==2.10.0
torch==2.11.0 / torchvision==0.26.0 / torchaudio==2.11.0
```

### Diffusers and Transformers Mismatch

Symptoms:

- `cannot import name 'Dinov2WithRegistersConfig' from 'transformers'`
- `Failed to import diffusers.models.autoencoders.autoencoder_kl`
- The app pins old `transformers` but leaves `diffusers` unpinned.

Fix:

- Pin `diffusers` to a version compatible with the transformer pin.
- Or upgrade `transformers` if the model and app code support it.
- Avoid broad unpinned `diffusers` in old SDXL/Kolors/Florence apps.

Examples:

```text
transformers==4.43.2 with diffusers==0.31.0
transformers==4.46.3 with diffusers==0.32.2
```

Treat these as starting points, not universal truth.

### Florence Remote Code and FlashAttention

Symptoms:

- Florence remote code demands `flash_attn` even though the app does not need it.
- `ImportError: modeling file requires flash_attn`
- Runtime install of `flash-attn` fails or is too slow.

Fix:

Patch `transformers.dynamic_module_utils.get_imports` before `from_pretrained`:

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
    model = AutoModelForCausalLM.from_pretrained(model_id, trust_remote_code=True)
    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
```

If it then requests `einops`, add `einops` to requirements. Do not remove real required imports blindly.

### Hub Download Timeouts at Import

Symptoms:

- `ReadTimeout`
- `LocalEntryNotFoundError`
- App crashes during `snapshot_download` or `from_pretrained`.

Fix:

- Increase Hub timeouts with environment variables.
- Retry downloads.
- Prefer `snapshot_download(..., max_workers=2, etag_timeout=60)` for large repos.
- Load from the local snapshot path.

Pattern:

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

### Heavy Model Loading on ZeroGPU

Symptoms:

- Space reaches `APP_STARTING` for a long time.
- App loads CUDA models at module import.
- CPU hardware reports no NVIDIA driver.
- ZeroGPU app crashes before any decorated function runs.

Fix:

- Launch the Gradio UI first.
- Lazy-load CUDA models inside functions decorated with `@spaces.GPU`.
- Keep globals initialized to `None`.
- Use helper functions such as `get_pipeline()` that load on first GPU call.

Pattern:

```python
pipe = None

def get_pipe():
    global pipe
    if pipe is None:
        pipe = Pipeline.from_pretrained(...).to("cuda")
    return pipe

@spaces.GPU(duration=120)
def run(prompt):
    return get_pipe()(prompt).images[0]
```

Do not initialize GPU models at import time in ZeroGPU apps unless the platform explicitly supports it.

### Runtime Pip Installs

Runtime installs are a last resort, but sometimes needed for legacy packages that require torch to already be installed.

Use a conditional install:

```python
import importlib.util
import subprocess
import sys

def ensure_runtime_package(module_name, requirement):
    if importlib.util.find_spec(module_name) is not None:
        return
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-build-isolation", requirement],
        check=True,
    )
```

Use only when:

- Build isolation cannot see torch.
- A compiled extension must match the runtime torch/CUDA ABI.
- A package is not available as a compatible wheel.

Avoid unconditional `subprocess.run("pip install ...", shell=True)` at import time. It hides failures and slows every restart.

### Compiled CUDA Extensions

Symptoms:

- Undefined symbols from `.so` files.
- CUDA version mismatch.
- `IndexError: list index out of range` in `_get_cuda_arch_flags`.
- Wheels built for an older torch ABI.

Fix sequence:

1. Prefer a wheel compiled for the exact torch/CUDA runtime.
2. If none exists, compile from source with `--no-build-isolation` after torch is installed.
3. Set `TORCH_CUDA_ARCH_LIST` when no GPU is visible during compilation.
4. For A10G, `TORCH_CUDA_ARCH_LIST=8.6` is usually appropriate.
5. If CUDA compiler version mismatches torch CUDA version, align torch to a supported version closer to the runtime toolchain.

### Storage Limit and Example Caching

Symptoms:

- `Workload evicted, storage limit exceeded`
- CPU utility Space caches examples or creates outputs at startup.

Fix:

- Disable example caching unless explicitly needed.
- Remove stale generated outputs from the repo.
- Do not commit cache directories.
- Use temporary directories and cleanup callbacks.

```python
gr.Examples(..., cache_examples=False)
```

### Real-ESRGAN and pkg_resources

Symptoms:

- `ModuleNotFoundError: No module named 'pkg_resources'`
- `Failed to build git+https://github.com/inference-sh/Real-ESRGAN.git`
- App then crashes on `from RealESRGAN import RealESRGAN`.

Fix:

- Add `setuptools<81`.
- Install Real-ESRGAN conditionally with `--no-build-isolation`.
- Make the install checked, not silent.

## Editing Requirements

Prefer narrow pins over broad latest upgrades. When fixing requirements:

- Pin the root conflict and its companion packages.
- Remove duplicate packages.
- Remove unused packages that cause resolver conflicts.
- Avoid `torch`, `torchvision`, `diffusers`, `transformers`, `gradio`, and `huggingface_hub` all floating together.
- Use dry-run resolver checks when feasible:

```powershell
python -m pip install --dry-run -r requirements.txt
```

For Linux/Python wheel checks:

```powershell
python -m pip install --dry-run --only-binary=:all: --platform manylinux_2_28_x86_64 --python-version 3.10 --implementation cp --abi cp310 -r requirements.txt
```

This does not perfectly emulate Hugging Face, but it catches many impossible pins.

## Verification

Always verify in layers:

1. Local syntax:

```powershell
python -m py_compile app.py
python -m compileall -q app.py package_dir
```

2. Git cleanliness:

```powershell
git status --short
```

3. Push with in-memory auth.

4. Poll runtime:

```powershell
Invoke-RestMethod -Uri "https://huggingface.co/api/spaces/USER/SPACE/runtime"
```

5. Fetch the public Space page when applicable:

```powershell
Invoke-WebRequest -Uri "https://USER-SPACE.hf.space/" -UseBasicParsing -TimeoutSec 60
```

6. If user reported an action failure, test the same action path when practical. A `RUNNING` stage only proves the app server started.

Poll patiently. Heavy ML Spaces can spend minutes in `BUILDING` or `APP_STARTING`. Do not stack speculative commits while a build is still progressing unless logs reveal a deterministic next failure.

## Pushing

Use scoped commits:

```powershell
git add README.md requirements.txt app.py
git commit -m "Fix Space runtime dependencies"
```

Push without storing the token:

```powershell
$token = $env:HF_TOKEN
$basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("__token__:$token"))
git -c http.extraheader="Authorization: Basic $basic" push origin main
```

After pushing, do not declare success until Hugging Face reports `RUNNING` and any relevant page/request check passes.

## User Communication

Keep the user oriented:

- State which Space you are fixing.
- Say whether it is public, private, running, sleeping, build-error, or runtime-error.
- Name the root cause once known.
- Mention when a push triggers a rebuild.
- If the user narrows scope, obey immediately.
- If the user says not to touch private Spaces, stop all private polling and work.

Final responses should include:

- Which Spaces were fixed.
- Current runtime states.
- Any Spaces intentionally skipped.
- Any tests performed, including page HTTP status.
- A reminder to rotate tokens if the token appeared in chat.

## References

Use `references/failure-patterns.md` for more examples and exact symptoms. Use `scripts/space_status.py` for quick public or explicitly authorized authenticated scans.
