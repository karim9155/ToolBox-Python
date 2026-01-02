import asyncio
import edge_tts
import os

async def test_tts_robust():
    voice = "fr-FR-HenriNeural"
    fallback_voices = ["fr-FR-DeniseNeural", "en-US-AriaNeural"]
    text = "Ceci est un test de synthèse vocale avec logique de secours."
    output = "test_audio_robust.mp3"
    
    print(f"Testing TTS with primary voice: {voice}")
    
    voices_to_try = [voice] + fallback_voices
    success = False
    
    for current_voice in voices_to_try:
        print(f"Attempting voice: {current_voice}")
        try:
            communicate = edge_tts.Communicate(text, current_voice)
            await communicate.save(output)
            
            # Verify file
            if os.path.exists(output) and os.path.getsize(output) > 0:
                print(f"✅ Success! Audio generated with {current_voice}")
                success = True
                break
            else:
                print(f"❌ File created but empty with {current_voice}")
                
        except Exception as e:
            print(f"❌ Error with {current_voice}: {e}")
            
    if not success:
        print("❌ All voices failed.")
    else:
        print("Test complete.")

if __name__ == "__main__":
    asyncio.run(test_tts_robust())
