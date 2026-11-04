#!/usr/bin/env python3
import time
import os
import argparse
import re
import json
import mimetypes
import sys
import base64
from dotenv import load_dotenv
from google import genai

# --- ENV & CONFIG SETUP ---
# Load .env from various locations
# The tool reads only its own config file (plus a .env in the current directory),
# so it never borrows another tool's API key.
xdg_config_home = os.getenv("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
CONFIG_PATH = os.path.join(xdg_config_home, "generate-veo", ".env")
load_dotenv(CONFIG_PATH)
load_dotenv(os.path.join(os.getcwd(), ".env"))  # Only a .env in the current dir; never walk up to ~/.env

# Configuration with Env Fallbacks
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "ucr-research-computing")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
API_KEY = os.getenv("GEMINI_API_KEY")

MODELS = {
    "standard": "gemini-omni-1.1-flash",
    "fast": "gemini-omni-1.1-flash",
    "lite": "gemini-omni-1.1-flash",
}

TIER_RESOLUTIONS = {
    "standard": "1080p",
    "fast": "720p",
    "lite": "720p",
}

MODEL_ID = os.getenv("VEO_MODEL", MODELS["standard"])
# Automatically redirect retired Veo preview model IDs to the Omni successor
if "veo" in MODEL_ID.lower():
    print(f"[WARN] Configured model '{MODEL_ID}' is retired. Upgrading to {MODELS['standard']}.")
    MODEL_ID = MODELS["standard"]

HISTORY_FILE = ".veo_history.json"
POLLING_TIMEOUT_SEC = 900  # 15 minutes max wait time


