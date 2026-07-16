import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
try:
    client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
    response = client.models.generate_content(
        model='gemini-3.5-flash',
        contents='say hello'
    )
    print('API Key test successful with gemini-3.5-flash:', response.text.strip())
except Exception as e:
    print('API Key test FAILED:', str(e))
