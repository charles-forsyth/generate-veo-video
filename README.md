# Generate Veo Video CLI

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23755693.svg)](https://doi.org/10.5281/zenodo.23755693)

[![CI](https://github.com/charles-forsyth/generate-veo-video/actions/workflows/ci.yml/badge.svg)](https://github.com/charles-forsyth/generate-veo-video/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A CLI tool (`v0.3.0`) for generating and extending videos using Google's **Veo 3.1** models (`standard`, `fast`, `lite`) via the Gemini Developer API or Vertex AI.

See [SPEC.md](SPEC.md) for the full system specification, architecture, cost model, and requirement traceability.

## Features

- **Text-to-Video**: Generate 720p videos with synchronized audio from text prompts.
- **Image-to-Video**: Animate static images (`--image`).
- **Reference Images**: Use up to 3 reference images (`--ref-images`) to guide style and character consistency.
- **First/Last Frame Control**: Interpolate smoothly between a starting and ending frame (`--image` + `--last-frame`).
- **Video Extension**: Extend existing Veo-generated videos (`--video`).
- **Isolated Configuration**: Loads its API key from `~/.config/generate-veo/.env` and strips inherited `GOOGLE_API_KEY` environment variables so it never borrows another tool's key.
- **Model Tiers**: `--model standard|fast|lite` selects Veo 3.1 ($0.40/s), 3.1 Fast ($0.10/s), or 3.1 Lite ($0.05/s).

## Installation

Install directly from GitHub using `uv`:

```bash
uv tool install --python 3.12 git+https://github.com/charles-forsyth/generate-veo-video.git
```

To update to the latest version:
```bash
uv tool upgrade generate-veo-video
```

## Configuration

Create `~/.config/generate-veo/.env` (`chmod 600`) with a Gemini API key restricted to `generativelanguage.googleapis.com`:

```env
GEMINI_API_KEY=AIza...
VEO_MODEL=veo-3.1-lite-generate-preview
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
```

## Usage Examples

### 1. Text-to-Video (Cheapest 4s Lite Tier)
```bash
generate-veo "Sunlight dappling through pine trees in a quiet forest" --model lite --duration 4 -o forest.mp4
```

### 2. Image-to-Video
```bash
generate-veo "The waterfall flows smoothly and mist rises from the pool." --image ./waterfall.png --model lite
```

### 3. Reference Images (Style / Character Consistency)
```bash
generate-veo "A model walking down a runway wearing the referenced dress." --ref-images ./dress.png ./shoes.png
```

### 4. Morphing (First & Last Frame Interpolation)
```bash
generate-veo "A rough pencil sketch fading into a photorealistic render." --image ./sketch.jpg --last-frame ./render.jpg
```

### 5. Video Extension
```bash
generate-veo "The camera pans up to reveal a starlit sky above the mountains." --video ./intro_clip.mp4
```

## Options Reference

| Flag | Description | Default |
|------|-------------|---------|
| `prompt` | Positional text prompt for the video. | — |
| `--output-file`, `-o` | Custom output filename. | Auto-generated from prompt |
| `--model {fast,lite,standard}` | Veo 3.1 tier (`lite` $0.05/s, `fast` $0.10/s, `standard` $0.40/s). | `standard` (or `VEO_MODEL`) |
| `--duration {4,6,8}` | Video duration in seconds. | `8` |
| `--aspect-ratio {16:9,9:16}` | Video aspect ratio. | `16:9` |
| `--negative-prompt` | Elements to avoid in the video. | `None` |
| `--image` | Initial start frame image path. | `None` |
| `--last-frame` | Ending frame image path (requires `--image`). | `None` |
| `--ref-images` | 1 to 3 reference image paths. | `None` |
| `--video` | Path to a Veo-generated video to extend. | `None` |
| `--seed` | Random seed for reproducibility. | `None` |
| `--history` | Show command history. | — |
| `--rerun ID` | Rerun a command from history by 1-based ID. | — |

## Development

```bash
uv sync --python 3.12
uv run --python 3.12 pytest
uv run --python 3.12 ruff check .
```
