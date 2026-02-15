import os
import shutil
import tempfile
import subprocess
import json
from typing import List, Dict
import logging
import asyncio
import requests
import base64
from PIL import Image

import pdfplumber
import fitz  # PyMuPDF
# import edge_tts # Removed in favor of Google TTS

logger = logging.getLogger(__name__)

# Google Cloud TTS Configuration
# Key is now loaded from environment variable for security
GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY")
GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

# Default voices for common languages
DEFAULT_VOICES = {
    "fr-FR": "fr-FR-Studio-D",
    "en-US": "en-US-Studio-M",
    "es-ES": "es-ES-Studio-C",
    "de-DE": "de-DE-Studio-B",
    "it-IT": "it-IT-Neural2-A",
    "pt-BR": "pt-BR-Neural2-A",
    "ja-JP": "ja-JP-Neural2-B",
    "ko-KR": "ko-KR-Neural2-A",
    "zh-CN": "cmn-CN-Wavenet-A", # Studio/Neural2 availability varies for CN
}

def calculate_tts_cost(char_count: int, voice_name: str) -> float:
    """
    Estimates the cost of Google TTS usage based on character count and voice type.
    Pricing (approximate USD per 1M chars):
    - Studio: $160.00
    - Neural2: $16.00
    - WaveNet: $16.00
    - Standard: $4.00
    """
    cost_per_million = 4.0 # Default/Standard
    
    if "Studio" in voice_name:
        cost_per_million = 160.0
    elif "Neural2" in voice_name:
        cost_per_million = 16.0
    elif "Wavenet" in voice_name:
        cost_per_million = 16.0
        
    cost = (char_count / 1_000_000) * cost_per_million
    return round(cost, 6)

def get_audio_duration(audio_path: str) -> float:
    """
    Returns the duration of the audio file (in seconds) using ffprobe.
    """
    audio_path = os.path.abspath(audio_path)
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    try:
        # On Windows, we might need shell=True or full path if not in PATH, 
        # but usually subprocess.run works if ffmpeg/ffprobe are in PATH.
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )

        if result.returncode != 0 or not result.stdout.strip():
            logger.warning(f"⚠️ Impossible to retrieve duration for {audio_path}, defaulting to None.")
            logger.warning(f"ffprobe stderr: {result.stderr}")
            return None

        return float(result.stdout.strip())
    except Exception as e:
        logger.error(f"⚠️ Error getting duration for {audio_path}: {e}")
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
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    
    try:
        doc = fitz.open(pdf_path)
        for i in range(len(doc)):
            page = doc.load_page(i)
            # Set zoom factor based on DPI (72 is default PDF DPI)
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            out_path = os.path.join(out_dir, f"page_{i+1:03d}.png")
            pix.save(out_path)
            paths.append(out_path)
        doc.close()
    except Exception as e:
        logger.error(f"Error converting PDF to images: {e}")
        raise RuntimeError(f"Failed to convert PDF to images: {e}")

    return paths


def normalize_images(image_path: str, out_dir: str) -> List[str]:
    """
    Handles single image files (JPG, PNG, GIF).
    If it's an animated GIF, it is PRESERVED as a single file (not split).
    Static images are converted to PNG.
    Returns a list of file paths.
    """
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    
    try:
        img = Image.open(image_path)
        
        # Check if it's an animated GIF
        is_animated = False
        if getattr(img, "is_animated", False):
            is_animated = True
        elif hasattr(img, 'n_frames') and img.n_frames > 1:
            is_animated = True

        if is_animated:
            # COPY the GIF as is, don't split it
            logger.info(f"Animated GIF usage: preserving as looping video slide.")
            out_path = os.path.join(out_dir, f"page_001.gif")
            # We must save or copy the file
            # Since PIL saving might not preserve all optimizations, simplest is to copy the original file
            # but we assume the original 'image_path' is accessible.
            shutil.copy2(image_path, out_path)
            paths.append(out_path)
        else:
            # Single image file - convert to PNG
            out_path = os.path.join(out_dir, f"page_001.png")
            img.convert("RGB").save(out_path, "PNG")
            paths.append(out_path)
            
    except Exception as e:
        logger.error(f"Error processing image: {e}")
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


