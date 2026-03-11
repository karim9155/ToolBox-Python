import os
import shutil
import tempfile
import subprocess
import json
from typing import List, Dict
import logging
import asyncio
from google.cloud import texttospeech_v1beta1 as texttospeech
from google.api_core.client_options import ClientOptions
from PIL import Image

import pdfplumber
import fitz  # PyMuPDF
# import edge_tts # Removed in favor of Google TTS

logger = logging.getLogger("narrative.service")

# ---------------------------------------------------------------------------
# Resolve ffmpeg / ffprobe paths once at import time.
# On some Windows setups the server process may not have the updated PATH,
# so we fall back to the known winget install location.
# ---------------------------------------------------------------------------
_FFMPEG_PATH = shutil.which("ffmpeg") or os.path.expandvars(
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.EXE"
)
_FFPROBE_PATH = shutil.which("ffprobe") or os.path.expandvars(
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffprobe.EXE"
)
logger.info(f"ffmpeg  resolved to: {_FFMPEG_PATH}")
logger.info(f"ffprobe resolved to: {_FFPROBE_PATH}")

# ---------------------------------------------------------------------------
# Watermark configuration – load pre-rendered PNG logo once at import time
# ---------------------------------------------------------------------------
_WATERMARK_PNG_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "watermark.png")
_WATERMARK_IMG: Image.Image | None = None

try:
    _WATERMARK_IMG = Image.open(_WATERMARK_PNG_PATH).convert("RGBA")
    logger.info(f"Watermark PNG loaded: {_WATERMARK_IMG.size}")
except Exception as _e:
    logger.warning(f"⚠️ Could not load watermark PNG ({_WATERMARK_PNG_PATH}): {_e}")


def _paste_watermark(img: Image.Image) -> Image.Image:
    """
    Pastes the pre-rendered SVG watermark in the **bottom-right** corner.
    The watermark is scaled to ~20 % of the slide width so it stays
    proportional on any resolution.  Modifies *img* in-place.
    """
    if _WATERMARK_IMG is None:
        return img

    # Scale watermark to ~20 % of slide width (min 120 px)
    target_w = max(120, int(img.width * 0.20))
    ratio = target_w / _WATERMARK_IMG.width
    target_h = int(_WATERMARK_IMG.height * ratio)
    wm = _WATERMARK_IMG.resize((target_w, target_h), Image.LANCZOS)

    margin = 20
    x = img.width - target_w - margin
    y = img.height - target_h - margin

    # Composite: handle RGBA properly
    if img.mode != "RGBA":
        img = img.convert("RGBA")
        img.paste(wm, (x, y), wm)
        img = img.convert("RGB")
    else:
        img.paste(wm, (x, y), wm)
    return img


def add_watermark_to_images(image_paths: List[str]) -> None:
    """
    Stamps the SVG watermark on every image file in *image_paths* (in-place).
    Handles static images (PNG/JPG) and animated GIFs.
    """
    logger.info(f"\n🏷️  Adding watermark to {len(image_paths)} image(s)...")
    for img_path in image_paths:
        try:
            img = Image.open(img_path)
            is_animated = getattr(img, "is_animated", False) or (
                hasattr(img, "n_frames") and img.n_frames > 1
            )

            if is_animated:
                # Watermark every frame of the animated GIF
                frames = []
                durations = []
                for frame_idx in range(img.n_frames):
                    img.seek(frame_idx)
                    frame = img.convert("RGBA")
                    frame = _paste_watermark(frame)
                    frames.append(frame)
                    durations.append(img.info.get("duration", 100))
                frames[0].save(
                    img_path,
                    save_all=True,
                    append_images=frames[1:],
                    loop=img.info.get("loop", 0),
                    duration=durations,
                )
                logger.info(f"   ✅ Watermarked animated GIF ({img.n_frames} frames): {img_path}")
            else:
                img = img.convert("RGB")
                img = _paste_watermark(img)
                if img_path.lower().endswith(".png"):
                    img.save(img_path, "PNG")
                else:
                    img.save(img_path, "JPEG")
                logger.info(f"   ✅ Watermarked: {img_path}")
        except Exception as e:
            logger.warning(f"   ⚠️ Could not watermark {img_path}: {e}")


# ---------------------------------------------------------------------------
# Vertex AI TTS Configuration – Chirp 3: HD Voices
# Uses service-account auth (GOOGLE_APPLICATION_CREDENTIALS) and a regional
# EU endpoint so that audio data never leaves the EU.
# ---------------------------------------------------------------------------
VERTEX_PROJECT = os.getenv("GOOGLE_VERTEX_PROJECT")
VERTEX_LOCATION = os.getenv("GOOGLE_VERTEX_LOCATION", "europe-west1")

_TTS_CLIENT: texttospeech.TextToSpeechClient | None = None

def _get_tts_client() -> texttospeech.TextToSpeechClient:
    """Lazy-initialise a regional Vertex AI TTS client (EU endpoint)."""
    global _TTS_CLIENT
    if _TTS_CLIENT is None:
        endpoint = f"{VERTEX_LOCATION}-texttospeech.googleapis.com"
        logger.info(f"🔊 Initialising Vertex AI TTS client → {endpoint}")
        opts = ClientOptions(api_endpoint=endpoint)
        _TTS_CLIENT = texttospeech.TextToSpeechClient(client_options=opts)
    return _TTS_CLIENT

