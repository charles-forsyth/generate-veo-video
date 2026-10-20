# generate-veo-video specification

Version 0.3.0 (2026-10-20; code 0.3.0). Owner: Chuck Forsyth.
Repository: `charles-forsyth/generate-veo-video` (local checkout `~/Projects/Gen-Video-IVXX`). License: MIT.

## 1. Purpose and scope

`generate-veo-video` (executable `generate-veo`) is a standalone Python CLI for generating and extending videos with Google's **Veo 3.1** model family (`veo-3.1-generate-preview`, `veo-3.1-fast-generate-preview`, `veo-3.1-lite-generate-preview`). It supports:

1. **Text-to-Video** (`generate-veo "prompt"`)
2. **Image-to-Video** (`--image start.png`)
3. **First/Last Frame Interpolation (Morphing)** (`--image start.png --last-frame end.png`)
4. **Reference-Guided Generation** (`--ref-images ref1.png ref2.png` up to 3 asset references)
5. **Video Extension** (`--video prev_clip.mp4`)

## 2. Design decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Dedicated per-tool config `~/.config/generate-veo/.env` (`0600`) | Loaded at startup; never walks up directory trees to `~/.env`. Drops any inherited `GOOGLE_API_KEY` from `os.environ` in `get_client()` so the `google-genai` SDK cannot silently use another tool's key over `GEMINI_API_KEY`. |
| D2 | Three Veo 3.1 tiers (`standard`, `fast`, `lite`) | Maps friendly CLI tiers (`--model {standard,fast,lite}`) or `VEO_MODEL` env config to `veo-3.1-generate-preview`, `veo-3.1-fast-generate-preview`, and `veo-3.1-lite-generate-preview`. Retired Veo 2.0/3.0 IDs are excluded. |
| D3 | Gemini Developer API vs Vertex AI config adaptation | The Gemini Developer API (`api_key=GEMINI_API_KEY`) rejects `enhance_prompt` and `generate_audio` fields in `GenerateVideosConfig` (audio is always on) and requires `client.files.download(file=video_obj)` before `.save()`. Vertex AI mode (`vertexai=True`) passes `enhance_prompt=True`. |
| D4 | Bounded polling loop (`POLLING_TIMEOUT_SEC = 900`) | Polls `client.operations.get(operation)` every 10 seconds with elapsed-time progress output and aborts cleanly if an operation exceeds 15 minutes. |

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
  |     |-- load_image_from_path(path) -> types.Image(image_bytes=..., mime_type=...)
  |     |-- load_video_from_path(path) -> types.Video(video_bytes=..., mime_type=...)
  |     `-- Reference images wrapped as types.VideoGenerationReferenceImage(image=..., reference_type="ASSET")
  `-- Generation & polling (generate_video())
        |-- client.models.generate_videos(model=resolved_model, prompt=..., image=..., video=..., config=...)
        |-- 10s polling loop up to POLLING_TIMEOUT_SEC (900s)
        `-- client.files.download(file=video_obj) (API key mode) -> video_obj.save(output_filename)
```

### Module map

| File | Responsibility |
|---|---|
| `generate_veo3_video.py` | Single-module CLI: config loading, `MODELS` map, `get_client()`, `load_image_from_path()`, `load_video_from_path()`, `generate_output_filename()`, `generate_video()`, `main()`. |
| `tests/test_generate_veo.py` | Unit tests covering image loading, config construction, polling loop, and file saving. |

## 4. Models and cost model

| Tier alias (`--model`) | Model ID | Resolution / Audio | List price (USD / second) | 4s clip | 8s clip |
|---|---|---|---|---|---|
| `lite` | `veo-3.1-lite-generate-preview` | 720p w/ audio | $0.05 / s | $0.20 | $0.40 |
| `fast` | `veo-3.1-fast-generate-preview` | 720p w/ audio | $0.10 / s | $0.40 | $0.80 |
| `standard` (default) | `veo-3.1-generate-preview` | 720p w/ audio | $0.40 / s | $1.60 | $3.20 |

## 5. Configuration (`~/.config/generate-veo/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | `None` | Gemini API key restricted to `generativelanguage.googleapis.com`. Preferred authentication method. |
| `VEO_MODEL` | `veo-3.1-generate-preview` | Default model ID or tier when `--model` is omitted. |
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
             [--no-audio]                          # ignored on Veo 3.1 (always generates audio)
             [--seed INT]
             [--model {fast,lite,standard}]
             [--history]
             [--rerun INT]
```

Validation rules:
- Passing `--last-frame` without `--image` exits with error (`--last-frame requires --image to be specified`).
- Passing more than 3 `--ref-images` exits with error (`Maximum of 3 reference images allowed`).
- When `-o` / `--output-file` is omitted, `generate_output_filename(prompt)` builds `<first_five_words_slug>.mp4` (appending `_1`, `_2` if the file already exists in cwd).

## 7. Requirements traceability

| ID | Requirement | Verified by |
|---|---|---|
| REQ-MEDIA-1 | `load_image_from_path` reads bytes and detects MIME type (`image/png`, `image/jpeg`), returning `None` on missing files. | `tests/test_generate_veo.py::test_load_image_from_path_success`, `test_load_image_from_path_failure` |
| REQ-CFG-1 | `GenerateVideosConfig` sets `duration_seconds`, `aspect_ratio`, `negative_prompt`, and `person_generation="allow_all"` for text-to-video. | `tests/test_generate_veo.py::test_generate_video_config_construction` |
| REQ-CFG-2 | Providing `--image` switches `person_generation` to `"allow_adult"` as required by Veo safety policies. | `tests/test_generate_veo.py::test_generate_video_with_image` |
| REQ-POLL-1 | `generate_video` polls `client.operations.get` until `operation.done` is True and downloads/saves the resulting video. | `tests/test_generate_veo.py::test_generate_video_polling_loop`, `test_generate_video_save` |

## 8. Known gaps and backlog

- **K1 (Confirmed):** `HISTORY_FILE = ".veo_history.json"` is relative to the current working directory rather than `~/.config/generate-veo/history.json`, leaving dotfiles in working directories when invoked without `--no-history`.
- **K2 (Confirmed):** `generate-veo` and `vidius` overlap in scope; `vidius` is the packaged multi-module successor used by Mirage (`~/Videos/Vidius` default output dir, retry loop on `503/429`), while `generate-veo` remains installed for standalone CLI scripts.
