# Generate Veo Video CLI - Project Context

## Project Overview
**generate-veo-video** is a powerful Python CLI tool designed to generate high-quality videos using Google's **Veo 3.1** model via the Vertex AI / Gemini API. It supports text-to-video, image-to-video, style control via reference images, and video extension capabilities.

## Tech Stack
*   **Language:** Python 3.10+
*   **Package Manager:** `uv`
*   **Build System:** `hatchling`
*   **Core Libraries:** `google-genai`, `rich`, `pydantic`, `python-dotenv`
*   **Testing:** `pytest`
*   **Linting:** `ruff`

## Key Files
*   `generate_veo3_video.py`: The main entry point and core logic script. Handles argument parsing, API interaction, and file operations.
*   `pyproject.toml`: Configuration for dependencies, build settings, and script entry points (`generate-veo`).
*   `.github/workflows/ci.yml`: CI pipeline configuration for automated testing and linting.
*   `tests/`: Directory containing test suites (e.g., `test_generate_veo.py`).

## Environment Configuration
The application relies on environment variables for authentication and project settings. These are loaded from `.env` files in the following order of precedence:
1.  Current working directory `.env`
2.  `~/.config/deepresearch/.env`
3.  `~/.env`

**Required Variables:**
*   `GOOGLE_CLOUD_PROJECT`: Your GCP Project ID (default: `ucr-research-computing`)
*   `GOOGLE_CLOUD_LOCATION`: GCP Region (default: `us-central1`)
*   `GEMINI_API_KEY`: API Key for Gemini (optional, falls back to Vertex AI ADC)

## Development Workflow

### 1. Setup
This project uses `uv` for fast dependency management.
```bash
# Install dependencies
uv sync --dev
```

### 2. Running the Tool
You can run the script directly using `uv`:
```bash
uv run generate_veo3_video.py "A cinematic drone shot of a futuristic city."
```

### 3. Testing
Run the test suite using `pytest`:
```bash
uv run pytest tests/
```

### 4. Linting & Formatting
Ensure code quality with `ruff`:
```bash
uv run ruff check .
```

## Common Usage Patterns

*   **Text-to-Video:**
    ```bash
    uv run generate_veo3_video.py "Prompt text..." --aspect-ratio 16:9
    ```
    Or via pipe:
    ```bash
    echo "Prompt text..." | uv run generate_veo3_video.py --aspect-ratio 16:9
    ```
*   **Image-to-Video:**
    ```bash
    uv run generate_veo3_video.py "Animate this image..." --image ./path/to/image.png
    ```
*   **Reference Images:**
    ```bash
    uv run generate_veo3_video.py "Style transfer..." --ref-images ./style1.png ./style2.png
    ```

## Contribution Guidelines
*   Follow the pull request workflow: Fork -> Branch -> Test -> PR.
*   Ensure all tests pass and code is linted before submitting.
*   Adhere to the existing project structure and naming conventions.
