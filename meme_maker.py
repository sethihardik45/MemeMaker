from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types
import textwrap
import json
import random
import os
import requests
import base64
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
BOLD_FONT_INDEX = 0

IMGBB_API_KEY = os.environ["IMGBB_API_KEY"]
INSTAGRAM_ACCOUNT_ID = os.environ["INSTAGRAM_ACCOUNT_ID"]
INSTAGRAM_ACCESS_TOKEN = os.environ["INSTAGRAM_ACCESS_TOKEN"]

TITLE_COLORS = {
    "politics": (255, 200, 150),
    "tech": (255, 255, 200),
    "cricket": (173, 216, 230),
    "Bollywood": (255, 182, 182),
    "space": (211, 211, 211),
    "geopolitics": (182, 255, 182),
}

client = genai.Client(api_key=GEMINI_API_KEY)

# Fetch latest news from the internet using Gemini
topic = random.choice(['politics', 'tech', 'cricket', 'Bollywood', 'space', 'geopolitics'])
print(f"Topic: {topic}")

news = None
for news_attempt in range(3):
    try:
        news_response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Give me one latest breaking news from today about {topic}. Pick something unique and fresh, not a commonly repeated story. Return ONLY valid JSON with two keys: \"title\" (a short headline, around 6-10 words) and \"caption\" (a brief summary, around 25-35 words). No emojis. No markdown, no code fences, just raw JSON.",
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        news_text = news_response.text.strip()
        if news_text.startswith("```"):
            news_text = news_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        news = json.loads(news_text)
        break
    except (json.JSONDecodeError, Exception) as e:
        print(f"News fetch attempt {news_attempt + 1} failed: {e}")
        if news_attempt < 2:
            print("Retrying...")

if news is None:
    print("All news fetch attempts failed. Exiting.")
    exit(1)

title = news["title"]
caption = news["caption"]
print(f"Title: {title}")
print(f"Caption: {caption}")


def fit_text(draw, text, font_path, max_font_size, img_width, img_height, padding=40, font_index=0):
    """Dynamically find the best font size and wrap width to fill the area without overflow."""
    for font_size in range(max_font_size, 20, -2):
        font = ImageFont.truetype(font_path, font_size, index=font_index)
        for wrap_width in range(45, 10, -1):
            wrapped = textwrap.fill(text, width=wrap_width)
            bbox = draw.textbbox((0, 0), wrapped, font=font, align="center")
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            if tw <= img_width - padding and th <= img_height - padding:
                return font, wrapped, tw, th
    font = ImageFont.truetype(font_path, 20, index=font_index)
    wrapped = textwrap.fill(text, width=15)
    bbox = draw.textbbox((0, 0), wrapped, font=font, align="center")
    return font, wrapped, bbox[2] - bbox[0], bbox[3] - bbox[1]


# Top padding
img = Image.new("RGB", (1080, 100), color=(0, 0, 0))
img.save("top-padding.png")

# Title
title_img = Image.new("RGB", (1080, 250), color=TITLE_COLORS[topic])
title_draw = ImageDraw.Draw(title_img)
title_font, wrapped_title, tw, th = fit_text(title_draw, title, BOLD_FONT_PATH, 80, 1080, 250, font_index=BOLD_FONT_INDEX)
x = (1080 - tw) / 2
y = (250 - th) / 2
title_draw.text((x, y), wrapped_title, fill="black", font=title_font, align="center")
title_img.save("title.png")

# Photo from Gemini (with safe prompt and retry logic)
photo_img = None
for attempt in range(3):
    safe_prompt_response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"Rewrite the following news headline into a safe, non-violent image generation prompt suitable for an AI image generator. Focus on symbols, landmarks, diplomacy, or scenery. Return ONLY the prompt text, nothing else.\n\nHeadline: {title}",
    )
    safe_prompt = safe_prompt_response.text.strip()
    print(f"Image prompt (attempt {attempt + 1}): {safe_prompt}")

    response = client.models.generate_images(
        model="imagen-4.0-generate-001",
        prompt=safe_prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
        ),
    )
    if response.generated_images:
        response.generated_images[0].image.save("photo_raw.png")
        photo_img = Image.open("photo_raw.png").resize((1080, 600))
        photo_img.save("photo.png")
        break
    print(f"Image generation failed on attempt {attempt + 1}, retrying...")

