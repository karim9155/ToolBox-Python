import asyncio
import edge_tts

async def test_tts():
    voice = "fr-FR-HenriNeural"
    text = "Bonjour, ceci est un test."
    output = "test_audio.mp3"
    
    print(f"Testing voice: {voice}")
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output)
        print("Success! Audio generated.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_tts())
