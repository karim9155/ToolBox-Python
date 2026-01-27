import asyncio
import os
import shutil
import tempfile
from unittest.mock import patch, MagicMock

# Import the service directly
# Note: This requires the app module to be in the python path
import sys
sys.path.append(os.getcwd())

from app.services.narrative_video import generate_tts_audios, process_media_with_voice

# Mock the actual API call to avoid credentials/network issues
async def mock_generate_google_tts(text, output_path, language_code, voice_name):
    # Simulate creating a dummy mp3 file
    with open(output_path, "wb") as f:
        f.write(b"\x00\x00\x00\x00") # Dummy bytes
    return True

# Mock duration
def mock_get_audio_duration(path):
    return 5.0

# Mock other heavy dependencies if necessary
def mock_extract_page_texts(pdf_path):
    return [{"index": 0, "text": "Page 1 Content"}, {"index": 1, "text": "Page 2 Content"}]

def mock_pdf_to_images(pdf_path, out_dir, dpi=150):
    # Ensure directory exists (mimicking original function behavior)
    os.makedirs(out_dir, exist_ok=True)
    # Create dummy images
    img1 = os.path.join(out_dir, "page_001.png")
    img2 = os.path.join(out_dir, "page_002.png")
    for img in [img1, img2]:
        with open(img, "wb") as f:
            f.write(b"fake_image_data")
    return [img1, img2]

def mock_create_single_slide_video(image_path, audio_path, duration, output_path):
    with open(output_path, "wb") as f:
        f.write(b"fake_video_data")

def mock_concat_videos(video_paths, output_path):
    with open(output_path, "wb") as f:
        f.write(b"fake_concat_video_data")

async def run_integration_test():
    print("🧪 Starting TTS Cost Integration Test...")
    
    # Test Data
    voice_data = [
        {"page_number": 1, "voice_over": "Hello World", "slide_title": "Slide 1"},
        {"page_number": 2, "voice_over": "This used to cost money.", "slide_title": "Slide 2"}
    ]
    
    # Setup temp workspace
    temp_dir = tempfile.mkdtemp()
    audio_dir = os.path.join(temp_dir, "audio_tmp")
    
    try:
        print("\n1️⃣ Testing generate_tts_audios logic...")
        
        # Patch the external calls
        with patch("app.services.narrative_video.generate_google_tts", side_effect=mock_generate_google_tts), \
             patch("app.services.narrative_video.get_audio_duration", side_effect=mock_get_audio_duration):
            
            # --- TEST 1: Direct function call ---
            # voice used in code for en-US is 'en-US-Studio-M' -> $160/1M chars
            page_map, logs, tts_usage = await generate_tts_audios(voice_data, audio_dir, language_code="en-US")
            
            # Calculate Expected
            text1 = "Hello World" # 11
            text2 = "This used to cost money." # 24
            total_chars = len(text1) + len(text2) # 35
            
            expected_cost = (total_chars / 1_000_000) * 160.0
            
            print(f"   Input Chars: {total_chars}")
            print(f"   Calculated Cost: ${tts_usage['total_cost_usd']:.8f}")
            print(f"   Expected Cost:   ${expected_cost:.8f}")
            
            assert tts_usage["total_chars"] == total_chars, f"Char count mismatch: {tts_usage['total_chars']} != {total_chars}"
            assert abs(tts_usage["total_cost_usd"] - expected_cost) < 1e-9, "Cost calculation mismatch"
            assert "Studio" in tts_usage["voice_name"], "Voice name mismatch"
            
            print("   ✅ generate_tts_audios passed verification.")


        print("\n2️⃣ Testing process_media_with_voice unpacking...")
        # create a dummy pdf file
        dummy_pdf = os.path.join(temp_dir, "test.pdf")
        with open(dummy_pdf, "w") as f:
            f.write("dummy pdf")

        with patch("app.services.narrative_video.generate_google_tts", side_effect=mock_generate_google_tts), \
             patch("app.services.narrative_video.get_audio_duration", side_effect=mock_get_audio_duration), \
             patch("app.services.narrative_video.extract_page_texts", side_effect=mock_extract_page_texts), \
             patch("app.services.narrative_video.pdf_to_images", side_effect=mock_pdf_to_images), \
             patch("app.services.narrative_video.create_single_slide_video", side_effect=mock_create_single_slide_video), \
             patch("app.services.narrative_video.concat_videos", side_effect=mock_concat_videos):

             # Call the higher level function to ensure unpacking works
             results, logs, usage = await process_media_with_voice(
                 media_path=dummy_pdf,
                 voice_data=voice_data,
                 workdir=temp_dir,
                 language_code="en-US"
             )
             
             assert usage is not None
             assert "total_cost_usd" in usage
             print(f"   Received Usage from pipeline: {usage}")
             print("   ✅ Pipeline unpacking passed.")
             
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        shutil.rmtree(temp_dir)
        print("\n🧹 Cleanup done.")

if __name__ == "__main__":
    asyncio.run(run_integration_test())
