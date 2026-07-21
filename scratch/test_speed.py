import os
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

# Select 3 sample files from uploads/
upload_files = [f for f in os.listdir('uploads') if f.endswith('.pdf')][:3]
paths = [os.path.join('uploads', f) for f in upload_files]
print("Testing with files:", upload_files)

# --- Method 2: Inline bytes (Part.from_bytes) ---
t0 = time.time()
parts = []
for p in paths:
    fname = os.path.basename(p)
    with open(p, 'rb') as fp:
        raw_bytes = fp.read()
    parts.append(f"--- Document: {fname} ---")
    parts.append(types.Part.from_bytes(data=raw_bytes, mime_type="application/pdf"))
t1 = time.time()
print(f"[Method 2: Inline Bytes Preparation] Time taken: {t1 - t0:.2f} seconds")

# Call model with inline bytes
t0 = time.time()
resp = client.models.generate_content(
    model="gemini-3.5-flash",
    contents=["Extract candidate names as JSON list:", *parts],
    config=types.GenerateContentConfig(response_mime_type="application/json")
)
t1 = time.time()
print(f"[Method 2: Inline Generation Time] Time taken: {t1 - t0:.2f} seconds")
print("Response:", resp.text)