# Chirp HD default suffix.  D = Male, F = Female, O = Female (alt).
DEFAULT_CHIRP_SUFFIX = "F"

# Best available voice per language on the europe-west1 endpoint.
# Languages with Chirp-HD get the high-quality model; others fall back
# to the best Neural2 / Wavenet voice available.
DEFAULT_VOICES = {
    # ── Chirp HD languages (highest quality) ──
    "fr-FR": "fr-FR-Chirp-HD-F",
    "fr-CA": "fr-CA-Chirp-HD-F",
    "en-US": "en-US-Chirp-HD-F",
    "en-GB": "en-GB-Chirp-HD-F",
    "en-AU": "en-AU-Chirp-HD-F",
    "en-IN": "en-IN-Chirp-HD-F",
    "es-ES": "es-ES-Chirp-HD-F",
    "es-US": "es-US-Chirp-HD-F",
    "de-DE": "de-DE-Chirp-HD-F",
    "it-IT": "it-IT-Chirp-HD-F",
    # ── Neural2 / Wavenet fallback ──
    "pt-BR": "pt-BR-Neural2-A",
    "ja-JP": "ja-JP-Neural2-B",
    "ko-KR": "ko-KR-Neural2-A",
    "zh-CN": "cmn-CN-Wavenet-A",
    "ar-XA": "ar-XA-Wavenet-A",
    "hi-IN": "hi-IN-Neural2-A",
    "nl-NL": "nl-NL-Wavenet-F",
    "pl-PL": "pl-PL-Wavenet-F",
    "ru-RU": "ru-RU-Wavenet-A",
    "tr-TR": "tr-TR-Wavenet-A",
}

def _resolve_voice_name(language_code: str, voice_name: str | None = None) -> str:
    """
    Resolve the full wire voice name for a language.
    If *voice_name* is already a full wire name (contains '-'), return as-is.
    If it is a Chirp HD suffix letter (D/F/O), build the Chirp-HD name.
    Otherwise fall back to DEFAULT_VOICES or a Neural2-A guess.
    """
    if voice_name and "-" in voice_name:
        # Already a full wire name like 'fr-FR-Chirp-HD-F'
        return voice_name
    if voice_name and voice_name in ("D", "F", "O"):
        return f"{language_code}-Chirp-HD-{voice_name}"
    if voice_name:
        # Unknown short name; try as Chirp-HD suffix
        return f"{language_code}-Chirp-HD-{voice_name}"
    # No voice specified: use default mapping
    return DEFAULT_VOICES.get(language_code, f"{language_code}-Neural2-A")

def calculate_tts_cost(char_count: int, voice_name: str) -> float:
    """
    Estimates cost for Vertex AI TTS.
    Pricing (approximate USD per 1 M characters, 2025-Q4):
    - Chirp HD : $30
    - Neural2  : $16
    - Wavenet  : $16
    - Standard : $4
    """
    if "Chirp" in voice_name:
        cost_per_million = 30.0
    elif "Neural2" in voice_name:
        cost_per_million = 16.0
    elif "Wavenet" in voice_name:
        cost_per_million = 16.0
    else:
        cost_per_million = 4.0
    cost = (char_count / 1_000_000) * cost_per_million
    return round(cost, 6)

