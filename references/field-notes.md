# Hugging Face Spaces Field Notes

Load this reference when the obvious traceback is not enough, when a Space has already been patched once and still fails, or when the user asks to repair many Spaces one by one. These notes capture practical lessons from repeated Space repairs while staying Space agnostic.

## Table of Contents

- Scope and identity
- Runtime state is not enough
- Patch discipline
- Model loading and ZeroGPU
- Dependency lessons
- Build and native extension lessons
- Code hygiene lessons
- Private Space handling
- Case families

## Scope and Identity

The display title, pinned list title, and repository slug can differ. Resolve exact Space IDs first through the Hub API or the Space URL. Do not guess from the UI title when pushing.

Treat scope as a hard boundary:

- If the user says public only, do not list, clone, poll, or inspect private Spaces.
- If the user says private Spaces are allowed, use authenticated API/Git only for the explicitly included Spaces or the explicitly included owner.
- Sleeping private Spaces are not failures by default. Do not wake or poll them unless the user explicitly asks.
- If the user excludes one Space by name, keep it excluded even if it is broken.
- If a token appears in chat, use it only in memory and remind the user to rotate it after the work.

When working through many Spaces, keep a visible queue:

```text
Space                Scope    Stage          Action
owner/one            public   BUILD_ERROR    patch requirements
owner/two            public   RUNNING        page check
owner/private-one    private  skipped        user excluded private
```

## Runtime State Is Not Enough

`RUNNING` means the container is serving. It does not prove the app is usable.

Common cases:

- `RUNNING` and page HTTP 200: base launch likely works.
- `RUNNING` and page HTTP 500: launch completed enough for the router, but app rendering, component config, startup request, or route handling is failing.
- `RUNNING` and page loads, but button click fails: the decorated function, model lazy-load path, missing file, input conversion, or GPU function path is broken.
- `APP_STARTING` for a long time: top-level model download/load, build-time import, or cold cache delay.
- `RUNTIME_ERROR` after a page visit: the page request triggered code that was not exercised at import.

For every fixed public Space, fetch the page after the runtime endpoint says `RUNNING`. If the user reported a specific interaction, test or at least inspect that path.

## Patch Discipline

Patch one root cause at a time when logs are deterministic. Avoid stacking speculative changes while a build is still in progress.

Good loop:

1. Read state and latest error.
2. Patch the smallest root cause.
3. Commit with a direct message.
4. Push once.
5. Poll until build resolves.
6. Re-read logs only if the next state proves a new failure.

When the next error changes after a patch, treat that as progress. Many ML Spaces fail in layers: README runtime, dependency resolver, import, model download, then request path.

Prefer narrow changes:

- Pin a companion package instead of upgrading the whole stack.
- Remove one unsupported component kwarg instead of rewriting the UI.
- Move model load into a lazy function instead of changing model behavior.
- Use a runtime install only when the package genuinely needs the already-installed torch/CUDA environment.

## Model Loading and ZeroGPU

ZeroGPU and heavy GPU Spaces should launch the UI before loading CUDA models.

Lessons:

- Do not call `.to("cuda")`, `.cuda()`, or huge `from_pretrained` calls at module import in ZeroGPU apps.
- Keep global model variables as `None`.
- Load the model inside a helper called by a `@spaces.GPU` function.
- Compute the current device inside the request path after GPU allocation, not only once at module import.
- Create `torch.Generator(device=current_device)` with the same device that will run inference.
- If preprocessing needs a model, route preprocessing through the same lazy helper.
- A tiny warm-up can be useful after lazy load, but wrap it so failure does not crash launch unless the warm-up is required.

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
    current_device = "cuda" if torch.cuda.is_available() else "cpu"
    generator = torch.Generator(device=current_device).manual_seed(0)
    return get_pipe()(prompt, generator=generator).images[0]
