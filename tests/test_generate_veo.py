import pytest
import base64
from unittest.mock import MagicMock, patch, mock_open
import argparse
from generate_veo3_video import generate_video, load_image_from_path, call_with_retry

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
    args.aspect_ratio = "16:9"
    args.negative_prompt = None
    args.image = None
    args.last_frame = None
    args.ref_images = None
    args.video = None
    args.no_audio = False
    args.seed = None
    args.model = "standard"
    return args


def test_load_image_from_path_success():
    fake_data = b"fake_image_data"
    expected_b64 = base64.b64encode(fake_data).decode("utf-8")
    with patch("builtins.open", mock_open(read_data=fake_data)):
        with patch("mimetypes.guess_type", return_value=("image/png", None)):
            result = load_image_from_path("test.png")
            assert isinstance(result, dict)
            assert result["type"] == "image"
            assert result["mime_type"] == "image/png"
            assert result["data"] == expected_b64


def test_load_image_from_path_failure():
    with patch("builtins.open", side_effect=FileNotFoundError):
        result = load_image_from_path("nonexistent.png")
        assert result is None


def test_generate_video_config_construction(mock_client, mock_args):
    # Setup mock interaction
    mock_interaction = MagicMock()
    mock_interaction.id = "test_interaction"
    mock_interaction.status = "completed"
    mock_video_obj = MagicMock()
    mock_video_obj.data = base64.b64encode(b"video_bytes").decode("utf-8")
    mock_video_obj.uri = None
    mock_interaction.output_video = mock_video_obj

    mock_client.interactions.create.return_value = mock_interaction
    mock_client.interactions.get.return_value = mock_interaction

    with patch("builtins.open", mock_open()), patch(f'{MODULE_PATH}.os.rename'):
        result = generate_video(mock_args)

    assert result is not None
    mock_client.interactions.create.assert_called_once()
    call_kwargs = mock_client.interactions.create.call_args.kwargs

    assert call_kwargs['model'] == "gemini-omni-1.1-flash"
    assert call_kwargs['background'] is True
    assert call_kwargs['input'] == "Test prompt"

    resp_fmt = call_kwargs['response_format']
    assert resp_fmt['type'] == "video"
    assert resp_fmt['duration'] == "8s"
    assert resp_fmt['aspect_ratio'] == "16:9"
    assert resp_fmt['resolution'] == "1080p"


def test_generate_video_with_image(mock_client, mock_args):
    mock_args.image = "start.png"
    mock_args.model = "fast"

    mock_img = {"type": "image", "data": "fake_b64", "mime_type": "image/png"}

    with patch(f'{MODULE_PATH}.load_image_from_path', return_value=mock_img):
        mock_interaction = MagicMock()
        mock_interaction.id = "test_interaction"
        mock_interaction.status = "completed"
        mock_video_obj = MagicMock()
        mock_video_obj.data = base64.b64encode(b"video_bytes").decode("utf-8")
        mock_video_obj.uri = None
        mock_interaction.output_video = mock_video_obj

        mock_client.interactions.create.return_value = mock_interaction
        mock_client.interactions.get.return_value = mock_interaction

        with patch("builtins.open", mock_open()), patch(f'{MODULE_PATH}.os.rename'):
            generate_video(mock_args)

        call_kwargs = mock_client.interactions.create.call_args.kwargs
        input_items = call_kwargs['input']
        assert isinstance(input_items, list)
        assert mock_img in input_items
        assert {"type": "text", "text": "Test prompt"} in input_items

        assert call_kwargs['response_format']['resolution'] == "720p"
        assert call_kwargs['generation_config']['video_config']['task'] == "image_to_video"


def test_generate_video_first_and_last_frame(mock_client, mock_args):
    mock_args.image = "start.png"
    mock_args.last_frame = "end.png"

    img_start = {"type": "image", "data": "start_b64", "mime_type": "image/png"}
    img_end = {"type": "image", "data": "end_b64", "mime_type": "image/png"}

    def fake_load_image(path):
        if path == "start.png":
            return img_start
        if path == "end.png":
            return img_end
        return None

    with patch(f'{MODULE_PATH}.load_image_from_path', side_effect=fake_load_image):
        mock_interaction = MagicMock()
        mock_interaction.id = "test_interaction"
        mock_interaction.status = "completed"
        mock_video_obj = MagicMock()
        mock_video_obj.data = base64.b64encode(b"video_bytes").decode("utf-8")
        mock_interaction.output_video = mock_video_obj

        mock_client.interactions.create.return_value = mock_interaction

        with patch("builtins.open", mock_open()), patch(f'{MODULE_PATH}.os.rename'):
            generate_video(mock_args)

        call_kwargs = mock_client.interactions.create.call_args.kwargs
        input_items = call_kwargs['input']
        assert input_items[0] == img_start
        assert input_items[1] == img_end
        assert input_items[2] == {"type": "text", "text": "Test prompt"}
        assert call_kwargs['generation_config']['video_config']['task'] == "image_to_video"


def test_generate_video_polling_loop(mock_client, mock_args):
    # Simulate polling: in_progress -> in_progress -> completed
    interaction_running = MagicMock()
    interaction_running.id = "test_interaction"
    interaction_running.status = "in_progress"

    interaction_done = MagicMock()
    interaction_done.id = "test_interaction"
    interaction_done.status = "completed"
    mock_video_obj = MagicMock()
    mock_video_obj.data = base64.b64encode(b"fake_video").decode("utf-8")
    interaction_done.output_video = mock_video_obj

    mock_client.interactions.create.return_value = interaction_running
    mock_client.interactions.get.side_effect = [interaction_running, interaction_done]

    with patch("time.sleep") as mock_sleep, patch("builtins.open", mock_open()), patch(f'{MODULE_PATH}.os.rename'):
        generate_video(mock_args)

        assert mock_client.interactions.get.call_count == 2
        assert mock_sleep.call_count == 2


def test_generate_video_save(mock_client, mock_args):
    raw_video_bytes = b"fake_video_content"
    b64_content = base64.b64encode(raw_video_bytes).decode("utf-8")

    mock_interaction = MagicMock()
    mock_interaction.id = "test_interaction"
    mock_interaction.status = "completed"
    mock_video = MagicMock()
    mock_video.data = b64_content
    mock_video.uri = None
    mock_interaction.output_video = mock_video

    mock_client.interactions.create.return_value = mock_interaction

    with patch("builtins.open", mock_open()) as mock_file, patch(f'{MODULE_PATH}.os.rename') as mock_rename:
        result = generate_video(mock_args)
        assert result is not None
        assert result["output_file"] == "test_output.mp4"

        # Verify file write
        mock_file.assert_called_with("test_output.mp4.part", "wb")
        mock_file().write.assert_called_with(raw_video_bytes)

        # Verify os.rename call
        mock_rename.assert_called_with("test_output.mp4.part", "test_output.mp4")


def test_call_with_retry_transient_error():
    mock_fn = MagicMock()
    error_503 = Exception("503 Service Unavailable")
    mock_fn.side_effect = [error_503, "success"]

    with patch("time.sleep"):
        res = call_with_retry(mock_fn, max_retries=3, initial_delay=0.1)
        assert res == "success"
        assert mock_fn.call_count == 2
