"""
Test script for the async callback workflow of /generate-narrative endpoint.

This script demonstrates both modes:
1. Async mode with callback URL
2. Synchronous mode (original behavior)
"""
import requests
import time
import uuid
from flask import Flask, request, jsonify
import threading
import json

# ============================================================================
# Mock Callback Server (simulates your main application receiving callbacks)
# ============================================================================

app = Flask(__name__)
callback_results = {}

@app.route('/api/tools/learn/video-callback', methods=['POST'])
def video_callback():
    """Mock callback endpoint that receives video generation results."""
    
    # Verify secret header
    secret = request.headers.get('x-callback-secret')
    if secret != 'test-secret-123':
        return jsonify({"error": "Invalid callback secret"}), 403
    
    data = request.json
    job_id = data.get('jobId')
    status = data.get('status')
    
    print(f"\n{'='*60}")
    print(f"📥 CALLBACK RECEIVED for job: {job_id}")
    print(f"Status: {status}")
    
    if status == 'completed':
        video_count = len(data.get('videos', []))
        metadata = data.get('metadata', {})
        print(f"✅ SUCCESS - {video_count} videos generated")
        print(f"   Processing time: {metadata.get('processingTime')}s")
        print(f"   Total duration: {metadata.get('totalDuration')}s")
        print(f"   TTS cost: ${metadata.get('ttsCost')}")
        
        # Store first video for inspection
        if data.get('videos'):
            first_video = data['videos'][0]
            print(f"   First video: {first_video['filename']} ({len(first_video['data'])} chars base64)")
    
    elif status == 'failed':
        print(f"❌ FAILED - {data.get('error')}")
        print(f"   Failed at: {data.get('failedAt')}")
    
    print('='*60)
    
    # Store result for inspection
    callback_results[job_id] = data
    
    return jsonify({"success": True}), 200

def run_callback_server():
    """Run the mock callback server in a background thread."""
    app.run(port=5000, debug=False, use_reloader=False)


# ============================================================================
# Test Functions
# ============================================================================

def test_async_mode():
    """Test async callback workflow."""
    print("\n" + "="*60)
    print("TEST 1: Async Mode (with callback)")
    print("="*60)
    
    job_id = str(uuid.uuid4())
    
    # Prepare test data
    files = {
        'files': ('test_slide.png', open('test_output_local/slide_1.png', 'rb'), 'image/png')
    }
    
    script_data = [
        {
            "page_number": 1,
            "voice_over": "Ceci est un test de génération vidéo asynchrone.",
            "slide_title": "Test Slide"
        }
    ]
    
    data = {
        'script': json.dumps(script_data),
        'language': 'fr-FR',
        'jobId': job_id,
        'callbackUrl': 'http://localhost:5000/api/tools/learn/video-callback',
        'callbackSecret': 'test-secret-123',
        'documentId': 'doc-123',
        'projectId': 'project-456'
    }
    
    # Send request to toolbox API
    print(f"📤 Sending async request with jobId: {job_id}")
    response = requests.post(
        'http://localhost:8000/api/generate-narrative',
        files=files,
        data=data
    )
    
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.json()}")
    
    if response.status_code == 202:
        print("✅ Request accepted - processing in background")
        
        # Poll job status endpoint
        print("\n📊 Polling job status...")
        for i in range(30):  # Poll for up to 5 minutes
            time.sleep(10)
            status_response = requests.get(
                f'http://localhost:8000/api/narrative-job/{job_id}'
            )
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                print(f"   Status: {status_data.get('status')} (attempt {i+1})")
                
                if status_data.get('status') in ['completed', 'failed', 'callback_failed']:
                    break
        
        # Check if callback was received
        time.sleep(2)  # Give callback a moment to arrive
        if job_id in callback_results:
            print("\n✅ Callback was successfully received!")
        else:
            print("\n⚠️ Callback was not received (check logs)")
    else:
        print(f"❌ Request failed: {response.text}")


def test_sync_mode():
    """Test original synchronous workflow (no callback)."""
    print("\n" + "="*60)
    print("TEST 2: Sync Mode (original behavior)")
    print("="*60)
    
    files = {
        'files': ('test_slide.png', open('test_output_local/slide_1.png', 'rb'), 'image/png')
    }
    
    script_data = [
        {
            "page_number": 1,
            "voice_over": "Test synchrone sans callback.",
            "slide_title": "Test"
        }
    ]
    
    data = {
        'script': json.dumps(script_data),
        'language': 'fr-FR'
        # No callbackUrl - should use original sync behavior
    }
    
    print("📤 Sending sync request (no callback)...")
    response = requests.post(
        'http://localhost:8000/api/generate-narrative',
        files=files,
        data=data,
        stream=True
    )
    
    print(f"Response status: {response.status_code}")
    
    if response.status_code == 200:
        # Save ZIP file
        with open('test_sync_output.zip', 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print("✅ ZIP file received and saved as test_sync_output.zip")
        print(f"   Headers: {dict(response.headers)}")
    else:
        print(f"❌ Request failed: {response.text}")


# ============================================================================
# Main Execution
# ============================================================================

if __name__ == '__main__':
    print("""
╔══════════════════════════════════════════════════════════════╗
║   Async Callback Workflow Test Suite                        ║
║   Testing /generate-narrative endpoint                       ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Start mock callback server in background
    print("🚀 Starting mock callback server on http://localhost:5000...")
    server_thread = threading.Thread(target=run_callback_server, daemon=True)
    server_thread.start()
    time.sleep(2)  # Give server time to start
    
    # Check if test file exists
    import os
    if not os.path.exists('test_output_local/slide_1.png'):
        print("⚠️ Warning: test_output_local/slide_1.png not found")
        print("   Please ensure you have a test image file, or update the path in this script")
        exit(1)
    
    try:
        # Run tests
        test_async_mode()
        print("\n" + "="*60)
        input("Press Enter to run sync mode test...")
        test_sync_mode()
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*60)
    print("Tests complete!")
    print("="*60)
