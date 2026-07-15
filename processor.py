import os
import re
import json
import pdfplumber
from google import genai
from google.genai import types
from dotenv import load_dotenv

# OCR fallback for scanned PDFs
try:
    from pdf2image import convert_from_path
    import pytesseract
    OCR_AVAILABLE = True
    print("[OCR] pytesseract + pdf2image available")
except ImportError:
    OCR_AVAILABLE = False
    print("[OCR] pytesseract/pdf2image not installed — OCR fallback disabled")

# --------------------------------------------------------------
#  Recruitment PDF extractor - Gemini powered (google-genai SDK)
# --------------------------------------------------------------

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set in .env")

# Create Gemini client
client = genai.Client(api_key=API_KEY)
MODEL_NAME = "gemini-3.5-flash"


def ocr_pdf(pdf_path: str) -> str:
    """OCR a scanned PDF using pdf2image + pytesseract."""
    if not OCR_AVAILABLE:
        return ""
    try:
        images = convert_from_path(pdf_path, dpi=300)
        texts = []
        for i, img in enumerate(images):
            text = pytesseract.image_to_string(img, lang='eng')
            texts.append(text)
        result = "\n".join(texts).strip()
        fname = os.path.basename(pdf_path)
        print(f"[OCR] '{fname}': extracted {len(result)} chars via Tesseract")
        return result
    except Exception as e:
        print(f"[OCR ERROR] {pdf_path}: {e}")
        return ""


