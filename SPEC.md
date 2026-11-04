# generate-veo-video specification

Version 0.4.0 (2026-11-03; code 0.4.0). Owner: Chuck Forsyth.
Repository: `charles-forsyth/generate-veo-video` (local checkout `~/Projects/Gen-Video-IVXX`). License: MIT.

## 1. Purpose and scope

`generate-veo-video` (executable `generate-veo`) is a standalone Python CLI for generating and extending videos using Google's **Gemini Omni Flash** (`gemini-omni-1.1-flash`) multimodal model via the Gemini Interactions API, serving as the production successor to the retired Veo 3.1 preview endpoints (`veo-3.1-generate-preview`, `veo-3.1-fast-generate-preview`, `veo-3.1-lite-generate-preview`). It supports:

1. **Text-to-Video** (`generate-veo "prompt"`)
2. **Image-to-Video** (`--image start.png`)
3. **First/Last Frame Interpolation (Morphing)** (`--image start.png --last-frame end.png`)
4. **Reference-Guided Generation** (`--ref-images ref1.png ref2.png` up to 3 asset references)
5. **Video Extension** (`--video prev_clip.mp4`)

## 2. Design decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Dedicated per-tool config `~/.config/generate-veo/.env` (`0600`) | Loaded at startup; never walks up directory trees to `~/.env`. Drops any inherited `GOOGLE_API_KEY` from `os.environ` in `get_client()` so the `google-genai` SDK cannot silently use another tool's key over `GEMINI_API_KEY`. |
| D2 | Gemini Omni Flash 1.1 with quality tiers (`standard`, `fast`, `lite`) | Maps CLI tiers (`--model {standard,fast,lite}`) to `gemini-omni-1.1-flash` with resolution presets (`standard` = 1080p, `fast` = 720p, `lite` = 720p). Retired Veo 3.1 preview IDs in config/env are automatically upgraded with a warning. |
| D3 | Interactions API with background polling | Uses `client.interactions.create(background=True)` and polls `client.interactions.get(id=...)` to prevent client-side HTTP read timeouts on long video generations. Supports base64 inline decoding as well as Files API download for video output. |
| D4 | Exponential backoff on transient API errors | Wraps API calls in `call_with_retry` to handle `429`, `500`, and `503` rate limits or temporary service unavailability cleanly. |
| D5 | Bounded polling loop (`POLLING_TIMEOUT_SEC = 900`) | Polls `client.interactions.get` with adaptive intervals (5s to 15s) with elapsed-time progress output and aborts cleanly if an operation exceeds 15 minutes. |

## 3. Architecture

```text
generate-veo CLI (generate_veo3_video.py)
  |-- Config loader
  |     |-- ~/.config/generate-veo/.env (GEMINI_API_KEY, VEO_MODEL, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION)
  |     `-- get_client() -> pops GOOGLE_API_KEY; genai.Client(api_key=GEMINI_API_KEY) or Vertex AI fallback
  |-- History manager (.veo_history.json)
  |     |-- --history -> display_history()
  |     `-- --rerun N -> reloads prompt N from history
  |-- Input & media loaders
  |     |-- load_image_from_path(path) -> {"type": "image", "data": base64, "mime_type": ...}
  |     |-- prepare_video_input(client, path) -> inline base64 or client.files.upload
  |     `-- Reference images wrapped as image content items (max 3)
  |-- Retry wrapper (call_with_retry) -> exponential backoff on 429/500/503
  `-- Generation & polling (generate_video())
        |-- client.interactions.create(model=gemini-omni-1.1-flash, input=..., response_format=..., background=True)
        |-- Adaptive polling loop up to POLLING_TIMEOUT_SEC (900s)
        `-- base64 decode (inline data) or client.files.download(uri) -> atomic write to output.mp4
