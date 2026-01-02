import asyncio
import os
import json
from app.services.narrative_video import process_pdf_with_voice

async def test_full_pipeline():
    pdf_path = os.path.abspath("test_narrative.pdf")
    workdir = os.path.abspath("test_output_local")
    
    # Create a dummy script for the PDF
    # Assuming the PDF has at least 1 page.
    voice_data = [
        {
            "page_number": 1,
            "voice_over": "Ceci est la première page du test local.",
            "slide_title": "Introduction"
        }
    ]
    
    print(f"Starting full pipeline test with {pdf_path}")
    
    try:
        results, logs = await process_pdf_with_voice(
            pdf_path=pdf_path,
            voice_data=voice_data,
            workdir=workdir,
            min_sections=1
        )
        
        print("\n--- Generation Logs ---")
        for log in logs:
            print(log)
        print("-----------------------")
        
        if results:
            print(f"\n✅ Success! Generated {len(results)} video segments.")
            for res in results:
                print(f"Video: {res['video_path']}")
        else:
            print("\n❌ No results generated.")
            
    except Exception as e:
        print(f"\n❌ Error during pipeline execution: {e}")

if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
