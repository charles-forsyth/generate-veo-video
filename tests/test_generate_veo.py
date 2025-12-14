import pytest
from unittest.mock import MagicMock, patch, mock_open
import argparse
from generate_veo3_video import generate_video, load_image_from_path
from google.genai import types

# Mock constants from the script
MODULE_PATH = 'generate_veo3_video'

@pytest.fixture
def mock_client():
    with patch(f'{MODULE_PATH}.get_client') as mock:
        client = MagicMock()
        mock.return_value = client
        yield client

@pytest.fixture
def mock_args():
    args = argparse.Namespace()
    args.prompt = "Test prompt"
    args.output_file = "test_output.mp4"
    args.duration = 8
    args.resolution = "720p" # Note: script currently ignores this but arg parser might have it
    args.aspect_ratio = "16:9"
    args.no_enhance = False
    args.negative_prompt = None
    args.image = None
    args.last_frame = None
    args.ref_images = None
    args.video = None
    args.no_audio = False
    args.seed = None
    return args

def test_load_image_from_path_success():
    with patch("builtins.open", mock_open(read_data=b"fake_image_data")):
        with patch("mimetypes.guess_type", return_value=("image/png", None)):
            result = load_image_from_path("test.png")
            assert isinstance(result, types.Image)
            assert result.mime_type == "image/png"
            assert result.image_bytes == b"fake_image_data"

def test_load_image_from_path_failure():
    with patch("builtins.open", side_effect=FileNotFoundError):
        result = load_image_from_path("nonexistent.png")
        assert result is None

def test_generate_video_config_construction(mock_client, mock_args):
    # Setup mock operation
    mock_op = MagicMock()
    mock_op.name = "test_operation"
    mock_op.done = True
    mock_op.result.generated_videos = [MagicMock()]
    mock_client.models.generate_videos.return_value = mock_op
    mock_client.operations.get.return_value = mock_op

    # Run generation
    generate_video(mock_args)

    # Verify API call
    mock_client.models.generate_videos.assert_called_once()
    call_kwargs = mock_client.models.generate_videos.call_args.kwargs
    
    assert call_kwargs['model'] == "veo-3.1-generate-preview"
    assert call_kwargs['prompt'] == "Test prompt"
    
    config = call_kwargs['config']
    assert isinstance(config, types.GenerateVideosConfig)
    assert config.duration_seconds == 8
    assert config.aspect_ratio == "16:9"
    assert config.person_generation == "allow_all" # Default for text-only

def test_generate_video_with_image(mock_client, mock_args):
    mock_args.image = "start.png"
    
    # Mock image loading
    mock_img = types.Image(image_bytes=b"data", mime_type="image/png")
    
    with patch(f'{MODULE_PATH}.load_image_from_path', return_value=mock_img):
        # Setup operation
        mock_op = MagicMock()
        mock_op.done = True
        mock_op.result.generated_videos = [MagicMock()]
        mock_client.models.generate_videos.return_value = mock_op
        
        generate_video(mock_args)
        
        call_kwargs = mock_client.models.generate_videos.call_args.kwargs
        assert call_kwargs['image'] == mock_img
        # Person generation should switch to allow_adult for image inputs
        assert call_kwargs['config'].person_generation == "allow_adult"

def test_generate_video_polling_loop(mock_client, mock_args):
    # Simulate polling: Not done -> Not done -> Done
    op_running = MagicMock()
    op_running.done = False
    
    op_done = MagicMock()
    op_done.done = True
    op_done.result.generated_videos = [MagicMock()]
    
    mock_client.models.generate_videos.return_value = op_running
    # operations.get called until done
    mock_client.operations.get.side_effect = [op_running, op_done]
    
    with patch("time.sleep") as mock_sleep: # Speed up test
        generate_video(mock_args)
        
        assert mock_client.operations.get.call_count == 2
        assert mock_sleep.call_count == 2

def test_generate_video_save(mock_client, mock_args):
    # Mock successful generation
    mock_video_bytes = b"fake_video_content"
    mock_generated_video = MagicMock()
    mock_generated_video.video = "gs://video/uri" # Mimic URI or object
    
    mock_op = MagicMock()
    mock_op.done = True
    mock_op.result.generated_videos = [mock_generated_video]
    
    mock_client.models.generate_videos.return_value = mock_op
    mock_client.operations.get.return_value = mock_op
    
    # Mock download
    mock_client.files.download.return_value = mock_video_bytes
    
    with patch("builtins.open", mock_open()) as mock_file, \
         patch(f'{MODULE_PATH}.os.rename') as mock_rename:
        generate_video(mock_args)
        
        # Verify download call
        mock_client.files.download.assert_called_with(file="gs://video/uri")
        
        # Verify file write
        mock_file.assert_called_with("test_output.mp4.part", "wb")
        mock_file().write.assert_called_with(mock_video_bytes)
        
        # Verify os.rename call
        mock_rename.assert_called_with("test_output.mp4.part", "test_output.mp4")
