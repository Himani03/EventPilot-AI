from io import BytesIO
import base64

from PIL import Image

from src import visuals


def test_event_graphic_uses_uploaded_photo_as_square_background(tmp_path, monkeypatch):
    monkeypatch.setattr(visuals, "OUTPUT_DIR", tmp_path)
    source = Image.new("RGB", (1600, 900), (40, 150, 210))
    image_bytes = BytesIO()
    source.save(image_bytes, format="JPEG")

    output_path = visuals.create_event_graphic(
        "Outdoor Movie Night", "Friday at 7 PM", "Campus Lawn", photo_bytes=image_bytes.getvalue()
    )

    with Image.open(output_path) as output:
        assert output.size == (1080, 1080)
        # The photo remains visible beneath the dark text overlay.
        background_pixel = output.getpixel((800, 600))
        assert background_pixel[2] > background_pixel[0]


def test_event_graphic_without_photo_keeps_local_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(visuals, "OUTPUT_DIR", tmp_path)

    output_path = visuals.create_event_graphic("Jazz Night", "Friday at 7 PM")

    assert output_path.exists()
    with Image.open(output_path) as output:
        assert output.size == (1080, 1080)


def test_ai_background_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    try:
        visuals.generate_ai_background("Jazz Night", "Friday")
    except RuntimeError as error:
        assert "OPENAI_API_KEY" in str(error)
    else:
        raise AssertionError("Missing API key should be reported clearly.")


def test_ai_background_decodes_generated_image(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    expected = b"fake-png-data"

    class Response:
        ok = True

        @staticmethod
        def json():
            return {"data": [{"b64_json": base64.b64encode(expected).decode("ascii")}]} 

    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(visuals.requests, "post", fake_post)

    result = visuals.generate_ai_background("Jazz Night", "Friday", "Theater", "Live music")

    assert result == expected
    assert captured["json"]["model"] == "gpt-image-2.5-flare"
    assert "readable text" in captured["json"]["prompt"]


def test_ai_background_reports_provider_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class Response:
        ok = False
        status_code = 403

        @staticmethod
        def json():
            return {"error": {"message": "Image API access is unavailable."}}

    monkeypatch.setattr(visuals.requests, "post", lambda *args, **kwargs: Response())

    try:
        visuals.generate_ai_background("Jazz Night", "Friday")
    except RuntimeError as error:
        assert "access is unavailable" in str(error)
    else:
        raise AssertionError("Provider errors should be shown to the user.")
