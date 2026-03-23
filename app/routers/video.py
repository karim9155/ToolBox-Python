import os
import shutil
import subprocess
import tempfile
from typing import Optional

import cv2
from fastapi import APIRouter, File, Query, UploadFile, HTTPException
from fastapi.responses import Response

router = APIRouter()

_FFMPEG_PATH = shutil.which("ffmpeg") or os.path.expandvars(
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.EXE"
)

def extract_last_frame_bytes(data: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
        f.write(data)
        path = f.name

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        raise ValueError("Cannot open video")

    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if n > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, n - 1)
        ok, frame = cap.read()
    else:
        ok, frame = False, None
        while True:
            r, fr = cap.read()
            if not r:
                break
            ok, frame = r, fr

    cap.release()

    if not ok or frame is None:
        raise ValueError("Failed to read last frame")

    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise ValueError("Failed to encode frame")

    return buf.tobytes()

@router.post("/last-frame", tags=["Video"])
async def last_frame(file: UploadFile = File(...)):
    try:
        data = await file.read()
        return Response(content=extract_last_frame_bytes(data), media_type="image/jpeg")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _convert_video_to_gif(
    input_path: str,
    output_path: str,
    fps: int = 20,
    width: int = -1,
    max_duration: Optional[float] = None,
) -> None:
    """Single-pass per-frame palette conversion for maximum GIF quality.

    Each frame gets its own optimised 256-colour palette, producing much
    better colour reproduction than a single global palette — especially
    for real-world video with varied scenes and gradients.
    """
    duration_args = ["-t", str(max_duration)] if max_duration else []

    # Build the scale part only when the caller requests resizing
    if width > 0:
        scale = f"scale={width}:-1:flags=lanczos,"
    else:
        scale = ""

    # Single-pass: split stream → per-frame palettegen → paletteuse
    filtergraph = (
        f"fps={fps},{scale}split[s0][s1];"
        f"[s0]palettegen=max_colors=256:stats_mode=single[p];"
        f"[s1][p]paletteuse=dither=sierra2_4a:new=1"
    )

    cmd = [
        _FFMPEG_PATH, "-y",
        *duration_args,
        "-i", input_path,
        "-lavfi", filtergraph,
        "-loop", "0",
        output_path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"GIF encoding failed: {result.stderr[-500:]}")


@router.post("/video-to-gif", tags=["Video"])
async def video_to_gif(
    file: UploadFile = File(...),
    fps: int = Query(20, ge=1, le=30, description="Output frames per second"),
    width: int = Query(-1, ge=-1, le=1920, description="Output width in px (-1 = original resolution)"),
    max_duration: Optional[float] = Query(None, gt=0, le=60, description="Max seconds to convert"),
):
    tmp_dir = tempfile.mkdtemp()
    try:
        input_path = os.path.join(tmp_dir, "input.mp4")
        output_path = os.path.join(tmp_dir, "output.gif")

        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        with open(input_path, "wb") as f:
            f.write(data)

        _convert_video_to_gif(input_path, output_path, fps=fps, width=width, max_duration=max_duration)

        with open(output_path, "rb") as f:
            gif_bytes = f.read()

        return Response(
            content=gif_bytes,
            media_type="image/gif",
            headers={"Content-Disposition": 'attachment; filename="output.gif"'},
        )
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
