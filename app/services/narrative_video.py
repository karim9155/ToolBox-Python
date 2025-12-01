import os
import shutil
import tempfile
import subprocess
import json
from typing import List, Dict
import logging

import pdfplumber
import fitz  # PyMuPDF
from gtts import gTTS

logger = logging.getLogger(__name__)

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
            logger.warning(f"⚠️ Impossible to retrieve duration for {audio_path}, defaulting to 5s.")
            return 5.0

        return float(result.stdout.strip())
    except Exception as e:
        logger.error(f"⚠️ Error getting duration for {audio_path}: {e}")
        return 5.0

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


def generate_tts_audios(voice_data: List[Dict], audio_dir: str, lang: str = "fr") -> Dict[int, Dict]:
    """
    Generates MP3 for each slide using gTTS.
    """
    os.makedirs(audio_dir, exist_ok=True)
    page_to_info = {}

    # Handle nested structure if present (e.g. [{"data": [...]}] or just [...])
    data_list = voice_data
    if isinstance(voice_data, list) and len(voice_data) > 0 and "data" in voice_data[0]:
        data_list = voice_data[0]["data"]
    elif isinstance(voice_data, dict) and "data" in voice_data:
        data_list = voice_data["data"]

    for item in data_list:
        if not isinstance(item, dict):
            continue
        if "page_number" not in item or "voice_over" not in item:
            continue

        page_num = int(item["page_number"])
        text = item["voice_over"]
        title = item.get("slide_title", "")

        audio_path = os.path.join(audio_dir, f"page_{page_num:03d}.mp3")

        logger.info(f"🔊 gTTS page {page_num} ...")
        try:
            tts = gTTS(text=text, lang=lang)
            tts.save(audio_path)
            duration = get_audio_duration(audio_path)
        except Exception as e:
            logger.error(f"Error generating TTS for page {page_num}: {e}")
            duration = 5.0 # Fallback

        page_to_info[page_num] = {
            "audio_path": audio_path,
            "duration": duration,
            "title": title,
        }

    return page_to_info

def create_single_slide_video(image_path: str,
                              audio_path: str,
                              duration: float,
                              output_path: str):
    """
    Creates a video for ONE slide.
    """
    image_path = os.path.abspath(image_path)
    output_path = os.path.abspath(output_path)

    # Ensure duration is at least something small to avoid ffmpeg errors
    if duration <= 0:
        duration = 5.0

    if audio_path is None:
        # Silent audio
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-vf", "scale=1280:-2",
            "-shortest",
            output_path,
        ]
    else:
        audio_path = os.path.abspath(audio_path)
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-vf", "scale=1280:-2",
            "-shortest",
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
        raise RuntimeError(f"ffmpeg error (code {result.returncode}) for {output_path}")

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

def process_pdf_with_voice(pdf_path: str,
                           voice_data: List[Dict],
                           workdir: str,
                           min_sections: int = 3,
                           default_duration: float = 5.0) -> List[Dict]:
    """
    Main pipeline.
    """
    os.makedirs(workdir, exist_ok=True)

    # A. Number of pages
    pages = extract_page_texts(pdf_path)
    if not pages:
        raise ValueError("The PDF contains no readable pages.")
    num_pages = len(pages)
    logger.info(f"📄 Number of pages : {num_pages}")

    segments = build_uniform_segments(num_pages, min_sections=min_sections)
    logger.info(f"📦 Segments : {segments}")

    # B. PDF -> images
    img_dir = os.path.join(workdir, "images_tmp")
    image_paths = pdf_to_images(pdf_path, img_dir)

    # C. Generate TTS audios
    audio_dir = os.path.join(workdir, "audio_tmp")
    page_to_info = generate_tts_audios(voice_data, audio_dir, lang="fr")

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

            slide_video_path = os.path.join(
                slide_video_dir,
                f"segment{seg['index']:02d}_page{p:03d}.mp4"
            )

            create_single_slide_video(
                image_path=img_path,
                audio_path=audio_path,
                duration=duration,
                output_path=slide_video_path
            )

            segment_slide_videos.append(slide_video_path)

        # Concat segment
        if segment_slide_videos:
            final_segment_path = os.path.join(workdir, f"part_{seg['index']:02d}.mp4")
            concat_videos(segment_slide_videos, final_segment_path)

            results.append({
                "index": seg["index"],
                "pages": pages_numbers,
                "video_path": final_segment_path
            })

    # E. Cleanup
    # We might want to keep the final videos, but clean up intermediates
    shutil.rmtree(img_dir, ignore_errors=True)
    shutil.rmtree(audio_dir, ignore_errors=True)
    shutil.rmtree(slide_video_dir, ignore_errors=True)
    logger.info("\n🧹 Temporary files removed.")

    return results
