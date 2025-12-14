# Generate Veo Video CLI

A powerful CLI tool for generating videos using Google's **Veo 3.1** model via the Vertex AI / Gemini API.

## Features

- **Text-to-Video**: Generate high-quality videos from text prompts.
- **Image-to-Video**: Animate static images.
- **Reference Images**: Use up to 3 reference images to guide style and character consistency.
- **First/Last Frame Control**: Interpolate between a starting and ending frame.
- **Video Extension**: Extend existing Veo-generated videos.
- **Environment Config**: Loads API keys and project settings from `.env` files (local or home directory).

## Installation

Install directly from GitHub using `uv`:

```bash
uv tool install git+https://github.com/charles-forsyth/generate-veo-video.git
```

## Configuration

The tool expects the following environment variables. You can set them in a `.env` file in your home directory or the working directory.

```bash
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GEMINI_API_KEY=AIza... # Optional, falls back to Vertex AI ADC if not present
```

## Usage

Once installed, use the `generate-veo` command:

### Basic Generation
```bash
generate-veo "A cinematic drone shot of a futuristic cyberpunk city at night, neon lights, rain."
```

### Image-to-Video
```bash
generate-veo "Animate this character walking" --image ./character.png
```

### Morphing (First & Last Frame)
```bash
generate-veo "Morph between these two images" --image ./start.png --last-frame ./end.png
```

### Reference Images (Style Transfer)
```bash
generate-veo "A girl in a red dress running" --ref-images ./style1.png ./style2.png
```

### Options
- `--duration`: 4, 6, or 8 seconds (Default: 8)
- `--aspect-ratio`: 16:9 or 9:16 (Default: 16:9)
- `--output-file`: Specify custom output filename.
- `--history`: View prompt history.
- `--rerun <N>`: Rerun a previous prompt from history.

## Development

To develop locally:

1. Clone the repo.
2. Run with `uv`:
   ```bash
   uv run generate_veo3_video.py "Prompt..."
   ```
