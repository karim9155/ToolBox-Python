"""
End-to-end test: Generate videos for a real project from prod database.
"""
import os
import sys
import asyncio
import tempfile
import shutil
from dotenv import load_dotenv

load_dotenv()

print("="*80)
print("🎬 END-TO-END VIDEO GENERATION TEST")
print("="*80)

# Project configuration
PROJECT_ID = "ef7883e9-1345-4f7b-8848-a6461975ba5a"
ENVIRONMENT = "prod"

print(f"\n📋 Configuration:")
print(f"   Project ID: {PROJECT_ID}")
print(f"   Environment: {ENVIRONMENT}")

# Import required modules
print("\n1️⃣ Importing modules...")
try:
    from app.utils.supabase_storage import get_supabase_client, upload_video_to_supabase
    from app.services.narrative_video import process_image_collection
    import httpx
    print("✅ Modules imported successfully")
except ImportError as e:
    print(f"❌ Failed to import modules: {e}")
    sys.exit(1)

# Connect to Supabase
print(f"\n2️⃣ Connecting to Supabase {ENVIRONMENT.upper()}...")
try:
    supabase = get_supabase_client(ENVIRONMENT)
    print(f"✅ Connected to Supabase {ENVIRONMENT}")
except Exception as e:
    print(f"❌ Failed to connect: {e}")
    sys.exit(1)

# Fetch project data
print(f"\n3️⃣ Fetching project data...")
try:
    # Query project
    url = f"{supabase.url}/rest/v1/projects"
    params = f"id=eq.{PROJECT_ID}"
    response = httpx.get(
        f"{url}?{params}",
        headers=supabase.headers,
        timeout=30
    )
    response.raise_for_status()
    projects = response.json()
    
    if not projects:
        print(f"❌ Project {PROJECT_ID} not found")
        sys.exit(1)
    
    project = projects[0]
    print(f"✅ Project found: {project.get('name', 'Unnamed')}")
    print(f"   Status: {project.get('status')}")
    
    # Get document_id from project
    document_id = project.get('document_id')
    if not document_id:
        print("❌ Project has no document_id")
        sys.exit(1)
    
    print(f"   Document ID: {document_id}")
    