```

For non-ZeroGPU paid GPU Spaces, lazy loading is still useful when startup download time causes internal server errors or watchdog failures.

## Dependency Lessons

The strongest repeated lesson: do not leave the ML stack floating. A Space that pins one of `torch`, `diffusers`, `transformers`, `gradio`, or `huggingface_hub` but leaves the others floating can break when the Hub image changes.

High-value pins seen repeatedly:

- Gradio 4 apps often need `huggingface_hub<1.0`.
- Older Gradio 4 apps often become stable with `pydantic==2.10.6`.
- Python 3.13 can break old audio dependencies; use `python_version: "3.10"` when that is the safer path.
- Legacy packages that import `pkg_resources` need `setuptools<81`.
- Old SDXL/Kolors/Florence family apps often need `diffusers==0.31.0` with older `transformers`.
- Florence-based apps often need `timm`, `einops`, and sometimes `sentencepiece`.
- Do not list `spaces` twice.
- Remove broad `triton` pins unless the traceback proves they are required.

When resolving:

```bash
python -m pip install --dry-run -r requirements.txt
python -m pip check
```

Dry-run success is not proof for CUDA runtime success, but it catches many resolver mistakes before pushing.

## Build and Native Extension Lessons

Native extension failures are usually ABI problems, not application logic.

Signals:

- `undefined symbol`
- CUDA version mismatch
- torch extension build cannot determine arch
- `IndexError: list index out of range` in `_get_cuda_arch_flags`
- package setup imports torch during build isolation

Useful fixes:

- Align torch, torchvision, torchaudio, xformers, and extension wheels.
- Install torch before source-built extensions, sometimes through `pre-requirements.txt` if the Space uses it.
- Use `--no-build-isolation` when setup must see the installed torch.
- Set `TORCH_CUDA_ARCH_LIST=8.6` for A10G when build logs show missing arch detection.
- Prefer a wheel built for the exact torch/CUDA runtime before compiling from source.

Do not blindly copy CUDA pins between Spaces. Verify current hardware, runtime image, and ZeroGPU supported versions.

## Code Hygiene Lessons

Small app-code fixes often unblock the whole Space:

- Replace unconditional `subprocess.run("pip install ...", shell=True)` with a conditional `sys.executable -m pip` call and `check=True`.
- Avoid `share=True` on Spaces unless it is clearly required.
- Remove unsupported component kwargs, such as a `gr.Video` kwarg not accepted by the pinned Gradio version.
- Keep `demo.launch()` simple on Spaces.
- Add missing imports explicitly rather than relying on transitive package behavior.
- Do not cache Gradio examples by default in storage-limited Spaces.
- Clean generated output directories before committing.

Runtime install pattern:

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

## Private Space Handling

Private Spaces are supported, but safety is stricter:

- Use in-memory auth headers or Git `http.extraheader`.
- Do not put tokens in remotes.
- Do not save private logs to committed files.
- Do not reveal private repo names in final output unless the user already named them or requested a report.
- Do not wake sleeping private Spaces unless explicitly included.
- If the user changes scope and says private Spaces are out, stop private work immediately.

## Case Families

Use these as pattern recognition, not as universal recipes.

### Old Gradio Custom Component App

Typical signals:

- Custom component pins `gradio<5`.
- SDK is set to Gradio 5 or a high Gradio 4.
- Launch fails in schema, Jinja, or client utilities.

Likely repairs:

- Set `sdk_version` to a stable Gradio 4 release used by the component.
- Add `huggingface_hub<1.0`.
- Add `pydantic==2.10.6`.
- Remove unsupported component kwargs.

### Florence Captioner App

Typical signals:

- `trust_remote_code=True`.
- Import demands `flash_attn`.
- `einops` or `timm` missing.
- Download timeout during `from_pretrained`.

Likely repairs:

- Patch `transformers.dynamic_module_utils.get_imports` only around Florence loading.
- Add `einops` or `timm` only when traceback proves it.
- Use `snapshot_download` with retries and load from local snapshot.
- Avoid runtime `pip install flash-attn` unless the model path truly needs it.

### Kolors or Old SDXL App

Typical signals:

- Old `transformers` pin plus unpinned `diffusers`.
- `Dinov2WithRegistersConfig` or autoencoder import failures.
- Large model snapshot times out at startup.

Likely repairs:

- Pin `diffusers` to a version compatible with the transformer pin.
- Add Hub timeout env vars and snapshot retry.
- Avoid unpinned torch companion packages.

### Real-ESRGAN Utility App

Typical signals:

- Runtime install from GitHub.
- `pkg_resources` missing.
- Reinstall happens on every restart.

Likely repairs:

- Add `setuptools<81`.
- Use conditional runtime install with `--no-build-isolation`.
- Use `check=True` so the crash is visible.

### TRELLIS or Native Extension App

Typical signals:

- spconv, xformers, or native extension ABI errors.
- CUDA arch detection fails.
- Heavy top-level model loads keep the Space in `APP_STARTING`.

Likely repairs:

- Align torch and xformers with the runtime.
- Set `TORCH_CUDA_ARCH_LIST` for A10G builds.
- Lazy-load TRELLIS and image generation models inside GPU call paths.
- Remove unsupported UI kwargs after launch gets far enough to render.
