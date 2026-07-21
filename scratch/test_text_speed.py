import os
import time
import pdfplumber
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

upload_files = [f for f in os.listdir('uploads') if f.endswith('.pdf')][:3]
paths = [os.path.join('uploads', f) for f in upload_files]

# Extract text locally via pdfplumber
t0 = time.time()
text_blocks = []
for p in paths:
    fname = os.path.basename(p)
    with pdfplumber.open(p) as pdf:
        text = "\n".join([page.extract_text() or "" for page in pdf.pages])
    text_blocks.append(f"--- Document: {fname} ---\n{text}")
t1 = time.time()
print(f"[Local pdfplumber Extraction Time] {t1 - t0:.2f} seconds")

# Call model with text
t0 = time.time()
resp = client.models.generate_content(
    model="gemini-3.5-flash",
    contents=["Extract candidate names as JSON list:", "\n".join(text_blocks)],
    config=types.GenerateContentConfig(response_mime_type="application/json")
)
t1 = time.time()
print(f"[Text Prompt Generation Time] {t1 - t0:.2f} seconds")
print("Response:", resp.text)