async def generate_google_tts(text: str, output_path: str, language_code: str = "fr-FR", voice_name: str = "fr-FR-Neural2-B"):
    """
    Generates audio using Google Cloud Text-to-Speech API.
    """
    headers = {"Content-Type": "application/json; charset=utf-8"}
    data = {
        "input": {"text": text},
        "voice": {"languageCode": language_code, "name": voice_name},
        "audioConfig": {"audioEncoding": "MP3"}
    }
    params = {"key": GOOGLE_TTS_API_KEY}

    if not GOOGLE_TTS_API_KEY:
        raise RuntimeError("GOOGLE_TTS_API_KEY environment variable is not set.")

    def _request():
        return requests.post(GOOGLE_TTS_URL, headers=headers, json=data, params=params)

    # Run blocking request in a separate thread
    response = await asyncio.to_thread(_request)

    if response.status_code == 200:
        response_json = response.json()
        audio_content = response_json.get("audioContent")
        if audio_content:
            # Ensure output directory exists
            output_dir = os.path.dirname(output_path)
            if output_dir:  # Only create directory if there is one
                os.makedirs(output_dir, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(audio_content))
            logger.info(f"✅ Saved audio to {output_path} ({os.path.getsize(output_path)} bytes)")
            return True
        else:
            raise RuntimeError(f"No audio content in Google TTS response. Response: {response_json}")
    else:
        raise RuntimeError(f"Google TTS API Error ({response.status_code}): {response.text}")