def load_history():
    """Loads the prompt history from the history file."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to load history: {e}")
        return []


def save_history(history):
    """Saves the prompt history to the history file."""
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=4)
    except Exception as e:
        print(f"[WARN] Failed to save history: {e}")


def display_history(history):
    """Displays the prompt history."""
    if not history:
        print("No history found.")
        return
    for i, entry in enumerate(history):
        print(f"{i+1}: {entry['prompt']}")


def get_client():
    """Creates the GenAI client with appropriate authentication."""
    # The key comes from our own config; drop any GOOGLE_API_KEY inherited from the shell
    # so the SDK cannot pick a different key.
    os.environ.pop("GOOGLE_API_KEY", None)
    if API_KEY:
        print("[INFO] Using API Key authentication.")
        return genai.Client(api_key=API_KEY)
    else:
        print(f"[INFO] Using Vertex AI (ADC) authentication for project {PROJECT_ID}")
        return genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)


def call_with_retry(fn, *args, max_retries=5, initial_delay=2.0, **kwargs):
    """Executes a function with exponential backoff on 429, 500, and 503 errors."""
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            err_str = str(e)
            is_retryable = False
            status_code = getattr(e, "status_code", getattr(e, "code", None))
            if status_code in (429, 500, 503):
                is_retryable = True
            elif any(code in err_str for code in ["429", "500", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE"]):
                is_retryable = True

            if is_retryable and attempt < max_retries - 1:
                print(f"[WARN] Transient API error ({e}). Retrying in {delay:.1f}s (attempt {attempt+1}/{max_retries})...")
                time.sleep(delay)
                delay *= 2
            else:
                raise


def load_image_from_path(path):
    """Loads a local image file and returns an image content dict with base64 data for the Interactions API."""
    if not path:
        return None
    try:
        mime_type, _ = mimetypes.guess_type(path)
        if not mime_type:
            mime_type = "image/png"
            print(f"[WARN] Could not detect MIME type for {path}. Defaulting to {mime_type}.")

        with open(path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")

        return {"type": "image", "data": b64_data, "mime_type": mime_type}
    except Exception as e:
        print(f"[ERROR] Failed to load image {path}: {e}")
        return None


def prepare_video_input(client, path):
    """Prepares a video file for extension (base64 inline or Files API upload)."""
    if not path:
        return None
    try:
        if not os.path.exists(path):
            print(f"[ERROR] Video file does not exist: {path}")
            return None

        size = os.path.getsize(path)
        mime_type, _ = mimetypes.guess_type(path) or ("video/mp4", None)

        if size > 20 * 1024 * 1024:
            print(f"[INFO] Uploading video for extension via Files API: {path}")
            video_file = client.files.upload(file=path)
            while video_file.state.name == "PROCESSING":
                print("Processing video upload...")
                time.sleep(2)
                video_file = client.files.get(name=video_file.name)

            if video_file.state.name != "ACTIVE":
                print(f"[ERROR] Video upload failed state: {video_file.state.name}")
                return None
            return {"type": "video", "uri": video_file.uri}
        else:
            with open(path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("utf-8")
            return {"type": "video", "data": b64_data, "mime_type": mime_type or "video/mp4"}
    except Exception as e:
        print(f"[ERROR] Failed to prepare video {path}: {e}")
        return None


def generate_output_filename(prompt):
    """Generates an output filename slug from the prompt."""
    sanitized = re.sub(r'[^a-zA-Z0-9_]+', '_', prompt or "video")[:50].strip('_')
    base = f"{sanitized or 'video'}.mp4"
    if not os.path.exists(base):
        return base
    counter = 1
    root, ext = os.path.splitext(base)
    while os.path.exists(f"{root}_{counter}{ext}"):
        counter += 1
    return f"{root}_{counter}{ext}"


def generate_video(args):
    """Generates a video using the Gemini Omni Flash model via the Interactions API."""
    client = get_client()

    # Input validations
    if getattr(args, "last_frame", None) and not getattr(args, "image", None):
        print("[ERROR] --last-frame requires --image to be specified.")
        return None

    if getattr(args, "ref_images", None) and len(args.ref_images) > 3:
        print("[ERROR] Maximum of 3 reference images allowed.")
        return None

    # Prepare Inputs
    image_input = load_image_from_path(args.image) if getattr(args, "image", None) else None
    last_frame_input = load_image_from_path(args.last_frame) if getattr(args, "last_frame", None) else None

    ref_images = []
    if getattr(args, "ref_images", None):
        for p in args.ref_images:
            img = load_image_from_path(p)
            if img:
                ref_images.append(img)

    video_input = prepare_video_input(client, args.video) if getattr(args, "video", None) else None

    # Build input items list for Interactions API
    input_items = []
    if image_input:
        input_items.append(image_input)
    if last_frame_input:
        input_items.append(last_frame_input)
    if ref_images:
        input_items.extend(ref_images)
    if video_input:
        input_items.append(video_input)

    prompt_text = (args.prompt or "").strip()
    if getattr(args, "negative_prompt", None):
        prompt_text = f"{prompt_text}\nAvoid: {args.negative_prompt}".strip()

    if prompt_text:
        input_items.append({"type": "text", "text": prompt_text})

    if not input_items:
        print("[ERROR] No input prompt or media provided.")
        return None

    # Determine tier resolution
    model_tier = getattr(args, "model", None) or "standard"
    resolution = TIER_RESOLUTIONS.get(model_tier, "720p")

    response_format = {
        "type": "video",
        "aspect_ratio": getattr(args, "aspect_ratio", "16:9"),
        "duration": f"{getattr(args, 'duration', 8)}s",
        "resolution": resolution,
    }

    generation_config = {}
    if getattr(args, "seed", None) is not None:
        generation_config["seed"] = args.seed

    if video_input:
        generation_config["video_config"] = {"task": "extend"}
    elif image_input and last_frame_input:
        generation_config["video_config"] = {"task": "image_to_video"}
    elif image_input:
        generation_config["video_config"] = {"task": "image_to_video"}
    elif ref_images:
        generation_config["video_config"] = {"task": "reference_to_video"}

    print(f"[INFO] Sending request to {MODEL_ID} (tier: {model_tier}, resolution: {resolution})...")
    print(f"  Prompt: {args.prompt}")
    if image_input:
        print("  Input: Image")
    if last_frame_input:
        print("  Input: Last Frame")
    if ref_images:
        print(f"  Input: {len(ref_images)} Reference Images")
    if video_input:
        print("  Input: Video (Extension)")

    try:
        interaction = call_with_retry(
            client.interactions.create,
            model=MODEL_ID,
            input=input_items if len(input_items) > 1 or not prompt_text else prompt_text,
            response_format=response_format,
            generation_config=generation_config if generation_config else None,
            background=True,
        )
    except Exception as e:
        print(f"[ERROR] API Request Failed: {e}")
        return None

    if not interaction:
        print("[ERROR] Failed to start interaction.")
        return None

    print(f"[INFO] Interaction started: {interaction.id} (status: {interaction.status})")

    # Polling Loop with Timeout
    start_time = time.time()
    while interaction and interaction.status == "in_progress":
        elapsed = time.time() - start_time
        if elapsed > POLLING_TIMEOUT_SEC:
            print(f"\n[ERROR] Operation timed out after {POLLING_TIMEOUT_SEC} seconds.")
            return None

        if elapsed < 30:
            sleep_time = 5
        elif elapsed < 60:
            sleep_time = 10
        else:
            sleep_time = 15

        print(f"  Generating... ({int(elapsed)}s elapsed, checking in {sleep_time}s)")
        time.sleep(sleep_time)

        try:
            interaction = call_with_retry(client.interactions.get, id=interaction.id)
        except Exception as e:
            print(f"  [WARN] Status check failed (retrying): {e}")

    if interaction and interaction.status == "completed":
        print("[INFO] Generation Success!")
        temp_filename = None
        try:
            output_video = getattr(interaction, "output_video", None)
            if not output_video and getattr(interaction, "outputs", None):
                for out in interaction.outputs:
                    if getattr(out, "type", None) == "video" or hasattr(out, "data"):
                        output_video = out
                        break

            if not output_video:
                print("[ERROR] Completed interaction contains no video output.")
                return None

            print("[INFO] Downloading video...")
            if getattr(output_video, "data", None):
                content = base64.b64decode(output_video.data)
            elif getattr(output_video, "uri", None):
                content = client.files.download(file=output_video.uri)
            else:
                print("[ERROR] Output video object has neither inline data nor URI.")
                return None

            # Determine filename
            if getattr(args, "output_file", None):
                filename = args.output_file
            else:
                filename = generate_output_filename(args.prompt)

            # Atomic Write
            temp_filename = filename + ".part"
            with open(temp_filename, "wb") as f:
                f.write(content)

            os.rename(temp_filename, filename)
            print(f"[INFO] Saved to: {filename}")

            return {
                "prompt": args.prompt,
                "output_file": filename,
                "duration": args.duration,
                "aspect_ratio": args.aspect_ratio,
            }
        except Exception as e:
            print(f"[ERROR] Failed to save video: {e}")
            if temp_filename and os.path.exists(temp_filename):
                os.remove(temp_filename)
            return None
    else:
        status_msg = interaction.status if interaction else "unknown"
        print(f"[ERROR] Operation ended with status: {status_msg}")
        if interaction and getattr(interaction, "error", None):
            print(f"Error details: {interaction.error}")
        return None


def main():
    epilog = """
