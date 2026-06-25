# ffmpeg-media (example-harness module)

A small, **config-only** example module for repositories that render short-form
video with FFmpeg. It ships render defaults plus the JSON Schema that validates
them — no skills, no executable code, no provider-specific wiring.

> Opt-in. This module is illustrative. Copy the pieces you need into your own
> harness and adjust the values for your pipeline.

## What it provides

| File | Purpose |
|------|---------|
| `harness/config/ffmpeg-defaults.json` | Default render parameters for a vertical (portrait) short-video pipeline. |
| `harness/schemas/render-config.schema.json` | JSON Schema (draft 2020-12) that validates a render config against the same shape. |

## Config fields

`ffmpeg-defaults.json` describes a single render pass:

- `resolution` — output frame size as `WxH` (default `1080x1920`, i.e. vertical 9:16).
- `fps` — output frame rate.
- `ken_burns` — slow pan/zoom on still images: `zoom_factor`, `motion` (`zoom-in` | `zoom-out`).
- `transition` — between-scene transition: `type` (`cut`), `duration_ms`.
- `caption` — burn-in subtitle styling: `burn_in`, `font`, `font_size`, `outline`.
- `safe_area` — optional title-safe inset: `enabled`, `scale_pct`, `margin_color`.
- `first_scene` — optional opening-shot emphasis: `impact_enabled`, `duration_sec`, `zoom_start`, `zoom_end`.
- `bgm` — background music toggle: `enabled`.
- `timeout_sec` — hard cap on the render subprocess.

The `font` value (`Pretendard`) is just a default font name; substitute any font
your renderer can resolve. Set `bgm.enabled` / `safe_area.enabled` /
`first_scene.impact_enabled` to opt into those passes.

## Validating a config

The schema is plain JSON Schema (draft 2020-12) and works with any standard
validator. Example with Python's `jsonschema`:

```python
import json
from jsonschema import validate

config = json.load(open("harness/config/ffmpeg-defaults.json"))
schema = json.load(open("harness/schemas/render-config.schema.json"))
validate(instance=config, schema=schema)
```

Note: the schema marks only `resolution` and `fps` as required and forbids
unknown top-level keys (`additionalProperties: false`), so trim or extend the
properties block if your pipeline needs a different shape.

## Adapting it

1. Copy `harness/config/ffmpeg-defaults.json` into your repo's config directory.
2. Copy `harness/schemas/render-config.schema.json` alongside your other schemas.
3. Wire the validator into your render entrypoint (or a pre-render check).
4. Tune resolution/fps/caption/timeout for your target platform.
