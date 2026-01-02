import asyncio
import edge_tts

# Text to speak
TEXT = "Bonjour. Ceci est une démonstration de la synthèse vocale utilisant Microsoft Edge. La qualité est bien meilleure que celle de Google Translate, n'est-ce pas ?"

# Output file
OUTPUT_FILE = "sample_edge_tts.mp3"

# Voice to use (French examples)
# fr-FR-DeniseNeural (Female)
# fr-FR-HenriNeural (Male)
VOICE = "fr-FR-HenriNeural"

async def main():
    print(f"Generating audio with voice: {VOICE}...")
    communicate = edge_tts.Communicate(TEXT, VOICE)
    await communicate.save(OUTPUT_FILE)
    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Error: {e}")
