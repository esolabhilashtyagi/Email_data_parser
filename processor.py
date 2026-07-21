import os
import re
import json
import time
import threading
import pdfplumber
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def image_to_text(image_path: str) -> str:
    """OCR an image using pytesseract if available."""
    if not OCR_AVAILABLE:
        return ""
    try:
        from PIL import Image
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang='eng')
        fname = os.path.basename(image_path)
        print(f"[IMAGE OCR] '{fname}': extracted {len(text)} chars via Tesseract")
        return text.strip()
    except Exception as e:
        print(f"[IMAGE OCR ERROR] {image_path}: {e}")
        return ""


def pdf_to_text(pdf_path: str) -> str:
    """Extract text from PDF or image. Uses pdfplumber for PDFs, falls back to OCR."""
    ext = os.path.splitext(pdf_path.lower())[1]
    if ext in ['.png', '.jpg', '.jpeg', '.webp']:
        return image_to_text(pdf_path)

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


def _process_one_file(path: str):
    """Process a single file locally for maximum speed:
    - If it's an image (.png, .jpg, etc.): send inline bytes as Part.from_bytes.
    - If it's a PDF: extract text via pdfplumber.
      - If text length >= 50: return extracted text (instantaneous & super fast for Gemini!).
      - If text length < 50 (scanned PDF): send inline PDF bytes as Part.from_bytes.
    Returns (fname, is_text, content_item, extracted_text).
    """
    fname = os.path.basename(path)
    ext = os.path.splitext(path.lower())[1]

    # Image files -> inline bytes
    if ext in ['.png', '.jpg', '.jpeg', '.webp']:
        mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}
        mime = mime_map.get(ext, 'image/jpeg')
        try:
            with open(path, 'rb') as f:
                raw_bytes = f.read()
            part = types.Part.from_bytes(data=raw_bytes, mime_type=mime)
            return fname, False, part, ""
        except Exception as e:
            print(f"[IMAGE READ ERROR] {fname}: {e}")
            return fname, True, "", ""

    # PDF files -> try fast local text extraction
    text = ""
    try:
        with pdfplumber.open(path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        text = "\n".join(pages).strip()
    except Exception as e:
        print(f"[PDF EXTRACT ERROR] {fname}: {e}")

    # If digital PDF with text >= 50 chars -> send text
    if len(text) >= 50:
        print(f"[FAST EXTRACT] '{fname}': extracted {len(text)} text chars locally")
        return fname, True, text, text

    # Scanned PDF (text < 50) -> send inline PDF bytes directly to Gemini vision
    print(f"[FAST SCANNED PDF] '{fname}': scanned PDF (<50 text chars), sending inline bytes to Gemini")
    try:
        with open(path, 'rb') as f:
            raw_bytes = f.read()
        part = types.Part.from_bytes(data=raw_bytes, mime_type="application/pdf")
        return fname, False, part, text
    except Exception as e:
        print(f"[PDF READ ERROR] {fname}: {e}")
        return fname, True, text, text


def group_files_by_candidate(pdf_paths: list) -> list:
    """Group file paths by candidate name found in filename or split into small chunks.
    Example filename: '766ed66c_XII_-_pragya_sharma.pdf' -> group key 'pragya_sharma'
    """
    groups = {}
    ungrouped = []

    for path in pdf_paths:
        fname = os.path.basename(path)
        # Check for '_-_' pattern like '766ed66c_XII_-_pragya_sharma.pdf'
        if "_-_" in fname:
            key = fname.rsplit("_-_", 1)[-1].rsplit(".", 1)[0].strip().lower()
            groups.setdefault(key, []).append(path)
        elif " - " in fname:
            key = fname.rsplit(" - ", 1)[-1].rsplit(".", 1)[0].strip().lower()
            groups.setdefault(key, []).append(path)
        else:
            ungrouped.append(path)

    grouped_list = list(groups.values())

    # Chunk any ungrouped files into small batches of max 4 files for fast parallel processing
    if ungrouped:
        chunk_size = 4
        for i in range(0, len(ungrouped), chunk_size):
            grouped_list.append(ungrouped[i:i + chunk_size])

    return grouped_list if grouped_list else [pdf_paths]


def _extract_single_group(pdf_paths: list) -> list:
    """Process a single group of candidate files with Gemini AI."""
    raw_text = ""
    contents = [PROMPT_TEMPLATE]

    # Parallel local prep for this group
    max_workers = min(len(pdf_paths), 8)
    results_map = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_process_one_file, path): path for path in pdf_paths}
        for future in as_completed(futures):
            fname, is_text, content_item, extracted_text = future.result()
            results_map[fname] = (is_text, content_item, extracted_text)

    # Build contents in original order
    for path in pdf_paths:
        fname = os.path.basename(path)
        is_text, content_item, extracted_text = results_map.get(fname, (True, "", ""))
        raw_text += f"\n--- Document: {fname} ---\n{extracted_text}"
        contents.append(f"--- Document: {fname} ---")
        contents.append(content_item)

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=0.0,
            top_p=0.95,
            max_output_tokens=65536,
            response_mime_type="application/json",
        ),
    )

    response_text = response.text.strip()
    print(f"[GEMINI GROUP] Response length: {len(response_text)} chars for {len(pdf_paths)} PDF(s)")

    data = None
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        pass

    if data is None:
        cleaned = re.sub(r"^```(?:json)?\s*", "", response_text, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    if data is None:
        m = re.search(r'(\[.*\]|\{.*\})', response_text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

    if data is None:
        repaired = response_text.rstrip()
        if repaired.startswith('['):
            open_b = repaired.count('{') - repaired.count('}')
            open_a = repaired.count('[') - repaired.count(']')
            repaired += '}' * max(0, open_b)
            repaired += ']' * max(0, open_a)
            try:
                data = json.loads(repaired)
            except json.JSONDecodeError:
                pass

    if data is None:
        print(f"[GEMINI GROUP WARNING] Failed to parse group JSON: {response_text[:300]}")
        return []

    if isinstance(data, dict):
        data = [data]

    # Python fallback per candidate: if AI left marks/percentage empty
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
                        if total <= 0 or total > 2000 or obtained > total or obtained < 10:
                            continue
                        entry["marks"] = f"{m.group(1)}/{m.group(2)}"
                        break
                    if entry.get("marks"):
                        break
            if entry.get("marks") and not entry.get("percentage"):
                entry["percentage"] = calc_percent(entry["marks"])

    return data


def extract_candidate_details(pdf_paths: list) -> list:
    """Full pipeline: PDF list -> parallel candidate batch prep -> Gemini AI -> parsed candidate dicts.
    Runs multiple candidate groups concurrently for 10x-15x faster response times.
    """
    if isinstance(pdf_paths, str):
        pdf_paths = [pdf_paths]

    if not pdf_paths:
        return []

    file_groups = group_files_by_candidate(pdf_paths)

    if len(file_groups) > 1:
        print(f"[PARALLEL AI] Processing {len(pdf_paths)} document(s) across {len(file_groups)} parallel candidate batches...")
        all_candidates = []
        with ThreadPoolExecutor(max_workers=min(len(file_groups), 8)) as group_exec:
            futures = [group_exec.submit(_extract_single_group, group) for group in file_groups]
            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res:
                        all_candidates.extend(res)
                except Exception as e:
                    print(f"[PARALLEL BATCH ERROR]: {e}")
        return all_candidates
    else:
        return _extract_single_group(file_groups[0])


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python processor.py <path-to-pdf>")
        sys.exit(1)
    pdf_file = sys.argv[1]
    if not os.path.isfile(pdf_file):
        print(f"File not found: {pdf_file}")
        sys.exit(1)
    result = extract_candidate_details([pdf_file])
    print("\n=== Extracted Candidate JSON ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
