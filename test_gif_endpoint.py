"""Quick smoke test for POST /video-to-gif."""
import subprocess, os, tempfile, requests

# 1. Create a 2-second synthetic test video
tmp = os.path.join(tempfile.gettempdir(), "test_input.mp4")
subprocess.run(
    ["ffmpeg", "-y", "-f", "lavfi", "-i",
     "testsrc=duration=2:size=320x240:rate=10",
     "-c:v", "libx264", "-pix_fmt", "yuv420p", tmp],
    capture_output=True,
)
print(f"Test video created: {os.path.getsize(tmp)} bytes")

# 2. Call the endpoint
with open(tmp, "rb") as f:
    r = requests.post(
        "http://localhost:8000/video-to-gif?fps=10&width=320",
        files={"file": ("test.mp4", f, "video/mp4")},
    )

print(f"Status: {r.status_code}")
ct = r.headers.get("content-type", "")
print(f"Content-Type: {ct}")
print(f"Response size: {len(r.content)} bytes")

if r.status_code == 200:
    print(f"Valid GIF header: {r.content[:3] == b'GIF'}")
    gif_path = os.path.join(tempfile.gettempdir(), "test_output.gif")
    with open(gif_path, "wb") as f:
        f.write(r.content)
    print(f"Saved to: {gif_path}")
else:
    print(f"Error body: {r.text[:500]}")