Examples:
---------
1. Text-to-Video:
   %(prog)s "A cinematic drone shot of a futuristic city at night, neon lights, rain."
   %(prog)s "A cute robot gardening in a sunlit greenhouse." --duration 4

2. Image-to-Video (Animation):
   %(prog)s "Make the waves move and the clouds drift." --image ./ocean.png
   %(prog)s "The character turns their head and smiles." --image ./portrait.jpg

3. Style Transfer (Reference Images):
   %(prog)s "A fashion model walking on a runway." --ref-images ./style_dress.png ./style_glasses.png
   %(prog)s "A cyberpunk street scene." --ref-images ./blade_runner_ref.jpg

4. Morphing (First & Last Frame):
   %(prog)s "Morph this sketch into a photorealistic drawing." --image ./sketch.png --last-frame ./final.png
   %(prog)s "A car transforming into a robot." --image ./car.png --last-frame ./robot.png

5. Video Extension:
   %(prog)s "The drone continues flying over the mountains." --video ./previous_clip.mp4
   %(prog)s "The character walks out of the frame." --video ./generated_clip.mp4
    """

    parser = argparse.ArgumentParser(
        description="Generate a video using Google's Gemini Omni Flash model (Interactions API).",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("prompt", type=str, nargs='?', default=None, help="The text prompt for the video.")

    # Outputs & Config
    parser.add_argument("--output-file", "-o", type=str, default=None, help="Output filename.")
    parser.add_argument("--duration", type=int, choices=[4, 6, 8], default=8, help="Duration (4, 6, 8). Default 8.")
    parser.add_argument("--aspect-ratio", type=str, choices=["16:9", "9:16"], default="16:9", help="Aspect ratio.")
    parser.add_argument("--negative-prompt", type=str, help="Negative prompt guidance.")

    # Inputs
    parser.add_argument("--image", type=str, help="Initial image path for Image-to-Video.")
    parser.add_argument("--last-frame", type=str, help="Last frame image path (requires --image).")
    parser.add_argument("--ref-images", type=str, nargs='+', help="Path(s) to reference images (max 3).")
    parser.add_argument("--video", type=str, help="Path to input video for extension.")

    # Audio
    parser.add_argument("--no-audio", action="store_true", help="Ignored (Gemini Omni Flash generates native audio).")

    # Advanced
    parser.add_argument("--seed", type=int, help="Seed for random number generation (optional).")
    parser.add_argument("--model", choices=sorted(MODELS), default=None,
                        help="Quality tier: standard (1080p), fast (720p), or lite (720p). Default standard.")

    # History
    parser.add_argument("--history", action="store_true", help="Display prompt history.")
    parser.add_argument("--rerun", type=int, default=None, help="Rerun a prompt from history by number.")

    args = parser.parse_args()

    global MODEL_ID
    if args.model:
        MODEL_ID = MODELS[args.model]

    # Load History
    history = load_history()
    if args.history:
        display_history(history)
        return

    # Handle Rerun
    if args.rerun is not None:
        if not history or args.rerun < 1 or args.rerun > len(history):
            print("Invalid history number.")
            return
        entry = history[args.rerun - 1]
        print(f"[INFO] Rerunning: {entry['prompt']}")
        args.prompt = entry["prompt"]

    # Check for piped input if prompt is missing
    if not args.prompt and not sys.stdin.isatty():
        try:
            piped_input = sys.stdin.read().strip()
            if piped_input:
                args.prompt = piped_input
                print(f"[INFO] Using piped input as prompt: \"{args.prompt[:50]}...\"")
        except Exception as e:
            print(f"[WARN] Failed to read from stdin: {e}")

    if not args.prompt and not args.video:
        parser.error("Prompt is required (provide as argument or via pipe).")

    # Validate inputs
    if args.last_frame and not args.image:
        parser.error("--last-frame requires --image to be specified.")

    if args.ref_images and len(args.ref_images) > 3:
        parser.error("Maximum of 3 reference images allowed.")

    # Execute with Robust Error Handling
    try:
        result = generate_video(args)
        if result:
            history.append(result)
            save_history(history)
    except KeyboardInterrupt:
        print("\n\n[WARN] Generation cancelled by user (Ctrl+C). Exiting...")
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception as e:
        print(f"\n[CRITICAL ERROR] An unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