def pdf_to_text(pdf_path: str) -> str:
    """Extract text from PDF. Uses pdfplumber first, falls back to OCR for scanned docs."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        text = "\n".join(pages).strip()
        fname = os.path.basename(pdf_path)
        print(f"[PDF] '{fname}': pdfplumber extracted {len(text)} chars")
        
        # If pdfplumber got very little text, try OCR
        if len(text) < 50:
            print(f"[PDF] '{fname}': too little text, trying OCR fallback...")
            ocr_text = ocr_pdf(pdf_path)
            if len(ocr_text) > len(text):
                print(f"[PDF] '{fname}': using OCR result ({len(ocr_text)} chars)")
                return ocr_text
        
        return text
    except Exception as e:
        print(f"[PDF ERROR] {pdf_path}: {e}")
        # Try OCR as last resort
        return ocr_pdf(pdf_path)


PROMPT_TEMPLATE = '''
You are an expert HR recruiter and document parser with OCR expertise.
You will receive MULTIPLE documents (PDFs with images/scans) that may belong to MULTIPLE different candidates.
These include CVs/Resumes, marksheets (scanned images), experience letters, offer letters, degree certificates, etc.

CRITICAL: Many documents are SCANNED IMAGES of marksheets. You MUST carefully OCR and read every single page of every document. Do NOT skip any document.

STEP 1 - READ EVERY DOCUMENT CAREFULLY:
- Open and read EVERY attached PDF thoroughly, even if it is a scanned image.
- For marksheets: Read the subject-wise marks table, the total marks, the percentage, the board name, the passing year, and the student name.
- For CVs/Resumes: Read every section including education, experience, contact details, personal info.
- For experience/offer letters: Read the candidate name, company, dates, role.

STEP 2 - IDENTIFY CANDIDATES:
- Figure out how many DISTINCT candidates are present across all documents.
- Group documents by candidate using names visible in the documents.

STEP 3 - EXTRACT DATA FOR EACH CANDIDATE:
For each candidate, extract their information into the JSON structure shown below.

CRITICAL RULES FOR MARKS & PERCENTAGES (MUST FOLLOW):
1. EVERY marksheet PDF contains marks. You MUST read the scanned image carefully and extract them.
2. For Indian board marksheets (CBSE, ICSE, UP Board, MP Board, Bihar Board, etc.):
   - Look for a table with subject names and marks columns
   - Find "Total Marks" or "Grand Total" row. If not present, SUM all subject marks yourself.
   - Find "Maximum Marks" (usually 500 for 5 subjects, 600 for 6 subjects, etc.)
   - Output marks as "obtained/total" (e.g., "425/500", "1609/2000")
3. For university marksheets/grade cards:
   - Look for SGPA, CGPA, total marks, or percentage printed on the document
   - If CGPA is given, store as "8.5 CGPA" in percentage field
4. If marks are found but percentage is NOT explicitly written, CALCULATE IT: (obtained/total)*100, round to 2 decimals.
5. Also check the CV/Resume — it often lists percentages like "10th - 82.4%", "B.Tech - 8.2 CGPA", "12th - 78%"
6. NEVER leave marks AND percentage BOTH empty if a marksheet PDF exists for that level. Extract SOMETHING.
7. If you truly cannot read the marksheet at all, put "Unable to read" in the marks field.

RULES FOR EXPERIENCE:
- Sum only full-time job durations from ALL documents (CV + experience letters) for that candidate.
- Exclude internships unless explicitly labelled as full-time.
- Format: "X years Y months". If fresher/no experience, use "".

RULES FOR PERSONAL DETAILS:
- State: Look at the candidate's address in the CV. Extract just the State name (e.g., "Maharashtra", "Delhi", "Gujarat").
- Gender: If explicitly stated, use it. If not, infer from name or salutations (Mr./Ms.) if obvious. Otherwise leave blank.
- Date of Birth: Look for "DOB", "Date of Birth", or similar. Also check marksheets — Indian marksheets often show DOB.
- Phone & Email: Thoroughly check the header/footer of the CV and also marksheets for contact details.

RULES FOR DOCUMENT LINKS:
- Look at each document header "--- Document: filename.pdf ---".
- For marksheet_link: put the filename of the document that is a marksheet for that level.
- For experience_letter_link: put the filename of the experience letter/offer letter document.
- For resume_link: put the filename of the CV/Resume document.

Return ONLY a valid JSON ARRAY, even if there is only one candidate. No markdown, no explanation, no extra text.

[
  {
    "candidate_name": "",
    "candidate_email": "",
    "date_of_birth": "",
    "mobile_number": "",
    "gender": "",
    "state": "",
    "10th": {
      "board": "",
      "passing_year": "",
      "marks": "",
      "percentage": "",
      "marksheet_link": ""
    },
    "12th": {
      "board": "",
      "passing_year": "",
      "stream": "",
      "marks": "",
      "percentage": "",
      "marksheet_link": ""
    },
    "graduation": {
      "university": "",
      "degree": "",
      "passing_year": "",
      "marks": "",
      "percentage": "",
      "marksheet_link": ""
    },
    "post_graduation": {
      "university": "",
      "degree": "",
      "passing_year": "",
      "marks": "",
      "percentage": "",
      "marksheet_link": ""
    },
    "experience": {
      "total_years_months": "",
      "experience_letter_link": ""
    },
    "resume_link": ""
  }
]

--- CANDIDATE DOCUMENTS START BELOW ---
'''


def calc_percent(s: str) -> str:
    """Detect patterns like 85/100 or 85 out of 100 and return percentage."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:/|out\s+of)\s*(\d+(?:\.\d+)?)", s, re.I)
    if not m:
        return ""
    try:
        return f"{(float(m.group(1)) / float(m.group(2)) * 100):.2f}"
    except Exception:
        return ""


