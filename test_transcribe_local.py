import os
import sys
from fastapi import UploadFile
import dotenv

# Load environment variables
dotenv.load_dotenv()

# Ensure we can import from app
sys.path.append(os.getcwd())

from app.routers.audio import transcribe

# Check API Key
if not os.getenv("ASSEMBLYAI_API_KEY"):
    print("❌ Error: ASSEMBLYAI_API_KEY is not set in environment variables.")
    print("Please set it in your .env file or environment.")
    sys.exit(1)

# Path to a test file
TEST_FILE = "test_google_local.mp3"

if not os.path.exists(TEST_FILE):
    # Try to find any mp3
    files = [f for f in os.listdir('.') if f.endswith('.mp3')]
    if files:
        TEST_FILE = files[0]
    else:
        print("❌ No MP3 files found to test. Please place an .mp3 file in this directory.")
        sys.exit(1)

print(f"Testing transcription with {TEST_FILE}...")

# Mock UploadFile structure expected by the endpoint
class MockUploadFile:
    def __init__(self, path):
        self.filename = os.path.basename(path)
        self.file = open(path, "rb")

try:
    mock_file = MockUploadFile(TEST_FILE)
    
    # Call transcribe with lang="auto"
    print("Calling transcribe(lang='auto')... This may take a minute.")
    result = transcribe(file=mock_file, lang="auto")
    
    print("\n--- ✅ Transcription Result ---")
    print(f"Text: {result.get('text')}")
    print(f"Language Code (detected): {result.get('utterances', [{}])[0].get('language_code', 'Unknown') if result.get('utterances') else 'Unknown'}")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
finally:
    if 'mock_file' in locals():
        mock_file.file.close()