async def generate_tts_audios(voice_data: List[Dict], audio_dir: str, language_code: str = "fr-FR", voice_name: str = None) -> tuple[Dict[int, Dict], List[str], Dict[str, float]]:
    """
    Generates MP3 for each slide using Google Cloud TTS.
    Returns: (page_to_info_map, list_of_log_messages, tts_usage_info)
    """
    os.makedirs(audio_dir, exist_ok=True)
    page_to_info = {}
    logs = []
    total_chars = 0
    
    # Determine voice name from parameter, language code, or fallback
    if not voice_name:
        voice_name = DEFAULT_VOICES.get(language_code)
        if not voice_name:
            # Fallback heuristic or default to English if unknown
            voice_name = f"{language_code}-Neural2-A"
            logs.append(f"⚠️ Unknown language {language_code}, trying fallback voice {voice_name}")

    # Handle nested structure if present (e.g. [{"data": [...]}] or just [...])
    data_list = voice_data
    if isinstance(voice_data, list) and len(voice_data) > 0 and "data" in voice_data[0]:
        data_list = voice_data[0]["data"]
    elif isinstance(voice_data, dict) and "data" in voice_data:
        data_list = voice_data["data"]
    
    logs.append(f"Processing {len(data_list)} items from voice_data using Google TTS ({language_code} / {voice_name}).")

    for item in data_list:
        if not isinstance(item, dict):
            continue
        if "page_number" not in item or "voice_over" not in item:
            logs.append(f"Skipping item without page_number or voice_over: {item}")
            continue

        page_num = int(item["page_number"])
        text = item["voice_over"]
        title = item.get("slide_title", "")
        
        if not text or not text.strip():
            msg = f"⚠️ Empty text for page {page_num}, skipping TTS."
            logger.warning(msg)
            logs.append(msg)
            # Default silent entry
            page_to_info[page_num] = {
                "audio_path": None,
                "duration": 5.0,
                "title": title
            }
            continue

        total_chars += len(text)
        audio_path = os.path.join(audio_dir, f"page_{page_num:03d}.mp3")

        logger.info(f"🔊 Google TTS page {page_num} ...")
        
        try:
            # Log truncated text for debugging
            logs.append(f"Page {page_num} text ({len(text)} chars): {text[:50]}...")

            await generate_google_tts(text, audio_path, language_code=language_code, voice_name=voice_name)

            # Verify file size
            if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                msg = f"❌ Generated audio file for page {page_num} is empty or missing."
                logger.error(msg)
                raise RuntimeError("Empty audio file generated")

            duration = get_audio_duration(audio_path)
            if duration is None:
                msg = f"❌ Invalid audio file (ffprobe failed) for page {page_num}"
                raise RuntimeError("Invalid audio file (ffprobe failed)")
            
            logs.append(f"✅ Generated audio for page {page_num} using {voice_name} ({duration}s)")
            
            # Small delay to be nice to the API
            await asyncio.sleep(0.1)

        except Exception as e:
            msg = f"❌ Failed to generate TTS for page {page_num}: {e}"
            logger.error(msg)
            logs.append(msg)
            duration = 5.0 # Fallback
            audio_path = None 

        page_to_info[page_num] = {
            "audio_path": audio_path,
            "duration": duration,
            "title": title,
        }

    total_cost = calculate_tts_cost(total_chars, voice_name)
    tts_usage = {
        "total_chars": total_chars,
        "total_cost_usd": total_cost,
        "voice_name": voice_name
    }
    
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
    
    # Check if input is a GIF
    is_gif = image_path.lower().endswith('.gif')

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
        "ffmpeg", "-y",
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
        "ffmpeg",
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

    logger.info(f"🔗 Concatenation to : {output_path}")
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

    if result.returncode != 0:
        logger.error("❌ ffmpeg concat failed")
        logger.error(result.stderr)
        raise RuntimeError(f"ffmpeg concat error (code {result.returncode}) for {output_path}")

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
    Unified pipeline that handles both PDF and image files (JPG, PNG, GIF).
    Treats images the same way as PDF pages to generate videos.
    
    - PDF: Extracts all pages as images
    - Single Image (JPG, PNG): Treats as single page
    - Animated GIF: Extracts all frames as pages
    
    Returns (results, logs, tts_usage)
    """
    os.makedirs(workdir, exist_ok=True)
    logs = []
    
    # Determine media type
    media_ext = os.path.splitext(media_path)[1].lower()
    is_pdf = media_ext == '.pdf'
    
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
        raise ValueError("No images could be extracted from the media file.")
    
    num_pages = len(image_paths)
    segments = build_uniform_segments(num_pages, min_sections=min_sections)
    logger.info(f"📦 Segments : {segments}")

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
            # Ensure we don't go out of bounds
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
    shutil.rmtree(img_dir, ignore_errors=True)
    shutil.rmtree(audio_dir, ignore_errors=True)
    shutil.rmtree(slide_video_dir, ignore_errors=True)
    logger.info("\n🧹 Temporary files removed.")

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
    os.makedirs(workdir, exist_ok=True)
    logs = []
    
    logger.info(f"🖼️  Processing collection of {len(image_paths)} image(s)...")
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
    
    num_pages = len(all_image_paths)
    logger.info(f"🖼️  Total pages extracted: {num_pages}")
    logs.append(f"Total pages extracted: {num_pages}")
    
    segments = build_uniform_segments(num_pages, min_sections=min_sections)
    logger.info(f"📦 Segments : {segments}")

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
            # Ensure we don't go out of bounds
            if p - 1 >= len(all_image_paths):
                break
                
            img_path = all_image_paths[p - 1]
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
    shutil.rmtree(img_dir, ignore_errors=True)
    shutil.rmtree(audio_dir, ignore_errors=True)
    shutil.rmtree(slide_video_dir, ignore_errors=True)
    logger.info("\n🧹 Temporary files removed.")

    return results, logs, tts_usage