def extract_candidate_details(pdf_paths: list) -> list:
    """Full pipeline: PDF list -> combined text -> Gemini -> list of parsed candidate dicts."""
    raw_text = ""
    contents = [PROMPT_TEMPLATE]
    uploaded_files = []

    import time

    for path in pdf_paths:
        fname = os.path.basename(path)
        # 1. Keep text for python fallback
        doc_text = pdf_to_text(path)
        raw_text += f"\n--- Document: {fname} ---\n{doc_text}"
        
        # 2. Upload file to Gemini directly so it can read scanned images/PDFs natively!
        try:
            print(f"[GEMINI] Uploading {fname} for native OCR...")
            g_file = client.files.upload(file=path, config={'display_name': fname})
            
            # Wait for file to be processed (Active)
            print(f"[GEMINI] Waiting for {fname} to be processed by File API...")
            while True:
                file_status = client.files.get(name=g_file.name)
                state_str = str(file_status.state)
                # State can be 'State.ACTIVE', 'State.PROCESSING', 'ACTIVE', etc.
                if "ACTIVE" in state_str:
                    print(f"[GEMINI] {fname} is ACTIVE.")
                    break
                elif "FAILED" in state_str:
                    raise RuntimeError(f"Gemini file processing failed for {fname}")
                else:
                    print(f"[GEMINI] {fname} state: {state_str}. Waiting 2s...")
                    time.sleep(2)
            
            uploaded_files.append(g_file)
            contents.append(f"--- Document: {fname} ---")
            contents.append(g_file)
        except Exception as e:
            print(f"[GEMINI ERROR] Failed to upload/process {fname}: {e}")
            contents.append(f"--- Document: {fname} ---\n{doc_text}")

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.0,
                top_p=1,
                max_output_tokens=16384,
            ),
        )
    finally:
        for f in uploaded_files:
            try:
                client.files.delete(name=f.name)
            except Exception as e:
                print(f"[GEMINI WARNING] Could not delete {f.name}: {e}")

    response_text = response.text.strip()
    response_text = re.sub(r"^```json\s*", "", response_text, flags=re.I)
    response_text = re.sub(r"\s*```$", "", response_text)
    try:
        data = json.loads(response_text)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to parse Gemini JSON.\nRaw output:\n{response.text}"
        ) from exc

    # Ensure we always have a list
    if isinstance(data, dict):
        data = [data]

    print(f"[GEMINI] Identified {len(data)} candidate(s) from {len(pdf_paths)} PDF(s)")

    # -------------------------------------------------------
    # Python fallback per candidate: if AI left marks/percentage
    # empty, try to find patterns in the raw PDF text
    # -------------------------------------------------------
    LEVEL_KEYWORDS = {
        "10th":            ["10th", "matriculat", "secondary", "ssc", "class x", "class 10", "x board"],
        "12th":            ["12th", "intermediate", "higher secondary", "hsc", "class xii", "class 12", "xii board"],
        "graduation":      ["bachelor", "b.tech", "b.sc", "b.com", "b.a.", "graduation", "undergrad", "bca", "bba"],
        "post_graduation": ["master", "m.tech", "m.sc", "m.com", "m.a.", "mba", "mca", "post graduation", "post-graduation", "postgrad", "pg semester"],
    }
    for candidate in data:
        for level, keywords in LEVEL_KEYWORDS.items():
            if level not in candidate:
                continue
            entry = candidate[level]
            if not entry.get("marks"):
                for kw in keywords:
                    idx = raw_text.lower().find(kw.lower())
                    if idx == -1:
                        continue
                    snippet = raw_text[max(0, idx - 100):idx + 1500]
                    for m in re.finditer(
                        r"(\d{1,4}(?:\.\d+)?)\s*(?:/|out\s+of)\s*(\d{1,4}(?:\.\d+)?)",
                        snippet, re.I
                    ):
                        obtained = float(m.group(1))
                        total = float(m.group(2))
                        if total <= 0 or total > 2000:
                            continue
                        if obtained > total:
                            continue
                        if obtained < 10:
                            continue
                        entry["marks"] = f"{m.group(1)}/{m.group(2)}"
                        print(f"[FALLBACK] {candidate.get('candidate_name','')} {level} marks via '{kw}': {entry['marks']}")
                        break
                    if entry.get("marks"):
                        break
            if entry.get("marks") and not entry.get("percentage"):
                entry["percentage"] = calc_percent(entry["marks"])
                print(f"[FALLBACK] {candidate.get('candidate_name','')} {level} pct computed: {entry['percentage']}")

    return data


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python processor.py <path-to-pdf>")
        sys.exit(1)
    pdf_file = sys.argv[1]
    if not os.path.isfile(pdf_file):
        print(f"File not found: {pdf_file}")
        sys.exit(1)
    result = extract_candidate_details(pdf_file)
    print("\n=== Extracted Candidate JSON ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