if photo_img is None:
    print("All attempts failed. Using placeholder image.")
    photo_img = Image.new("RGB", (1080, 600), color=(200, 200, 200))
    photo_img.save("photo.png")

# Caption
caption_img = Image.new("RGB", (1080, 350), color=(255, 255, 255))
caption_draw = ImageDraw.Draw(caption_img)
caption_font, wrapped_caption, cw, ch = fit_text(caption_draw, caption, FONT_PATH, 50, 1080, 350)
cx = (1080 - cw) / 2
cy = (350 - ch) / 2
caption_draw.text((cx, cy), wrapped_caption, fill="black", font=caption_font, align="center")
caption_img.save("caption.png")

# Bottom padding
bottom_img = Image.new("RGB", (1080, 50), color=(0, 0, 0))
bottom_img.save("bottom-padding.png")

# Stitch
final_img = Image.new("RGB", (1080, 100 + 250 + 600 + 350 + 50))
y_offset = 0
for part in [img, title_img, photo_img, caption_img, bottom_img]:
    final_img.paste(part, (0, y_offset))
    y_offset += part.size[1]
final_img.save("final.png")

# Save as JPEG under 8MB
quality = 95
while quality >= 10:
    final_img.save("final.jpeg", "JPEG", quality=quality)
    if os.path.getsize("final.jpeg") <= 8 * 1024 * 1024:
        break
    quality -= 5
print(f"final.jpeg saved (quality={quality}, size={os.path.getsize('final.jpeg') / 1024:.1f} KB)")

# --- Upload to imgbb ---
print("\n--- Uploading to imgbb ---")
image_url = None
try:
    with open("final.jpeg", "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    imgbb_response = requests.post(
        "https://api.imgbb.com/1/upload",
        data={
            "key": IMGBB_API_KEY,
            "image": image_data,
        },
        timeout=60,
    )
    imgbb_response.raise_for_status()
    imgbb_result = imgbb_response.json()
    if imgbb_result.get("success"):
        print(f"imgbb response data keys: {list(imgbb_result['data'].keys())}")
        print(f"imgbb image keys: {list(imgbb_result['data'].get('image', {}).keys())}")
        image_url = imgbb_result["data"].get("display_url") or imgbb_result["data"].get("image", {}).get("url") or imgbb_result["data"]["url"]
        print(f"Image uploaded to imgbb: {image_url}")
    else:
        print(f"imgbb upload failed: {imgbb_result}")
except requests.exceptions.RequestException as e:
    print(f"imgbb upload error: {e}")
except Exception as e:
    print(f"Unexpected error during imgbb upload: {e}")

# --- Post to Instagram ---
print("\n--- Posting to Instagram ---")
if image_url is None:
    print("Skipping Instagram post: no image URL available (imgbb upload failed).")
else:
    try:
        # Step 1: Create media container
        container_response = requests.post(
            f"https://graph.facebook.com/v25.0/{INSTAGRAM_ACCOUNT_ID}/media",
            data={
                "image_url": image_url,
                "caption": caption,
                "access_token": INSTAGRAM_ACCESS_TOKEN,
            },
            timeout=60,
        )
        container_response.raise_for_status()
        container_result = container_response.json()
        creation_id = container_result.get("id")
        if not creation_id:
            print(f"Instagram container creation failed: {container_result}")
        else:
            print(f"Instagram media container created: {creation_id}")

            # Wait for container to finish processing
            print("Waiting for Instagram to process the container...")
            time.sleep(15)

            # Step 2: Publish the container
            publish_response = requests.post(
                f"https://graph.facebook.com/v25.0/{INSTAGRAM_ACCOUNT_ID}/media_publish",
                data={
                    "creation_id": creation_id,
                    "access_token": INSTAGRAM_ACCESS_TOKEN,
                },
                timeout=60,
            )
            publish_response.raise_for_status()
            publish_result = publish_response.json()
            post_id = publish_result.get("id")
            if post_id:
                print(f"Successfully posted to Instagram! Post ID: {post_id}")
            else:
                print(f"Instagram publish response: {publish_result}")
    except requests.exceptions.HTTPError as e:
        print(f"Instagram API error: {e}")
        print(f"Response body: {e.response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Instagram request error: {e}")
    except Exception as e:
        print(f"Unexpected error during Instagram posting: {e}")
