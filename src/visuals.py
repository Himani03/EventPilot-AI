from pathlib import Path
from io import BytesIO
import base64
import os
import requests
from PIL import Image, ImageDraw, ImageFont
import re
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "generated"

def generate_ai_background(name, event_date, venue="", description=""):
    """Generate a text-free square background using the configured OpenAI API key."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Add OPENAI_API_KEY to your .env file to generate an AI background.")

    prompt = (
        "Create a photorealistic, editorial-quality square background image for an event poster. "
        "Use the following event details only as visual inspiration; do not include letters, words, logos, "
        "signage, or readable text. Keep the center and lower third uncluttered so poster text can be added later. "
        "Choose a natural candid scene, attractive lighting, and a polished social-media campaign look.\n"
        f"Event: {name}\nDate: {event_date}\nVenue: {venue or 'not specified'}\n"
        f"Description: {description}"
    )
    response = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "gpt-image-2.5-flare",
            "prompt": prompt,
            "size": "1024x1024",
            "quality": "low",
            "output_format": "png",
        },
        timeout=180,
    )
    if not response.ok:
        try:
            detail = response.json().get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            detail = ""
        raise RuntimeError(detail or f"Image API request failed ({response.status_code}).")
    try:
        return base64.b64decode(response.json()["data"][0]["b64_json"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("The image API returned an unexpected response.") from exc

def _font(size, bold=False):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()

def create_event_graphic(name, event_date, venue="", description="", photo_bytes=None):
    """Create an event poster, using an uploaded photo when one is provided."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip()).strip("-").lower()[:40] or "event"
    path = OUTPUT_DIR / f"{safe}-{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
    width, height = 1080, 1080
    if photo_bytes:
        photo = Image.open(BytesIO(photo_bytes)).convert("RGB")
        # Fill the square canvas and crop excess edges without stretching the photo.
        scale = max(width / photo.width, height / photo.height)
        photo = photo.resize((int(photo.width * scale), int(photo.height * scale)), Image.Resampling.LANCZOS)
        left = (photo.width - width) // 2
        top = (photo.height - height) // 2
        img = photo.crop((left, top, left + width, top + height)).convert("RGBA")
        shade = Image.new("RGBA", (width, height))
        shade_pixels = shade.load()
        for y in range(height):
            alpha = int(70 + 140 * y / height)
            for x in range(width):
                shade_pixels[x, y] = (8, 13, 30, alpha)
        img = Image.alpha_composite(img, shade).convert("RGB")
    else:
        img = Image.new("RGB", (width, height), "#101426")
        px = img.load()
        # Smooth abstract diagonal gradient, generated locally.
        c1, c2 = (35, 28, 82), (12, 105, 120)
        for y in range(height):
            for x in range(width):
                t = min(1, max(0, (x * 0.55 + y * 0.45) / (width * 0.9)))
                px[x, y] = tuple(int(c1[i] * (1-t) + c2[i] * t) for i in range(3))
    draw = ImageDraw.Draw(img, "RGBA")
    draw.ellipse((690, -170, 1260, 400), fill=(255, 255, 255, 18), outline=(255,255,255,45), width=3)
    draw.ellipse((-200, 700, 400, 1300), fill=(255, 255, 255, 13), outline=(255,255,255,35), width=3)
    draw.rounded_rectangle((70, 70, 1010, 1010), radius=38, outline=(255,255,255,80), width=2)
    draw.text((110, 135), "EVENTPILOT  /  LIVE EVENT", font=_font(25, True), fill="#BDEEF2")
    draw.line((110, 190, 400, 190), fill="#BDEEF2", width=5)

    def wrap(text, font, max_width):
        words, lines, current = (text or "").split(), [], ""
        for word in words:
            candidate = (current + " " + word).strip()
            if draw.textbbox((0,0), candidate, font=font)[2] <= max_width:
                current = candidate
            else:
                if current: lines.append(current)
                current = word
        if current: lines.append(current)
        return lines

    title_font = _font(72, True)
    title_lines = wrap(name.upper(), title_font, 820)[:3]
    y = 285
    for line in title_lines:
        draw.text((110, y), line, font=title_font, fill="#FFFFFF")
        y += 90
    date_font = _font(34, True)
    draw.text((110, y + 28), event_date, font=date_font, fill="#D2F7F4")
    y += 105
    if venue:
        draw.text((110, y), venue[:55], font=_font(27), fill="#E5E7EB")
    draw.rounded_rectangle((110, 835, 465, 910), radius=22, fill="#F3F4F6")
    draw.text((145, 855), "GET TICKETS", font=_font(27, True), fill="#111827")
    draw.text((110, 950), "YOUR NEXT GREAT NIGHT STARTS HERE", font=_font(18, True), fill="#D1D5DB")
    img.save(path, quality=95)
    return path
