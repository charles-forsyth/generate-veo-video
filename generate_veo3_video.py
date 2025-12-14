#!/usr/bin/env python3
import time
import os
import argparse
import re
import json
import mimetypes
import sys
from dotenv import load_dotenv
from google import genai
from google.genai import types

# --- ENV & CONFIG SETUP ---
# Load .env from various locations
load_dotenv() # Current dir
xdg_config_home = os.getenv("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
user_config_path = os.path.join(xdg_config_home, "deepresearch", ".env")
load_dotenv(user_config_path) # DeepResearch config
load_dotenv(os.path.join(os.path.expanduser("~"), ".env")) # Home dir .env

# Configuration with Env Fallbacks
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "ucr-research-computing")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_ID = "veo-3.1-generate-preview"
HISTORY_FILE = ".veo_history.json"
POLLING_TIMEOUT_SEC = 900 # 15 minutes max wait time

def load_history():
    """Loads the prompt history from the history file."""
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r") as f:
        return json.load(f)

def save_history(history):
    """Saves the prompt history to the history file."""
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)

def display_history(history):
    """Displays the prompt history."""
    if not history:
        print("No history found.")
        return
    for i, entry in enumerate(history):
        print(f"{i+1}: {entry['prompt']}")

def get_client():
    """Creates the GenAI client with appropriate authentication."""
    if API_KEY:
        print("[INFO] Using API Key authentication.")
        return genai.Client(api_key=API_KEY)
    else:
        print(f"[INFO] Using Vertex AI (ADC) authentication for project {PROJECT_ID}")
        return genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

def load_image_from_path(path):
    """Loads a local image file and returns a types.Image object with MIME type."""
    if not path:
        return None
    try:
        mime_type, _ = mimetypes.guess_type(path)
        if not mime_type:
            mime_type = "image/png" 
            print(f"[WARN] Could not detect MIME type for {path}. Defaulting to {mime_type}.")

        with open(path, "rb") as f:
            image_bytes = f.read()
            
        # Use image_bytes and explicit mime_type
        return types.Image(image_bytes=image_bytes, mime_type=mime_type)

    except Exception as e:
        print(f"[ERROR] Failed to load image {path}: {e}")
        return None

def upload_video_for_extension(client, path):
    """
    Uploads a video file for extension. 
    Note: Veo only supports extending Veo-generated videos.
    """
    if not path:
        return None
    try:
        print(f"[INFO] Uploading video for extension: {path}")
        # We need to use the Files API to upload
        video_file = client.files.upload(file=path)
        
        # Wait for processing? Usually video uploads need processing.
        while video_file.state.name == "PROCESSING":
             print("Processing video upload...")
             time.sleep(2)
             video_file = client.files.get(name=video_file.name)
             
        if video_file.state.name != "ACTIVE":
            print(f"[ERROR] Video upload failed state: {video_file.state.name}")
            return None
            
        return video_file
    except Exception as e:
        print(f"[ERROR] Failed to upload video {path}: {e}")
        return None

