# Hugging Face Spaces Verification Playbook

Load this reference before declaring a Space fixed, when a Space reaches `RUNNING` but the user still sees an internal server error, or when multiple pushed fixes are waiting on builds.

## Table of Contents

- Verification ladder
- Polling runtime state
- Checking public pages
- RUNNING but internal server error
- Testing request paths
- Build and runtime logs
- Wait versus patch
- Final report

## Verification Ladder

Verify in this order:

1. Git push succeeded.
2. Runtime endpoint changed to `BUILDING` or `APP_STARTING`.
3. Runtime endpoint reaches `RUNNING`.
4. Public page returns HTTP 200 for public Spaces.
5. The user-reported interaction path works or has been inspected.
6. Hardware current/requested values are expected.
7. Logs do not show a fresh deterministic error.

Do not stop at step 3 when the user reported a page-level or button-level failure.

## Polling Runtime State

Public:

```bash
curl -fsS "https://huggingface.co/api/spaces/USER/SPACE/runtime"
```

Private, only with explicit authorization:

```bash
curl -fsS \
  -H "Authorization: Bearer $HF_TOKEN" \
  "https://huggingface.co/api/spaces/USER/SPACE/runtime"
```

With the bundled script:

```bash
python scripts/space_status.py --ids USER/SPACE
python scripts/space_status.py --ids USER/PRIVATE-SPACE --token-env HF_TOKEN
```

Interpretation:

- `BUILDING`: wait unless logs already show a deterministic failure.
- `APP_STARTING`: wait for heavy apps, but investigate if it persists.
- `RUNNING`: fetch the page or test the path.
- `BUILD_ERROR`: read build logs and patch dependencies/config.
- `RUNTIME_ERROR`: read runtime logs and inspect import/startup/request paths.
- `CONFIG_ERROR`: check README frontmatter and ZeroGPU compatibility.
- `SLEEPING`: not a failure unless included by the user.

## Checking Public Pages

Use the official Space URL when available. If deriving it, the common form is:

```text
https://OWNER-SPACE.hf.space/
```

Use a page fetch:

```bash
curl -fsS -L \
  -o /tmp/space.html \
  -w 'HTTP %{http_code}\nbytes %{size_download}\n' \
  "https://OWNER-SPACE.hf.space/"
python - <<'PY'
from pathlib import Path
import re

html = Path("/tmp/space.html").read_text(errors="ignore")
match = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
print("title", match.group(1).strip() if match else "")
PY
```

If the page returns 200 but looks like a platform loading screen only, wait and retry. Heavy Spaces can briefly report running before the frontend is fully useful.

## RUNNING but Internal Server Error

When runtime says `RUNNING` but the page says internal server error, do not repatch blindly. Trigger one page request, then inspect logs.

Likely causes:

- Gradio component config fails during route rendering.
- A component kwarg is unsupported by the pinned Gradio version.
- `demo.launch()` flags conflict with Spaces routing.
- Lazy-loaded model path crashes on first request.
- Top-level import swallowed an install error and later import fails.
- Static asset or custom component frontend build artifact is missing.
- Hardware allocation differs from assumptions in request code.

Checklist:

- Fetch `/` and note HTTP status.
- Check whether runtime state changes to `RUNTIME_ERROR` after the request.
- Inspect recent runtime logs.
- Search app code for recently downgraded Gradio APIs.
- Remove `share=True` unless required.
- Remove unsupported component kwargs rather than upgrading the whole stack.
- If the request path calls a model, verify lazy load is inside the GPU-decorated function.

## Testing Request Paths

For Gradio apps, the page can load while the main function still fails. Test the user-reported path when practical:

- upload path for captioners
- generate button for diffusion apps
- upscale button for image restoration apps
- model export path for 3D apps
- example input if it exercises the same function

If browser/API testing is impractical because the model is huge, inspect the callback function and logs after one manual request. Report the limitation clearly.

## Build and Runtime Logs

Build logs may be available through a Hub logs endpoint. Runtime logs may be available through the Space page or API depending on current Hub behavior and authorization.

Use logs safely:

- Do not fetch private logs unless private inspection is authorized.
- Do not commit logs.
- Do not paste secrets from logs into final output.
- If logs are truncated, use the latest deterministic error, not old failures from previous builds.

Build-log pattern:

```bash
curl -fsS -N \
  -H "Authorization: Bearer $HF_TOKEN" \
  "https://huggingface.co/api/spaces/USER/SPACE/logs/build?tail=200"
```

If unauthenticated public log access fails, use the Space UI or the runtime error payload. Do not add a token for public work unless needed.

## Wait Versus Patch

Wait when:

- The state is `BUILDING` after a recent push.
- The state is `APP_STARTING` and the Space downloads large models.
- No new deterministic error is visible.
- The current build has not used the latest commit yet.

Patch when:

- `BUILD_ERROR`, `RUNTIME_ERROR`, or `CONFIG_ERROR` is stable.
- Logs show a clear missing package, incompatible version, or bad config.
- Page request reproducibly triggers a traceback.
- Hardware/current runtime shows the app cannot run as written.

Avoid repeated pushes before the Hub has finished building the previous commit. It makes causality hard to read and wastes build time.

## Final Report

For each Space, report:

- final stage
- hardware current/requested when relevant
- what was changed
- whether public page returned HTTP 200
- whether user-reported action path was checked
- skipped Spaces and why
- token rotation reminder if a token was pasted in chat

Short example:

```text
owner/example is RUNNING on zero-a10g. I pinned the Gradio 4 stack, added Hub download retries, and removed an unsupported video kwarg. The public page returns HTTP 200; I did not test the full generation path because it requires a long GPU run.
```
