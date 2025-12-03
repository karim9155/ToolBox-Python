import asyncio
import requests
import base64
import os

# Google Cloud TTS Configuration
GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY")
GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

async def test_google_tts_local():
    if not GOOGLE_TTS_API_KEY:
        print("❌ Error: GOOGLE_TTS_API_KEY environment variable is not set.")
        return

    text = "Ceci est un test local de l'API Google Cloud Text-to-Speech."
    output_path = "test_google_local.mp3"
    language_code = "fr-FR"
    voice_name = "fr-FR-Neural2-B"

    print(f"Testing Google TTS with key: {GOOGLE_TTS_API_KEY[:10]}...")
    
    headers = {"Content-Type": "application/json; charset=utf-8"}
    data = {
        "input": {"text": text},
        "voice": {"languageCode": language_code, "name": voice_name},
        "audioConfig": {"audioEncoding": "MP3"}
    }
    params = {"key": GOOGLE_TTS_API_KEY}

    def _request():
        return requests.post(GOOGLE_TTS_URL, headers=headers, json=data, params=params)

    try:
        print("Sending request to Google...")
        response = await asyncio.to_thread(_request)

        if response.status_code == 200:
            response_json = response.json()
            audio_content = response_json.get("audioContent")
            if audio_content:
                with open(output_path, "wb") as f:
                    f.write(base64.b64decode(audio_content))
                print(f"✅ Success! Audio saved to {output_path}")
            else:
                print("❌ Error: No audio content in response.")
        else:
            print(f"❌ API Error ({response.status_code}):")
            print(response.text)
            
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_google_tts_local())
