# Hugging Face Spaces Failure Patterns

This reference expands the main workflow with concrete examples. Load it when a Space has a build or runtime failure that is not obvious from `README.md`, `requirements.txt`, and `app.py`.

## Build Log Access

The runtime endpoint sometimes truncates errors. Build logs may be available through a Server-Sent Events endpoint:

```powershell
$headers = @{ Authorization = "Bearer $env:HF_TOKEN" }
Invoke-WebRequest `
  -Uri "https://huggingface.co/api/spaces/USER/SPACE/logs/build?tail=200" `
  -Headers $headers `
  -UseBasicParsing
```

Do not use authenticated log endpoints for private Spaces unless explicitly authorized. When private repair is authorized, use an in-memory token header and avoid saving logs that may contain private repo names, file names, or stack traces unless the user requested an artifact.

## README Frontmatter Pitfalls

Use string values for versions:

```yaml
sdk_version: 4.36.1
python_version: "3.10"
```

Unquoted `3.10` may become a numeric YAML value. This can make the build fail with unhelpful errors.

## Gradio Version Selection

Gradio 5 is not always better for old Spaces. Signs that Gradio 4 is required:

- Custom component says `gradio<5`.
- App uses APIs removed or changed in Gradio 5.
- Build resolver reports component conflicts.

Signs that a lower Gradio 4 is required:

- `TypeError: argument of type 'bool' is not iterable` in `gradio_client.utils`.
- `TypeError: unhashable type: 'dict'` in Jinja cache during launch.
- Older custom components work with `4.36.1` but not `4.44.1`.

Known adjustments:

- `gr.Video(loop=True)` is not accepted by some Gradio 4 versions. Remove `loop`.
- Pin `pydantic==2.10.6`.
- Pin `huggingface_hub<1.0`.

## ZeroGPU Pattern

For ZeroGPU apps:

- Keep `import spaces`.
- Decorate GPU work with `@spaces.GPU`.
- Lazy-load CUDA models inside the decorated call.
- Avoid `.to("cuda")` at module import.
- Avoid model downloads at module import when possible, especially huge repositories.

Bad pattern:

```python
pipe = Pipeline.from_pretrained(...).to("cuda")

@spaces.GPU
def run(prompt):
    return pipe(prompt)
```

Better pattern:

```python
pipe = None

def get_pipe():
    global pipe
    if pipe is None:
        pipe = Pipeline.from_pretrained(...).to("cuda")
    return pipe

@spaces.GPU
def run(prompt):
    return get_pipe()(prompt)
```

## Version Matrix Heuristics

When a Space pins one ML library but leaves another floating, expect import failures.

Stable old-SDXL family starting point:

```text
transformers==4.43.2
diffusers==0.31.0
torch==2.10.0
torchvision==0.25.0
```

Flux/TRELLIS newer family starting point:

```text
transformers==4.46.3
diffusers==0.32.2
torch==2.11.0
torchvision==0.26.0
```

Always verify against current Hugging Face runtime errors because ZeroGPU supported versions change.

## Common Missing Packages

Add these only when the traceback proves they are needed:

- `einops`: Florence, SD3, PaliGemma, and custom vision-language models.
- `sentencepiece`: T5, LLaMA-like tokenizers, some prompt enhancers.
- `timm`: Florence and some vision encoders.
- `setuptools<81`: legacy packages that import `pkg_resources`.
- `ninja`: source builds for CUDA extensions.

## Runtime Install Guardrails

Runtime installs can make startup slower and less reproducible. Use them only for packages that need the already-installed torch/CUDA environment.

Always:

- Check whether the module exists first.
- Use `sys.executable -m pip`.
- Use `check=True`.
- Avoid `shell=True`.
- Prefer `--no-build-isolation` when package setup imports torch.

## Large Models and CPU Spaces

CPU Spaces that import a CUDA model at startup often fail with:

```text
RuntimeError: Found no NVIDIA driver on your system
```

Options:

- Move to GPU/ZeroGPU if the Space is intended for GPU.
- Lazy-load under a GPU-decorated function if ZeroGPU.
- Use CPU device only if the model is small enough and latency is acceptable.
- Do not move a private or sleeping Space to new hardware without explicit permission. Private Spaces are supported, but the user's requested scope controls whether they may be inspected, cloned, pushed, restarted, or awakened.

## Storage Hygiene

Before pushing:

```powershell
Get-ChildItem -Directory -Recurse -Filter __pycache__
git status --short
```

Remove:

- `__pycache__`
- `.pytest_cache`
- generated outputs
- model caches
- temporary videos/images
- downloaded checkpoints unless the Space intentionally tracks them

Do not use destructive commands outside the Space clone.

## Final Verification Checklist

For each fixed Space:

- Runtime endpoint reports `RUNNING`.
- Hardware current equals requested, or the current state is expected.
- Public page returns HTTP 200 when the Space is public.
- User-reported interaction path was tested or the limitation is clearly stated.
- No private/sleeping Spaces were touched unless explicitly authorized.
- Token was not stored in the remote or committed.
