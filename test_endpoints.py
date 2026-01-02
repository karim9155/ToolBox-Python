import requests
import cv2
import numpy as np
import wave
import fitz  # PyMuPDF
import os
import time
import json

BASE_URL = "http://54.37.78.55:8000"

def create_dummy_video(filename="test_video.mp4"):
    height, width = 480, 640
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video = cv2.VideoWriter(filename, fourcc, 10, (width, height))
    
    for i in range(30):
        # Create a frame with random color
        frame = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
        # Add frame number text
        cv2.putText(frame, f"Frame {i}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        video.write(frame)
    
    video.release()
    print(f"Created {filename}")

def create_dummy_audio(filename="test_audio.wav"):
    with wave.open(filename, 'w') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(44100)
        # Generate 1 second of silence/noise
        data = np.random.randint(-32768, 32767, 44100, dtype=np.int16)
        f.writeframes(data.tobytes())
    print(f"Created {filename}")

def create_dummy_pdf(filename="test_report.pdf"):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "FSSC 22000 Audit Report")
    page.insert_text((50, 100), "1. Audit Details")
    page.insert_text((50, 150), "Date: 2023-01-01")
    doc.save(filename)
    print(f"Created {filename}")

def test_root():
    print("\nTesting GET / ...")
    try:
        r = requests.get(f"{BASE_URL}/")
        print(f"Status: {r.status_code}")
        print(f"Response: {r.json()}")
        assert r.status_code == 200
    except Exception as e:
        print(f"Failed: {e}")

def test_last_frame():
    print("\nTesting POST /last-frame ...")
    filename = "test_video.mp4"
    if not os.path.exists(filename):
        create_dummy_video(filename)
    
    try:
        with open(filename, "rb") as f:
            files = {"file": (filename, f, "video/mp4")}
            r = requests.post(f"{BASE_URL}/last-frame", files=files)
        
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            print("Success! Received image bytes.")
            with open("last_frame_output.jpg", "wb") as f:
                f.write(r.content)
        else:
            print(f"Error: {r.text}")
    except Exception as e:
        print(f"Failed: {e}")

def test_transcribe():
    print("\nTesting POST /transcribe ...")
    filename = "test_audio.wav"
    if not os.path.exists(filename):
        create_dummy_audio(filename)
        
    # Note: This might fail if the API key is invalid or if AssemblyAI rejects the dummy audio
    # But we want to see if the endpoint is reachable and tries to process
    try:
        with open(filename, "rb") as f:
            files = {"file": (filename, f, "audio/wav")}
            r = requests.post(f"{BASE_URL}/transcribe", files=files)
        
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            print(f"Response: {r.json()}")
        else:
            print(f"Error: {r.text}")
    except Exception as e:
        print(f"Failed: {e}")

def test_audit_time():
    print("\nTesting POST /audit-time ...")
    payload = {
        "standard": "IFS Food 7",
        "employees": 50,
        "productScopes": ["1"],
        "processingSteps": ["P1"]
    }
    
    try:
        r = requests.post(f"{BASE_URL}/audit-time", json=payload)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            print(f"Response: {r.json()}")
        else:
            print(f"Error: {r.text}")
    except Exception as e:
        print(f"Failed: {e}")

def test_fssc_extract():
    print("\nTesting POST /extract/fssc ...")
    filename = "test_report.pdf"
    if not os.path.exists(filename):
        create_dummy_pdf(filename)
        
    try:
        with open(filename, "rb") as f:
            files = {"file": (filename, f, "application/pdf")}
            r = requests.post(f"{BASE_URL}/extract/fssc?format=json", files=files)
        
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            print(f"Response: {r.json()}")
        else:
            print(f"Error: {r.text}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    # Wait for server to start
    print("Waiting for server to be ready...")
    time.sleep(5)
    
    test_root()
    test_last_frame()
    test_transcribe()
    test_audit_time()
    test_fssc_extract()