except Exception as e:
    print(f"❌ Failed to fetch project: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Fetch slides (images)
print(f"\n4️⃣ Fetching slides...")
try:
    url = f"{supabase.url}/rest/v1/document_images"
    params = f"document_id=eq.{document_id}&order=image_index.asc"
    response = httpx.get(
        f"{url}?{params}",
        headers=supabase.headers,
        timeout=30
    )
    response.raise_for_status()
    slides = response.json()
    
    print(f"✅ Found {len(slides)} slides")
    
    if not slides:
        print("❌ No slides found for this document")
        sys.exit(1)
    
    for i, slide in enumerate(slides[:3]):  # Show first 3
        print(f"   Slide {i}: {slide.get('supabase_url', 'No URL')[:60]}...")
    
except Exception as e:
    print(f"❌ Failed to fetch slides: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Fetch scripts
print(f"\n5️⃣ Fetching scripts...")
try:
    url = f"{supabase.url}/rest/v1/narrative_scripts"
    params = f"document_id=eq.{document_id}&order=page_number.asc"
    response = httpx.get(
        f"{url}?{params}",
        headers=supabase.headers,
        timeout=30
    )
    response.raise_for_status()
    scripts = response.json()
    
    print(f"✅ Found {len(scripts)} scripts")
    
    if not scripts:
        print("❌ No scripts found for this document")
        sys.exit(1)
    
    for i, script in enumerate(scripts[:3]):  # Show first 3
        text = script.get('voice_over', '')
        print(f"   Script {i}: {text[:60]}...")
    
except Exception as e:
    print(f"❌ Failed to fetch scripts: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Prepare voice data with scripts
print(f"\n6️⃣ Preparing voice configuration with scripts...")
voice_config = project.get('voice_config', {})
voice_name = voice_config.get('voice_name', 'fr-FR-Studio-D')  # Default French voice
language = project.get('language', 'fr')

# Convert language to proper format (e.g., 'fr' -> 'fr-FR')
if language == 'fr' and '-' not in language:
    language = 'fr-FR'
elif language == 'en' and '-' not in language:
    language = 'en-US'

# Build voice_data array - one entry per script, matching expected format
voice_data = []
for i, script in enumerate(scripts):
    voice_data.append({
        "page_number": script.get('page_number'),  # Use actual page_number from DB
        "voice_over": script.get('voice_over', ''),
        "slide_title": script.get('slide_title', '')
    })

print(f"✅ Voice: {voice_name}")
print(f"   Language: {language}")
print(f"   Scripts: {len(voice_data)}")

# Download slides to temp directory (only for scripts we have)
print(f"\n7️⃣ Downloading slides for {len(scripts)} scripts...")
temp_dir = tempfile.mkdtemp()
image_paths = []

try:
    # Build mapping of page_number to script index
    script_by_page = {s.get('page_number'): i for i, s in enumerate(scripts)}
    
    # For each script, find the FIRST matching slide by page number
    for script_idx, script in enumerate(scripts):
        page_num = script.get('page_number')
        
        # Find first slide matching this page number
        matching_slide = next((s for s in slides if s.get('page_number') == page_num), None)
        
        if not matching_slide:
            print(f"⚠️ No slide found for script page {page_num}, skipping")
            continue
        
        image_url = matching_slide.get('supabase_url')
        if not image_url:
            print(f"⚠️ Slide for page {page_num} has no supabase_url, skipping")
            continue
        
        # Download image
        print(f"   Downloading slide for script {script_idx+1}/{len(scripts)} (page {page_num})...")
        try:
            response = httpx.get(image_url, timeout=60)
            response.raise_for_status()
            
            # Save to temp file
            image_path = os.path.join(temp_dir, f"slide_page_{page_num}_script_{script_idx}.jpg")
            with open(image_path, "wb") as f:
                f.write(response.content)
            
            image_paths.append(image_path)
        except Exception as e:
            print(f"⚠️ Failed to download slide for page {page_num}: {e}")
            continue
    
    print(f"✅ Downloaded {len(image_paths)} slides matching {len(scripts)} scripts")
    
except Exception as e:
    print(f"❌ Failed to download slides: {e}")
    shutil.rmtree(temp_dir, ignore_errors=True)
    sys.exit(1)

# Generate videos
print(f"\n8️⃣ Generating videos...")
print("   This may take several minutes...")

try:
    # Run async video generation
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    results, logs, tts_usage = loop.run_until_complete(
        process_image_collection(
            image_paths=image_paths,
            voice_data=voice_data,
            workdir=temp_dir,
            min_sections=len(image_paths),
            language_code=language,
            voice_name=voice_name
        )
    )
    loop.close()
    
    # Log all messages
    for log in logs:
        print(f"   {log}")
    
    print(f"\n✅ Generated {len(results)} videos!")
    print(f"   TTS Cost: ${tts_usage.get('total_cost_usd', 0):.4f}")
    print(f"   TTS Characters: {tts_usage.get('total_chars', 0)}")
    
    # Show video details
    for i, result in enumerate(results):
        video_path = result.get('video_path')
        duration = result.get('duration', 0)
        size_mb = os.path.getsize(video_path) / (1024 * 1024) if os.path.exists(video_path) else 0
        print(f"   Video {i}: {duration:.1f}s, {size_mb:.2f}MB")
    
except Exception as e:
    print(f"\n❌ Video generation failed: {e}")
    import traceback
    traceback.print_exc()
    shutil.rmtree(temp_dir, ignore_errors=True)
    sys.exit(1)

# Upload videos to Supabase
print(f"\n9️⃣ Uploading videos to Supabase {ENVIRONMENT.upper()}...")

uploaded_videos = []
failed_uploads = 0

for i, result in enumerate(results):
    video_path = result.get('video_path')
    
    if not os.path.exists(video_path):
        print(f"   ⚠️ Video {i} file not found, skipping")
        failed_uploads += 1
        continue
    
    filename = f"narrative_video_{i}.mp4"
    
    try:
        print(f"   Uploading video {i+1}/{len(results)}...")
        
        upload_result = upload_video_to_supabase(
            video_path=video_path,
            document_id=document_id,
            project_id=PROJECT_ID,
            filename=filename,
            video_index=i,
            environment=ENVIRONMENT
        )
        
        uploaded_videos.append(upload_result)
        print(f"   ✅ Video {i} uploaded successfully")
        print(f"      Storage: {upload_result['storage_path']}")
        print(f"      Record ID: {upload_result['record_id']}")
        
    except Exception as e:
        print(f"   ❌ Video {i} upload failed: {e}")
        failed_uploads += 1

# Summary
print(f"\n" + "="*80)
print(f"📊 SUMMARY")
print("="*80)
print(f"✅ Videos Generated: {len(results)}")
print(f"✅ Videos Uploaded: {len(uploaded_videos)}")
print(f"❌ Failed Uploads: {failed_uploads}")
print(f"💰 TTS Cost: ${tts_usage.get('total_cost_usd', 0):.4f}")
print(f"📝 TTS Characters: {tts_usage.get('total_chars', 0)}")
print(f"🗂️  Project ID: {PROJECT_ID}")
print(f"📄 Document ID: {document_id}")
print(f"🌐 Environment: {ENVIRONMENT.upper()}")
print("="*80)

if failed_uploads == 0:
    print("\n🎉 ALL VIDEOS UPLOADED SUCCESSFULLY!")
    print("\nYou can now query the narrative_videos table:")
    print(f"   SELECT * FROM narrative_videos WHERE document_id = '{document_id}';")
else:
    print(f"\n⚠️ {failed_uploads} videos failed to upload")

print("="*80)

# Cleanup
print("\n🧹 Cleaning up temporary files...")
shutil.rmtree(temp_dir, ignore_errors=True)
print("✅ Done!")
