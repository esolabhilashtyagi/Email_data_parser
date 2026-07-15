# Email Data Parser / Recruitment Tracker

This is an automated recruitment tracker application that uses the Gemini API (via google-genai SDK) to extract structured candidate information from resumes and marksheets. It processes PDFs natively to capture 10th, 12th, Graduation, and Post-Graduation details (including marks and percentages), as well as total experience, and exports the data directly into a CSV format with Excel hyperlinks for attachments.

## Features
- **Batch Document Processing:** Upload multiple documents (Resumes, Marksheets) for a candidate at once.
- **Native AI Parsing:** Uses Gemini's native PDF capabilities to read scanned marksheets and extract precise marks.
- **Smart Logic Fallbacks:** Intelligent keyword scanning ensures no percentage or mark goes missing.
- **Excel-ready CSV:** Output CSV includes clickable hyperlinks connecting each extracted record back to its original uploaded PDF.

## Tech Stack
- **Backend:** Python, Flask
- **AI Processing:** Gemini API (`google-genai` SDK)
- **Frontend:** HTML, Vanilla CSS, JS

## Deployment (Render)
This project is configured for deployment on [Render](https://render.com/).
1. Fork or clone this repository.
2. In Render, create a new Web Service and link this repository.
3. Set the Environment Variable `GEMINI_API_KEY` with your actual API key.
4. Render will automatically use the `requirements.txt` and `Procfile` to deploy the app.
