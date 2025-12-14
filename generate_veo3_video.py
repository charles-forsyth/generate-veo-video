#!/usr/bin/env python3
import time
import os
import argparse
import re
import json
import base64
from pathlib import Path
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
        print(f"[INFO] Using API Key authentication.")
        return genai.Client(api_key=API_KEY)
    else:
        print(f"[INFO] Using Vertex AI (ADC) authentication for project {PROJECT_ID}")
        return genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

import mimetypes

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
        # For CLI, we likely need to upload the file first if it's a path
        # However, the SDK might expect a types.Video object from a previous response.
        # Let's try to upload it and use the file object.
        # Note: The Python SDK for `generate_videos` `video` param expects `types.Video` or compatible.
        # A File API object might work if wrapped. 
        # But per docs: "The video should come from a previous generation, like operation.response.generated_videos[0].video"
        # We'll try uploading.
        print("[WARN] Video extension via CLI implies uploading a local file. Only Veo-generated videos are supported.")
        f_obj = upload_video_for_extension(client, args.video)
        if f_obj:
            # We need to pass the file content/URI. 
            # The client.models.generate_videos `video` param usually takes the file URI or object.
            # We will pass the file object directly if SDK supports it, or try to wrap it.
            video_input = f_obj 

    # Configure the video generation
    # Note: person_generation="allow_adult" is required for Image-to-Video/Interpolation/Ref Images in some regions
    person_gen = "allow_all" if not (image_input or last_frame_input or ref_images) else "allow_adult"
    
    config = types.GenerateVideosConfig(
        aspect_ratio=args.aspect_ratio,
        number_of_videos=1,
        duration_seconds=args.duration,
        person_generation=person_gen,
        # enhance_prompt=not args.no_enhance, # Not supported in Veo 3.1
        # generate_audio=not args.no_audio, # Removed as Veo 3.1 is native audio always on
        negative_prompt=args.negative_prompt,
    )

    # Add specific config fields
    if last_frame_input:
        config.last_frame = last_frame_input
    
    if ref_images:
        config.reference_images = ref_images

    # Note: 'resolution' parameter is documented but currently returns "not supported in Gemini API" error.
    # We will rely on the model's default (720p).
    # if args.resolution:
    #      config.resolution = args.resolution

    print(f"[INFO] Sending request to {MODEL_ID}...")
    print(f"  Prompt: {args.prompt}")
    if image_input: print("  Input: Image")
    if last_frame_input: print("  Input: Last Frame")
    if ref_images: print(f"  Input: {len(ref_images)} Reference Images")
    if video_input: print("  Input: Video (Extension)")

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
        return

    print(f"[INFO] Operation started: {operation.name}")

    # Poll the operation status
    while not operation.done:
        print("  Generating... (checking in 10s)")
        time.sleep(10)
        try:
            operation = client.operations.get(operation)
        except Exception as e:
            print(f"  [WARN] Status check failed: {e}")

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
            
            print(f"[INFO] Downloading video...")
            # Use client.files.download() to get bytes directly.
            # Docs: client.files.download(file=generated_video.video) returns the bytes content.
            
            try:
                # Try passing the name if it's an object
                file_ref = generated_video.video.name if hasattr(generated_video.video, 'name') else generated_video.video
                content = client.files.download(file=file_ref)
            except AttributeError:
                # If it's a string or dict?
                content = client.files.download(file=generated_video.video)

            with open(filename, "wb") as f:
                f.write(content)

            print(f"[INFO] Saved to: {filename}")
            
            # History
            return {
                "prompt": args.prompt,
                "output_file": filename,
                "duration": args.duration,
                "aspect_ratio": args.aspect_ratio
            }
            
        except Exception as e:
            print(f"[ERROR] Failed to save video: {e}")
    else:
        print("[ERROR] Operation failed.")
        if operation.error:
            print(f"Error details: {operation.error}")

def main():
    parser = argparse.ArgumentParser(description="Generate a video using the Vertex AI VEO 3.1 model.")
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
        # We don't restore all flags for simplicity unless stored. 
        # Ideally we should, but for now we take the prompt.

    if not args.prompt and not args.video: # Prompt is optional for Extension? No, usually required.
        parser.error("Prompt is required.")

    # Execute
    result = generate_video(args)
    
    if result:
        history.append(result)
        save_history(history)

if __name__ == "__main__":
    main()