def generate_video(args):
    """Generates a video using the Vertex AI VEO model."""
    client = get_client()

    # Prepare Inputs
    image_input = load_image_from_path(args.image)
    last_frame_input = load_image_from_path(args.last_frame)
    
    # Reference Images
    ref_images = []
    if args.ref_images:
        for p in args.ref_images:
            img = load_image_from_path(p)
            if img:
                ref_images.append(types.VideoGenerationReferenceImage(
                    image=img,
                    reference_type="asset" # "asset" preserves subject appearance
                ))

    # Video Extension Input
    video_input = None
    if args.video:
        print("[WARN] Video extension via CLI implies uploading a local file. Only Veo-generated videos are supported.")
        f_obj = upload_video_for_extension(client, args.video)
        if f_obj:
            video_input = f_obj 

    # Configure the video generation
    person_gen = "allow_all" if not (image_input or last_frame_input or ref_images) else "allow_adult"
    
    config = types.GenerateVideosConfig(
        aspect_ratio=args.aspect_ratio,
        number_of_videos=1,
        duration_seconds=args.duration,
        person_generation=person_gen,
        negative_prompt=args.negative_prompt,
    )

    if args.seed:
        config.seed = args.seed

    if last_frame_input:
        config.last_frame = last_frame_input
    
    if ref_images:
        config.reference_images = ref_images

    print(f"[INFO] Sending request to {MODEL_ID}...")
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
        operation = client.models.generate_videos(
            model=MODEL_ID,
            prompt=args.prompt,
            config=config,
            image=image_input,
            video=video_input
        )
    except Exception as e:
        print(f"[ERROR] API Request Failed: {e}")
        return None

    print(f"[INFO] Operation started: {operation.name}")

    # Polling Loop with Timeout
    start_time = time.time()
    
    while not operation.done:
        elapsed = time.time() - start_time
        if elapsed > POLLING_TIMEOUT_SEC:
            print(f"\n[ERROR] Operation timed out after {POLLING_TIMEOUT_SEC} seconds.")
            return None

        # Smart polling interval
        if elapsed < 60:
            sleep_time = 10
        elif elapsed < 120:
            sleep_time = 15
        else:
            sleep_time = 30
            
        print(f"  Generating... ({int(elapsed)}s elapsed, checking in {sleep_time}s)")
        time.sleep(sleep_time)
        
        try:
            operation = client.operations.get(operation)
        except Exception as e:
            print(f"  [WARN] Status check failed (retrying): {e}")

    if operation.result:
        print("[INFO] Generation Success!")
        # Save the video
        try:
            generated_video = operation.result.generated_videos[0]
            
            # Determine filename
            if args.output_file:
                filename = args.output_file
            else:
                sanitized_prompt = re.sub(r'[^a-zA-Z0-9_]+', '_', args.prompt or "video")[:50]
                filename = f"{sanitized_prompt}.mp4"
            
            print("[INFO] Downloading video...")
            
            try:
                file_ref = generated_video.video.name if hasattr(generated_video.video, 'name') else generated_video.video
                content = client.files.download(file=file_ref)
            except AttributeError:
                content = client.files.download(file=generated_video.video)

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
                "aspect_ratio": args.aspect_ratio
            }
            
        except Exception as e:
            print(f"[ERROR] Failed to save video: {e}")
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
            return None
    else:
        print("[ERROR] Operation failed.")
        if operation.error:
            print(f"Error details: {operation.error}")
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
   %(prog)s "The drone continues flying over the mountains." --video ./previous_veo_clip.mp4
   %(prog)s "The character walks out of the frame." --video ./generated_clip.mp4
    """

    parser = argparse.ArgumentParser(
        description="Generate a video using the Vertex AI VEO 3.1 model.",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("prompt", type=str, nargs='?', default=None, help="The text prompt for the video.")
    
    # Outputs & Config
    parser.add_argument("--output-file", "-o", type=str, default=None, help="Output filename.")
    parser.add_argument("--duration", type=int, choices=[4, 6, 8], default=8, help="Duration (4, 6, 8). Default 8.")
    parser.add_argument("--aspect-ratio", type=str, choices=["16:9", "9:16"], default="16:9", help="Aspect ratio.")
    parser.add_argument("--negative-prompt", type=str, help="Negative prompt.")

    # Inputs
    parser.add_argument("--image", type=str, help="Initial image path for Image-to-Video.")
    parser.add_argument("--last-frame", type=str, help="Last frame image path (requires --image).")
    parser.add_argument("--ref-images", type=str, nargs='+', help="Path(s) to reference images (max 3).")
    parser.add_argument("--video", type=str, help="Path to input video for extension (must be Veo-generated).")
    
    # Audio
    parser.add_argument("--no-audio", action="store_true", help="Ignored (Veo 3.1 always generates audio).")

    # Advanced
    parser.add_argument("--seed", type=int, help="Seed for random number generation (optional).")

    # History
    parser.add_argument("--history", action="store_true", help="Display prompt history.")
    parser.add_argument("--rerun", type=int, default=None, help="Rerun a prompt from history by number.")

    args = parser.parse_args()

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

    # Execute with Robust Error Handling
    try:
        result = generate_video(args)
        if result:
            history.append(result)
            save_history(history)
    except KeyboardInterrupt:
        print("\n\n[WARN] Generation cancelled by user (Ctrl+C). Exiting...")
        sys.exit(130) # Standard exit code for SIGINT
    except Exception as e:
        print(f"\n[CRITICAL ERROR] An unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