```

### Module map

| File | Responsibility |
|---|---|
| `generate_veo3_video.py` | Single-module CLI: config loading, `MODELS` map, `get_client()`, `call_with_retry()`, `load_image_from_path()`, `prepare_video_input()`, `generate_output_filename()`, `generate_video()`, `main()`. |
| `tests/test_generate_veo.py` | Unit tests covering image loading, config construction, retry logic, first/last frame, polling loop, and file saving. |

## 4. Models and cost model

| Tier alias (`--model`) | Model ID | Resolution / Audio | List price (USD / second) | 4s clip | 8s clip |
|---|---|---|---|---|---|
| `lite` | `gemini-omni-1.1-flash` | 720p w/ audio | ~$0.10 / s | ~$0.40 | ~$0.80 |
| `fast` | `gemini-omni-1.1-flash` | 720p w/ audio | ~$0.10 / s | ~$0.40 | ~$0.80 |
| `standard` (default) | `gemini-omni-1.1-flash` | 1080p w/ audio | ~$0.15 / s | ~$0.60 | ~$1.20 |

## 5. Configuration (`~/.config/generate-veo/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | `None` | Gemini API key restricted to `generativelanguage.googleapis.com`. Preferred authentication method. |
| `VEO_MODEL` | `gemini-omni-1.1-flash` | Default model ID or tier when `--model` is omitted. |
| `GOOGLE_CLOUD_PROJECT` | `"ucr-research-computing"` | GCP project ID for Vertex AI fallback when `GEMINI_API_KEY` is unset. |
| `GOOGLE_CLOUD_LOCATION` | `"us-central1"` | GCP region for Vertex AI fallback. |

## 6. CLI interface

```text
generate-veo [prompt]
             [--output-file FILE | -o FILE]
             [--duration {4,6,8}]                  # default: 8
             [--aspect-ratio {16:9,9:16}]          # default: 16:9
             [--negative-prompt TEXT]
             [--image PATH]
             [--last-frame PATH]                   # requires --image
             [--ref-images PATH [PATH ...]]        # max 3
             [--video PATH]
             [--no-audio]                          # ignored (Gemini Omni Flash generates native audio)
             [--seed INT]
             [--model {fast,lite,standard}]
             [--history]
             [--rerun INT]
```

Validation rules:
- Passing `--last-frame` without `--image` exits with error (`--last-frame requires --image to be specified.`).
- Passing more than 3 `--ref-images` exits with error (`Maximum of 3 reference images allowed.`).
- When `-o` / `--output-file` is omitted, `generate_output_filename(prompt)` builds `<sanitized_slug>.mp4` (appending `_1`, `_2` if the file already exists in cwd).

## 7. Requirements traceability

| ID | Requirement | Verified by |
|---|---|---|
| REQ-MEDIA-1 | `load_image_from_path` reads bytes and detects MIME type (`image/png`, `image/jpeg`), returning `None` on missing files. | `tests/test_generate_veo.py::test_load_image_from_path_success`, `test_load_image_from_path_failure` |
| REQ-CFG-1 | `generate_video` sets model `gemini-omni-1.1-flash`, duration, aspect ratio, and resolution in `response_format`. | `tests/test_generate_veo.py::test_generate_video_config_construction` |
| REQ-CFG-2 | Providing `--image` structures multimodal input with image and text content items and sets `task="image_to_video"`. | `tests/test_generate_veo.py::test_generate_video_with_image` |
| REQ-CFG-3 | Providing `--last-frame` alongside `--image` arranges first and last frame image items for morphing interpolation. | `tests/test_generate_veo.py::test_generate_video_first_and_last_frame` |
| REQ-RETRY-1 | `call_with_retry` automatically retries transient 429/500/503 errors with exponential backoff. | `tests/test_generate_veo.py::test_call_with_retry_transient_error` |
| REQ-POLL-1 | `generate_video` polls `client.interactions.get` until `interaction.status == "completed"` and downloads/saves the video atomically. | `tests/test_generate_veo.py::test_generate_video_polling_loop`, `test_generate_video_save` |

## 8. Known gaps and backlog

- **K1 (Confirmed):** `HISTORY_FILE = ".veo_history.json"` is relative to the current working directory rather than `~/.config/generate-veo/history.json`.
- **K2 (Confirmed):** `generate-veo` and `vidius` overlap in scope; `vidius` is the packaged multi-module successor used by Mirage (`~/Videos/Vidius` default output dir), while `generate-veo` remains maintained for standalone CLI scripting.