def get_audio_duration(audio_path: str) -> float:
    """
    Returns the duration of the audio file (in seconds) using ffprobe.
    """
    audio_path = os.path.abspath(audio_path)
    logger.info(f"\n🔍 Getting audio duration for: {audio_path}")
    cmd = [
        _FFPROBE_PATH,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    logger.info(f"   Command: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        logger.info(f"   ffprobe return code: {result.returncode}")
        logger.info(f"   ffprobe stdout: '{result.stdout.strip()}'")

        if result.returncode != 0 or not result.stdout.strip():
            logger.warning(f"   ⚠️ Impossible to retrieve duration for {audio_path}, defaulting to None.")
            logger.warning(f"   ffprobe stderr: {result.stderr}")
            return None

        duration = float(result.stdout.strip())
        logger.info(f"   ✅ Duration: {duration:.2f}s")
        return duration
    except Exception as e:
        logger.error(f"   ⚠️ Error getting duration for {audio_path}: {e}")
        return None

def extract_page_texts(pdf_path: str) -> List[Dict]:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            pages.append({"index": i, "text": text})
    return pages

def build_uniform_segments(num_pages: int, min_sections: int = 3) -> List[Dict]:
    """
    Splits num_pages into min_sections segments.
    """
    if num_pages <= 0:
        return []

    n_segments = min(min_sections, num_pages)
    base = num_pages // n_segments
    extra = num_pages % n_segments

    segments = []
    start = 0
    for i in range(n_segments):
        length = base + (1 if i < extra else 0)
        end = start + length
        segments.append({
            "index": i + 1,
            "start": start,
            "end": end
        })
        start = end

    return segments

def pdf_to_images(pdf_path: str, out_dir: str, dpi: int = 150) -> List[str]:
    """
    Converts each page of the PDF to PNG using PyMuPDF (fitz).
    """
    logger.info(f"\n🖼️  pdf_to_images called")
    logger.info(f"   PDF path: {pdf_path}")
    logger.info(f"   Output dir: {out_dir}")
    logger.info(f"   DPI: {dpi}")
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    
    try:
        doc = fitz.open(pdf_path)
        logger.info(f"   PDF opened: {len(doc)} pages")
        for i in range(len(doc)):
            page = doc.load_page(i)
            # Set zoom factor based on DPI (72 is default PDF DPI)
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            out_path = os.path.join(out_dir, f"page_{i+1:03d}.png")
            pix.save(out_path)
            file_size = os.path.getsize(out_path) / 1024
            logger.info(f"   Page {i+1}/{len(doc)} -> {out_path} ({pix.width}x{pix.height}, {file_size:.1f} KB)")
            paths.append(out_path)
        doc.close()
        logger.info(f"   ✅ All {len(paths)} pages converted to images")
    except Exception as e:
        logger.error(f"   ❌ Error converting PDF to images: {e}")
        raise RuntimeError(f"Failed to convert PDF to images: {e}")

    return paths


def normalize_images(image_path: str, out_dir: str) -> List[str]:
    """
    Handles single image files (JPG, PNG, GIF).
    If it's an animated GIF, it is PRESERVED as a single file (not split).
    Static images are converted to PNG.
    Returns a list of file paths.
    """
    logger.info(f"\n🖼️  normalize_images called")
    logger.info(f"   Image path: {image_path}")
    logger.info(f"   Output dir: {out_dir}")
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    
    try:
        img = Image.open(image_path)
        logger.info(f"   Image opened: {img.format}, size={img.size}, mode={img.mode}")
        
        # Check if it's an animated GIF
        is_animated = False
        if getattr(img, "is_animated", False):
            is_animated = True
        elif hasattr(img, 'n_frames') and img.n_frames > 1:
            is_animated = True

        if is_animated:
            logger.info(f"   Animated GIF detected ({img.n_frames} frames). Preserving as looping video slide.")
            out_path = os.path.join(out_dir, f"page_001.gif")
            shutil.copy2(image_path, out_path)
            logger.info(f"   Copied to: {out_path}")
            paths.append(out_path)
        else:
            logger.info(f"   Static image. Converting to PNG.")
            out_path = os.path.join(out_dir, f"page_001.png")
            img.convert("RGB").save(out_path, "PNG")
            file_size = os.path.getsize(out_path) / 1024
            logger.info(f"   Saved to: {out_path} ({file_size:.1f} KB)")
            paths.append(out_path)
            
    except Exception as e:
        logger.error(f"   ❌ Error processing image: {e}")
        raise RuntimeError(f"Failed to process image: {e}")
    
    return paths


def extract_images_from_directory(dir_path: str) -> List[str]:
    """
    If multiple image files are in a directory, extract them.
    Useful for batch processing of multiple images.
    Returns list of image paths sorted by filename.
    """
    supported_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
    image_files = []
    
    if not os.path.isdir(dir_path):
        return []
    
    for filename in sorted(os.listdir(dir_path)):
        if filename.lower().endswith(supported_extensions):
            image_files.append(os.path.join(dir_path, filename))
    
    return image_files


async def generate_vertex_tts(text: str, output_path: str, language_code: str = "fr-FR", voice_name: str = None):
    """
    Generates audio using Vertex AI TTS (Chirp HD / Neural2 / Wavenet)
    via the google-cloud-texttospeech SDK.  The client is pinned to the
    EU regional endpoint configured by GOOGLE_VERTEX_LOCATION.
    """
    full_voice_name = _resolve_voice_name(language_code, voice_name)

    logger.info(f"\n🎵 generate_vertex_tts called")
    logger.info(f"   Text ({len(text)} chars): '{text[:100]}...'")
    logger.info(f"   Output path: {output_path}")
    logger.info(f"   Language: {language_code}, Voice: {full_voice_name}")

    client = _get_tts_client()

    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice_params = texttospeech.VoiceSelectionParams(
        language_code=language_code,
        name=full_voice_name,
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
    )

    def _synthesize():
        return client.synthesize_speech(
            input=synthesis_input,
            voice=voice_params,
            audio_config=audio_config,
        )

    logger.info(f"   Sending request to Vertex AI TTS ({VERTEX_LOCATION})...")
    response = await asyncio.to_thread(_synthesize)

    if response.audio_content:
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(response.audio_content)
        file_size = os.path.getsize(output_path)
        logger.info(f"   ✅ Audio saved: {output_path} ({file_size} bytes, {file_size/1024:.1f} KB)")
        return True
    else:
        logger.error("   ❌ No audio content in Vertex AI TTS response")
        raise RuntimeError("No audio content in Vertex AI TTS response")

async def generate_tts_audios(voice_data: List[Dict], audio_dir: str, language_code: str = "fr-FR", voice_name: str = None) -> tuple[Dict[int, Dict], List[str], Dict[str, float]]:
    """
    Generates MP3 for each slide using Vertex AI Chirp 3: HD Voices.
    Returns: (page_to_info_map, list_of_log_messages, tts_usage_info)
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"🎙️  generate_tts_audios called")
    logger.info(f"   Audio dir: {audio_dir}")
    logger.info(f"   Language: {language_code}")
    logger.info(f"   Voice name (param): {voice_name}")
    os.makedirs(audio_dir, exist_ok=True)
    page_to_info = {}
    logs = []
    tts_errors = []  # Collect per-page error messages for diagnostics
    total_chars = 0
    
    # Determine short Chirp 3 HD voice name
    # Resolve the full wire voice name
    voice_name = _resolve_voice_name(language_code, voice_name)
    logger.info(f"   Resolved voice: {voice_name}")

    # Handle nested structure if present
    data_list = voice_data
    if isinstance(voice_data, list) and len(voice_data) > 0 and "data" in voice_data[0]:
        data_list = voice_data[0]["data"]
        logger.info(f"   Unwrapped nested 'data' key from voice_data")
    elif isinstance(voice_data, dict) and "data" in voice_data:
        data_list = voice_data["data"]
        logger.info(f"   Unwrapped 'data' key from voice_data dict")
    
    logger.info(f"   Processing {len(data_list)} items using Vertex AI TTS ({language_code} / {voice_name}).")
    logs.append(f"Processing {len(data_list)} items using Vertex AI TTS ({language_code} / {voice_name}).")

    for item_idx, item in enumerate(data_list):
        if not isinstance(item, dict):
            logger.warning(f"   [{item_idx}] Skipping non-dict item: {item}")
            continue
        if "page_number" not in item or "voice_over" not in item:
            logger.warning(f"   [{item_idx}] Skipping item without page_number or voice_over: {item}")
            logs.append(f"Skipping item without page_number or voice_over: {item}")
            continue

        page_num = int(item["page_number"])
        text = item["voice_over"]
        title = item.get("slide_title", "")
        
        logger.info(f"\n   📄 [{item_idx+1}/{len(data_list)}] Page {page_num}: title='{title}'")
        logger.info(f"      Text ({len(text)} chars): '{text[:80]}...'")
        
        if not text or not text.strip():
            msg = f"⚠️ Empty text for page {page_num}, skipping TTS."
            logger.warning(f"      {msg}")
            logs.append(msg)
            page_to_info[page_num] = {
                "audio_path": None,
                "duration": 5.0,
                "title": title
            }
            continue

        total_chars += len(text)
        logger.info(f"      Total chars so far: {total_chars}")
        audio_path = os.path.join(audio_dir, f"page_{page_num:03d}.mp3")

        logger.info(f"      🔊 Generating TTS -> {audio_path}")
        
        try:
            logs.append(f"Page {page_num} text ({len(text)} chars): {text[:50]}...")

            await generate_vertex_tts(text, audio_path, language_code=language_code, voice_name=voice_name)

            # Verify file size
            if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                msg = f"❌ Generated audio file for page {page_num} is empty or missing."
                logger.error(f"      {msg}")
                raise RuntimeError("Empty audio file generated")

            audio_file_size = os.path.getsize(audio_path)
            logger.info(f"      Audio file size: {audio_file_size} bytes ({audio_file_size/1024:.1f} KB)")

            duration = get_audio_duration(audio_path)
            if duration is None:
                msg = f"❌ Invalid audio file (ffprobe failed) for page {page_num}"
                logger.error(f"      {msg}")
                raise RuntimeError("Invalid audio file (ffprobe failed)")
            
            logger.info(f"      ✅ TTS done: page {page_num}, duration={duration:.2f}s, voice={voice_name}")
            logs.append(f"✅ Generated audio for page {page_num} using {voice_name} ({duration}s)")
            
            # Small delay to be nice to the API
            await asyncio.sleep(0.1)

        except Exception as e:
            msg = f"❌ Failed to generate TTS for page {page_num}: {e}"
            logger.error(f"      {msg}")
            logs.append(msg)
            tts_errors.append(f"page {page_num}: {e}")
            duration = 5.0 # Fallback
            audio_path = None 

        page_to_info[page_num] = {
            "audio_path": audio_path,
            "duration": duration,
            "title": title,
        }
        logger.info(f"      page_to_info[{page_num}] = audio={audio_path is not None}, duration={duration}, title='{title}'")

    total_cost = calculate_tts_cost(total_chars, voice_name)
    failed_pages = sum(1 for info in page_to_info.values() if info["audio_path"] is None)
    tts_usage = {
        "total_chars": total_chars,
        "total_cost_usd": total_cost,
        "voice_name": voice_name,
        "failed_pages": failed_pages,
        "errors": tts_errors,
    }
    
    logger.info(f"\n   💰 TTS Usage Summary:")
    logger.info(f"      Total characters: {total_chars}")
    logger.info(f"      Estimated cost: ${total_cost:.6f}")
    logger.info(f"      Voice: {voice_name}")
    logger.info(f"      Pages processed: {len(page_to_info)}")
    logger.info(f"      Failed pages: {failed_pages}")
    if tts_errors:
        logger.error(f"      TTS errors: {tts_errors}")
    logger.info(f"{'='*60}\n")
    
    return page_to_info, logs, tts_usage

def create_single_slide_video(image_path: str,
                              audio_path: str,
                              duration: float,
                              output_path: str):
    """
    Creates a video for ONE slide.
    Handles static images (PNG, JPG) and looping GIFs.
    """
    image_path = os.path.abspath(image_path)
    output_path = os.path.abspath(output_path)
    
    logger.info(f"\n🎬 create_single_slide_video")
    logger.info(f"   Image: {image_path}")
    logger.info(f"   Audio: {audio_path}")
    logger.info(f"   Duration: {duration}s")
    logger.info(f"   Output: {output_path}")
    
    # Check if input is a GIF
    is_gif = image_path.lower().endswith('.gif')
    logger.info(f"   Is GIF: {is_gif}")

    # Ensure duration is at least something small to avoid ffmpeg errors
    if duration <= 0:
        duration = 5.0

    # Build input arguments
    input_args = []
    if is_gif:
        # Loop the GIF indefinitely
        input_args = ["-stream_loop", "-1", "-i", image_path]
    else:
        # Loop static image
        input_args = ["-loop", "1", "-i", image_path]

    # Build audio arguments
    if audio_path is None:
        # Silent audio
        audio_args = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    else:
        audio_path = os.path.abspath(audio_path)
        audio_args = ["-i", audio_path]

    # Assemble command
    cmd = [
        _FFMPEG_PATH, "-y",
        *input_args,
        *audio_args,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        "-vf", "scale=1280:-2",
        # For GIFs used as video streams + audio, -shortest might cut it if stream_loop isn't working right
        # But we force duration with -t, so it should be fine.
        output_path,
    ]

    logger.info(f"🎞️  Slide -> video : {output_path} (target duration = {duration}s)")
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        logger.error("❌ ffmpeg failed for slide")
        logger.error(result.stderr)
        raise RuntimeError(f"ffmpeg error (code {result.returncode}) for {output_path}: {result.stderr}")


def concat_videos(video_paths: List[str], output_path: str):
    """
    Concatenates multiple mp4 files into one.
    """
    logger.info(f"\n🔗 concat_videos called")
    logger.info(f"   Input videos: {len(video_paths)}")
    for i, vp in enumerate(video_paths):
        vsize = os.path.getsize(vp) / (1024*1024) if os.path.exists(vp) else 0
        logger.info(f"     [{i+1}] {vp} ({vsize:.2f} MB)")
    logger.info(f"   Output: {output_path}")
    
    if not video_paths:
        raise ValueError("No videos to concatenate")

    abs_videos = [os.path.abspath(p) for p in video_paths]

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as f:
        list_path = f.name
        for v in abs_videos:
            safe_v = v.replace("'", r"'\''")
            f.write(f"file '{safe_v}'\n")

    output_path = os.path.abspath(output_path)

    cmd = [
        _FFMPEG_PATH,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]

    logger.info(f"   ffmpeg concat command: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Clean up list file
    try:
        os.remove(list_path)
    except:
        pass

    logger.info(f"   ffmpeg concat return code: {result.returncode}")
    if result.returncode != 0:
        logger.error(f"   ❌ ffmpeg concat failed")
        logger.error(f"   ffmpeg stderr: {result.stderr[:500]}")
        raise RuntimeError(f"ffmpeg concat error (code {result.returncode}) for {output_path}")
    else:
        file_size = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"   ✅ Concatenated video: {output_path} ({file_size:.2f} MB)")

async def process_pdf_with_voice(pdf_path: str,
                           voice_data: List[Dict],
                           workdir: str,
                           min_sections: int = 3,
                           default_duration: float = 5.0,
                           language_code: str = "fr-FR",
                           voice_name: str = None) -> tuple[List[Dict], List[str], Dict[str, float]]:   
    """
    Main pipeline.
    Returns (results, logs, tts_usage)
    """
    os.makedirs(workdir, exist_ok=True)
    logs = []

    # A. Number of pages
    pages = extract_page_texts(pdf_path)
    if not pages:
        raise ValueError("The PDF contains no readable pages.")
    num_pages = len(pages)
    logger.info(f"📄 Number of pages : {num_pages}")
    logs.append(f"PDF loaded with {num_pages} pages.")

    segments = build_uniform_segments(num_pages, min_sections=min_sections)
    logger.info(f"📦 Segments : {segments}")

    # B. PDF -> images
    img_dir = os.path.join(workdir, "images_tmp")
    image_paths = pdf_to_images(pdf_path, img_dir)
    logs.append(f"Converted PDF to {len(image_paths)} images.")

    # B2. Add watermark to all slide images
    add_watermark_to_images(image_paths)
    logs.append("Added 'Generated By MyQAteam AI' watermark to all slides.")

    # C. Generate TTS audios
    audio_dir = os.path.join(workdir, "audio_tmp")
    page_to_info, tts_logs, tts_usage = await generate_tts_audios(voice_data, audio_dir, language_code=language_code, voice_name=voice_name)
    logs.extend(tts_logs)

    # D. Build videos
    slide_video_dir = os.path.join(workdir, "slides_tmp")
    os.makedirs(slide_video_dir, exist_ok=True)

    results = []

    for seg in segments:
        start, end = seg["start"], seg["end"]
        pages_numbers = list(range(start + 1, end + 1))  # 1-based
        logger.info(f"\n📚 Segment {seg['index']} -> pages {pages_numbers[0]} to {pages_numbers[-1]}")

        segment_slide_videos = []

        for p in pages_numbers:
            # Ensure we don't go out of bounds if PDF has fewer pages than expected
            if p - 1 >= len(image_paths):
                break
                
            img_path = image_paths[p - 1]
            info = page_to_info.get(p)

            if info is not None:
                audio_path = info["audio_path"]
                duration = info["duration"]
            else:
                audio_path = None
                duration = default_duration
                logs.append(f"⚠️ No audio info for page {p}, using silent default.")

            slide_video_path = os.path.join(
                slide_video_dir,
                f"segment{seg['index']:02d}_page{p:03d}.mp4"
            )

            try:
                create_single_slide_video(
                    image_path=img_path,
                    audio_path=audio_path,
                    duration=duration,
                    output_path=slide_video_path
                )
                segment_slide_videos.append(slide_video_path)
            except Exception as e:
                logs.append(f"❌ Failed to create video for page {p}: {e}")

        # Concat segment
        if segment_slide_videos:
            final_segment_path = os.path.join(workdir, f"part_{seg['index']:02d}.mp4")
            try:
                concat_videos(segment_slide_videos, final_segment_path)

                results.append({
                    "index": seg["index"],
                    "pages": pages_numbers,
                    "video_path": final_segment_path
                })
            except Exception as e:
                logs.append(f"❌ Failed to concat segment {seg['index']}: {e}")

    # E. Cleanup
    # We might want to keep the final videos, but clean up intermediates
    shutil.rmtree(img_dir, ignore_errors=True)
    shutil.rmtree(audio_dir, ignore_errors=True)
    shutil.rmtree(slide_video_dir, ignore_errors=True)
    logger.info("\n🧹 Temporary files removed.")

    return results, logs, tts_usage


async def process_media_with_voice(media_path: str,
                            voice_data: List[Dict],
                            workdir: str,
                            min_sections: int = 3,
                            default_duration: float = 5.0,
                            language_code: str = "fr-FR",
                            voice_name: str = None) -> tuple[List[Dict], List[str], Dict[str, float]]:
    """
    Unified pipeline that handles both PDF and image files.
    """
    logger.info(f"\n{'#'*80}")
    logger.info(f"### process_media_with_voice STARTED")
    logger.info(f"    media_path: {media_path}")
    logger.info(f"    workdir: {workdir}")
    logger.info(f"    min_sections: {min_sections}")
    logger.info(f"    default_duration: {default_duration}")
    logger.info(f"    language_code: {language_code}")
    logger.info(f"    voice_name: {voice_name}")
    logger.info(f"    voice_data items: {len(voice_data) if isinstance(voice_data, list) else 'dict'}")
    logger.info(f"{'#'*80}")
    
    os.makedirs(workdir, exist_ok=True)
    logs = []
    
    # Determine media type
    media_ext = os.path.splitext(media_path)[1].lower()
    is_pdf = media_ext == '.pdf'
    logger.info(f"\n   File extension: {media_ext}, is_pdf: {is_pdf}")
    
    # A. Extract images based on file type
    img_dir = os.path.join(workdir, "images_tmp")
    
    if is_pdf:
        logger.info(f"📄 Processing PDF file...")
        logs.append(f"Processing PDF file: {os.path.basename(media_path)}")
        
        # Extract text for page count (for PDF)
        pages = extract_page_texts(media_path)
        if not pages:
            raise ValueError("The PDF contains no readable pages.")
        num_pages = len(pages)
        logger.info(f"📄 Number of pages : {num_pages}")
        logs.append(f"PDF loaded with {num_pages} pages.")
        
        # Convert PDF to images
        image_paths = pdf_to_images(media_path, img_dir)
        logs.append(f"Converted PDF to {len(image_paths)} images.")
        
    else:
        # Handle image files (JPG, PNG, GIF)
        logger.info(f"🖼️  Processing image file...")
        logs.append(f"Processing image file: {os.path.basename(media_path)}")
        
        # Normalize image(s) - handles single images and animated GIFs
        image_paths = normalize_images(media_path, img_dir)
        num_pages = len(image_paths)
        logger.info(f"🖼️  Extracted {num_pages} image(s)")
        logs.append(f"Extracted {num_pages} image(s) from {os.path.basename(media_path)}.")
    
    if not image_paths:
        logger.error("   ❌ No images could be extracted from the media file.")
        raise ValueError("No images could be extracted from the media file.")

    # A2. Add watermark to all slide images
    add_watermark_to_images(image_paths)
    logs.append("Added 'Generated By MyQAteam AI' watermark to all slides.")
    
    num_pages = len(image_paths)
    logger.info(f"   Total image pages: {num_pages}")
    segments = build_uniform_segments(num_pages, min_sections=min_sections)
    logger.info(f"   Segments: {segments}")

    # C. Generate TTS audios
    logger.info(f"\n   🎙️  Step C: Generating TTS audios...")
    audio_dir = os.path.join(workdir, "audio_tmp")
    page_to_info, tts_logs, tts_usage = await generate_tts_audios(voice_data, audio_dir, language_code=language_code, voice_name=voice_name)
    logs.extend(tts_logs)

    # Fail early if every single slide failed TTS — no point building silent 5-sec clips
    if page_to_info and all(info["audio_path"] is None for info in page_to_info.values()):
        first_error = tts_usage["errors"][0] if tts_usage.get("errors") else "Unknown TTS error"
        raise RuntimeError(f"TTS generation failed for all slides. First error: {first_error}")

    # D. Build videos
    logger.info(f"\n   🎬 Step D: Building slide videos...")
    slide_video_dir = os.path.join(workdir, "slides_tmp")
    os.makedirs(slide_video_dir, exist_ok=True)

    results = []

    for seg in segments:
        start, end = seg["start"], seg["end"]
        pages_numbers = list(range(start + 1, end + 1))  # 1-based
        logger.info(f"\n   📚 Segment {seg['index']} -> pages {pages_numbers[0]} to {pages_numbers[-1]}")

        segment_slide_videos = []

        for p in pages_numbers:
            # Ensure we don't go out of bounds
            if p - 1 >= len(image_paths):
                logger.warning(f"      Page {p} is out of bounds (only {len(image_paths)} images). Skipping.")
                break
                
            img_path = image_paths[p - 1]
            info = page_to_info.get(p)

            if info is not None:
                audio_path = info["audio_path"]
                duration = info["duration"]
                logger.info(f"      Page {p}: audio={'YES' if audio_path else 'NONE'}, duration={duration}s")
            else:
                audio_path = None
                duration = default_duration
                logger.info(f"      Page {p}: no audio info, using silent default ({default_duration}s)")
                logs.append(f"⚠️ No audio info for page {p}, using silent default.")

            slide_video_path = os.path.join(
                slide_video_dir,
                f"segment{seg['index']:02d}_page{p:03d}.mp4"
            )

            try:
                create_single_slide_video(
                    image_path=img_path,
                    audio_path=audio_path,
                    duration=duration,
                    output_path=slide_video_path
                )
                segment_slide_videos.append(slide_video_path)
                logger.info(f"      ✅ Slide video created for page {p}")
            except Exception as e:
                logger.error(f"      ❌ Failed to create video for page {p}: {e}")
                logs.append(f"❌ Failed to create video for page {p}: {e}")

        # Concat segment
        if segment_slide_videos:
            final_segment_path = os.path.join(workdir, f"part_{seg['index']:02d}.mp4")
            logger.info(f"      Concatenating {len(segment_slide_videos)} slide videos -> {final_segment_path}")
            try:
                concat_videos(segment_slide_videos, final_segment_path)

                results.append({
                    "index": seg["index"],
                    "pages": pages_numbers,
                    "video_path": final_segment_path
                })
                logger.info(f"      ✅ Segment {seg['index']} concatenated successfully")
            except Exception as e:
                logger.error(f"      ❌ Failed to concat segment {seg['index']}: {e}")
                logs.append(f"❌ Failed to concat segment {seg['index']}: {e}")
        else:
            logger.warning(f"      ⚠️ No slide videos for segment {seg['index']}, skipping concat")

    # E. Cleanup
    logger.info(f"\n   🧹 Step E: Cleaning up temporary files...")
    shutil.rmtree(img_dir, ignore_errors=True)
    shutil.rmtree(audio_dir, ignore_errors=True)
    shutil.rmtree(slide_video_dir, ignore_errors=True)
    logger.info(f"   ✅ Temporary files removed.")
    
    logger.info(f"\n{'#'*80}")
    logger.info(f"### process_media_with_voice COMPLETED")
    logger.info(f"    Results: {len(results)} video segments")
    logger.info(f"    Logs: {len(logs)} entries")
    logger.info(f"{'#'*80}\n")

    return results, logs, tts_usage

async def process_image_collection(image_paths: List[str],
                            voice_data: List[Dict],
                            workdir: str,
                            min_sections: int = 3,
                            default_duration: float = 5.0,
                            language_code: str = "fr-FR",
                            voice_name: str = None) -> tuple[List[Dict], List[str], Dict[str, float]]:    
    """
    Processes a collection of image files as individual slides.
    Each image is treated as a page/slide in order.
    
    Supports: JPG, PNG, GIF (animated GIFs are extracted frame-by-frame)
    
    Returns (results, logs, tts_usage)
    """
    logger.info(f"\n{'#'*80}")
    logger.info(f"### process_image_collection STARTED")
    logger.info(f"    image_paths: {image_paths}")
    logger.info(f"    workdir: {workdir}")
    logger.info(f"    min_sections: {min_sections}")
    logger.info(f"    language_code: {language_code}")
    logger.info(f"    voice_name: {voice_name}")
    logger.info(f"    voice_data items: {len(voice_data) if isinstance(voice_data, list) else 'dict'}")
    logger.info(f"{'#'*80}")
    
    os.makedirs(workdir, exist_ok=True)
    logs = []
    
    logger.info(f"\n🖼️  Processing collection of {len(image_paths)} image(s)...")
    logs.append(f"Processing collection of {len(image_paths)} image file(s).")
    
    # A. Convert all images to PNG format
    img_dir = os.path.join(workdir, "images_tmp")
    os.makedirs(img_dir, exist_ok=True)
    
    all_image_paths = []
    image_counter = 1
    
    for idx, image_path in enumerate(image_paths):
        logger.info(f"Processing image {idx + 1}/{len(image_paths)}: {os.path.basename(image_path)}")
        logs.append(f"Processing image {idx + 1}: {os.path.basename(image_path)}")
        
        try:
            # Each image file might be a regular image or animated GIF
            img = Image.open(image_path)
            
            # Check if it's an animated GIF
            is_animated = False
            if getattr(img, "is_animated", False):
                is_animated = True
            elif hasattr(img, 'n_frames') and img.n_frames > 1:
                is_animated = True

            if is_animated:
                logger.info(f"  → Animated GIF detected. Preserving as looping slide.")
                logs.append(f"  → Animated GIF preserved.")
                
                # Copy original GIF
                out_path = os.path.join(img_dir, f"page_{image_counter:03d}.gif")
                # Using shutil.copy2 to preserve metadata if possible
                shutil.copy2(image_path, out_path)
                all_image_paths.append(out_path)
                image_counter += 1
            else:
                # Single image
                out_path = os.path.join(img_dir, f"page_{image_counter:03d}.png")
                img.convert("RGB").save(out_path, "PNG")
                all_image_paths.append(out_path)
                image_counter += 1
                
        except Exception as e:
            msg = f"❌ Failed to process image {os.path.basename(image_path)}: {e}"
            logger.error(msg)
            logs.append(msg)
            continue
    
    if not all_image_paths:
        raise ValueError("No images could be processed from the collection.")

    # A2. Add watermark to all slide images
    add_watermark_to_images(all_image_paths)
    logs.append("Added 'Generated By MyQAteam AI' watermark to all slides.")
    
    num_pages = len(all_image_paths)
    logger.info(f"🖼️  Total pages extracted: {num_pages}")
    logs.append(f"Total pages extracted: {num_pages}")
    
    segments = build_uniform_segments(num_pages, min_sections=min_sections)
    logger.info(f"📦 Segments : {segments}")

    # C. Generate TTS audios
    logger.info(f"\n   🎙️  Step C: Generating TTS audios...")
    audio_dir = os.path.join(workdir, "audio_tmp")
    page_to_info, tts_logs, tts_usage = await generate_tts_audios(voice_data, audio_dir, language_code=language_code, voice_name=voice_name)
    logs.extend(tts_logs)

    # Fail early if every single slide failed TTS — no point building silent 5-sec clips
    if page_to_info and all(info["audio_path"] is None for info in page_to_info.values()):
        first_error = tts_usage["errors"][0] if tts_usage.get("errors") else "Unknown TTS error"
        raise RuntimeError(f"TTS generation failed for all slides. First error: {first_error}")

    # D. Build videos
    logger.info(f"\n   🎬 Step D: Building slide videos...")
    slide_video_dir = os.path.join(workdir, "slides_tmp")
    os.makedirs(slide_video_dir, exist_ok=True)

    results = []

    for seg in segments:
        start, end = seg["start"], seg["end"]
        pages_numbers = list(range(start + 1, end + 1))  # 1-based
        logger.info(f"\n   📚 Segment {seg['index']} -> pages {pages_numbers[0]} to {pages_numbers[-1]}")

        segment_slide_videos = []

        for p in pages_numbers:
            # Ensure we don't go out of bounds
            if p - 1 >= len(all_image_paths):
                logger.warning(f"      Page {p} is out of bounds (only {len(all_image_paths)} images). Skipping.")
                break
                
            img_path = all_image_paths[p - 1]
            info = page_to_info.get(p)

            if info is not None:
                audio_path = info["audio_path"]
                duration = info["duration"]
                logger.info(f"      Page {p}: audio={'YES' if audio_path else 'NONE'}, duration={duration}s")
            else:
                audio_path = None
                duration = default_duration
                logger.info(f"      Page {p}: no audio info, using silent default ({default_duration}s)")
                logs.append(f"⚠️ No audio info for page {p}, using silent default.")

            slide_video_path = os.path.join(
                slide_video_dir,
                f"segment{seg['index']:02d}_page{p:03d}.mp4"
            )

            try:
                create_single_slide_video(
                    image_path=img_path,
                    audio_path=audio_path,
                    duration=duration,
                    output_path=slide_video_path
                )
                segment_slide_videos.append(slide_video_path)
                logger.info(f"      ✅ Slide video created for page {p}")
            except Exception as e:
                logger.error(f"      ❌ Failed to create video for page {p}: {e}")
                logs.append(f"❌ Failed to create video for page {p}: {e}")

        # Concat segment
        if segment_slide_videos:
            final_segment_path = os.path.join(workdir, f"part_{seg['index']:02d}.mp4")
            logger.info(f"      Concatenating {len(segment_slide_videos)} slide videos -> {final_segment_path}")
            try:
                concat_videos(segment_slide_videos, final_segment_path)

                results.append({
                    "index": seg["index"],
                    "pages": pages_numbers,
                    "video_path": final_segment_path
                })
                logger.info(f"      ✅ Segment {seg['index']} concatenated successfully")
            except Exception as e:
                logger.error(f"      ❌ Failed to concat segment {seg['index']}: {e}")
                logs.append(f"❌ Failed to concat segment {seg['index']}: {e}")
        else:
            logger.warning(f"      ⚠️ No slide videos for segment {seg['index']}, skipping concat")

    # E. Cleanup
    logger.info(f"\n   🧹 Step E: Cleaning up temporary files...")
    shutil.rmtree(img_dir, ignore_errors=True)
    shutil.rmtree(audio_dir, ignore_errors=True)
    shutil.rmtree(slide_video_dir, ignore_errors=True)
    logger.info(f"   ✅ Temporary files removed.")

    logger.info(f"\n{'#'*80}")
    logger.info(f"### process_image_collection COMPLETED")
    logger.info(f"    Results: {len(results)} video segments")
    logger.info(f"    Logs: {len(logs)} entries")
    logger.info(f"{'#'*80}\n")

    return results, logs, tts_usage