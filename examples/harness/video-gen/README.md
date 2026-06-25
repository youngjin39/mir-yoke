# video-gen (example-harness module)

A **config-only** example module for repositories that generate short-form video
with a self-hosted [ComfyUI](https://github.com/comfyanonymous/ComfyUI) backend.
It ships a ComfyUI WAN image-to-video workflow template, the image/video
generation defaults that drive it, and the JSON Schema that validates the
config — no skills, no executable code, no provider API keys.

> Opt-in. This module is illustrative. Copy the pieces you need into your own
> harness and replace the `__PLACEHOLDER__` slots with your own values.

## What it provides

| File | Purpose |
|------|---------|
| `harness/config/comfyui-gen.json` | Default ComfyUI image- and video-generation parameters (server endpoint, model slots, sampler, steps, cfg, quality gates). |
| `harness/config/comfyui-wan-i2v.workflow.json` | A ComfyUI WAN image-to-video workflow graph, parameterized with `__PLACEHOLDER__` slots a runner fills at submit time. |
| `harness/schemas/comfyui-gen.schema.json` | JSON Schema (draft 2020-12) that validates `comfyui-gen.json`. |

## Placeholders you must fill

Both config files use `__UPPER_SNAKE__` placeholders so nothing local is baked in.
Replace them before use:

| Placeholder | Meaning |
|-------------|---------|
| `__COMFYUI_SERVER__` | Base URL of your ComfyUI server, e.g. `http://127.0.0.1:8188`. |
| `__CHECKPOINT_NAME__` | Image checkpoint file as ComfyUI sees it (e.g. an SDXL `.safetensors`). |
| `__UNET_NAME__` | Video diffusion UNet weights file (e.g. a WAN `.safetensors`). |
| `__CLIP_NAME__` | Text-encoder / CLIP weights file. |
| `__VAE_NAME__` | VAE weights file. |
| `__START_IMAGE__` | Input image filename for image-to-video. |
| `__PROMPT__` / `__NEGATIVE_PROMPT__` | Positive / negative text prompts. |
| `__WIDTH__` `__HEIGHT__` `__FRAME_COUNT__` `__FPS__` | Output geometry and length. |
| `__SEED__` `__STEPS__` `__CFG__` `__SAMPLER_NAME__` `__SCHEDULER__` `__SAMPLING_SHIFT__` | Sampler controls. |
| `__SAVE_PREFIX__` | Output filename prefix. |

The model files are referenced **by name only** — ComfyUI resolves them inside
its own `models/` directory, so no absolute paths appear here. Point ComfyUI at
your own model directory; this module never hardcodes one.

## How the pieces fit

`comfyui-gen.json` is the high-level config your pipeline reads: which backend,
which server, which model slots, sampler defaults, and quality gates.
`video_gen.comfyui.workflow_template` points at
`comfyui-wan-i2v.workflow.json`, the actual ComfyUI graph your runner POSTs to
`{server}/prompt` after substituting the placeholder slots with values derived
from the config (and per-shot prompt/image/seed).

`video_gen.enabled` defaults to `false` — image generation is the default path;
flip it to `true` to opt into the image-to-video stage.

## Validating a config

The schema is plain JSON Schema (draft 2020-12) and works with any standard
validator. Example with Python's `jsonschema`:

```python
import json
from jsonschema import validate

config = json.load(open("harness/config/comfyui-gen.json"))
schema = json.load(open("harness/schemas/comfyui-gen.schema.json"))
validate(instance=config, schema=schema)
```

The schema forbids unknown keys (`additionalProperties: false`) on the
generation blocks, so trim or extend the properties block if your pipeline needs
a different shape.

## Adapting it

1. Copy `harness/config/*.json` into your repo's config directory.
2. Copy `harness/schemas/comfyui-gen.schema.json` alongside your other schemas.
3. Replace every `__PLACEHOLDER__` with your own server URL, model filenames, and
   sampler values.
4. Wire the workflow template into your ComfyUI submit step (substitute slots,
   POST to `{server}/prompt`, poll for the result).

## Related

For the downstream FFmpeg muxing/caption/render stage (assembling generated
clips into a finished vertical short), see the sibling `ffmpeg-media` module.
