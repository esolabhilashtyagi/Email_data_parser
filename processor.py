import os
import re
import json
import pdfplumber
from google import genai
from google.genai import types
from dotenv import load_dotenv

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


def pdf_to_text(pdf_path: str) -> str:
    """Extract plain text from a PDF using pdfplumber."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        text = "\n".join(pages).strip()
        fname = os.path.basename(pdf_path)
        print(f"[PDF] '{fname}': extracted {len(text)} chars | preview: {repr(text[:200])}")
        return text
    except Exception as e:
        print(f"[PDF ERROR] {pdf_path}: {e}")
        return ""


PROMPT_TEMPLATE = '''
You are an expert HR recruiter and document parser.
You will receive text extracted from MULTIPLE documents that may belong to MULTIPLE different candidates.
These could be CVs/Resumes, marksheets, experience letters, offer letters, etc.

STEP 1 - IDENTIFY CANDIDATES:
- First, figure out how many DISTINCT candidates are present in the documents.
- Group the documents by candidate. Use names, roll numbers, and content to determine which documents belong to which candidate.
- A candidate's CV/resume, their marksheets, and their experience letters will typically share the same name.

STEP 2 - EXTRACT DATA FOR EACH CANDIDATE:
For each candidate, extract their information into the JSON structure shown below.

RULES FOR MARKS & PERCENTAGES:
1. Search every document for any mention of marks, grades, or percentages for each qualification level.
2. Even if it is just a line in the CV like "M.Com - 67.20%" or "BCA: 64.36%", extract that percentage.
3. For marks, look for patterns like "450/600", "1609/2000", "450 out of 600", or subject-wise tables. Output as "obtained/total".
4. If marks are found but percentage is not written, CALCULATE: (obtained/total)*100 rounded to 2 decimal places, add "%" sign.
5. If CGPA is mentioned (e.g. "8.5 CGPA"), store it in the percentage field as "8.5 CGPA". If a conversion is given (x9.5 or x10), apply it.
6. NEVER leave percentage empty if ANY number like a grade/percent/marks is mentioned for that qualification in any document.
7. For 10th and 12th, look closely at board marksheets. The marks are often in a subject-wise table. Sum the marks if a total is not explicitly provided.

RULES FOR EXPERIENCE:
- Sum only full-time job durations from ALL documents (CV + experience letters) for that candidate.
- Exclude internships unless explicitly labelled as full-time.
- Format: "X years Y months". If fresher/no experience, use "".

RULES FOR PERSONAL DETAILS:
- State: Look at the candidate's address in the CV. Extract just the State name (e.g., "Maharashtra", "Delhi", "Gujarat").
- Gender: If explicitly stated, use it. If not, infer from the name or salutations (Mr./Ms.) if obvious. Otherwise leave blank.
- Date of Birth: Look for "DOB", "Date of Birth", or similar. Extract in the format found.
- Phone & Email: Thoroughly check the header/footer of the CV for contact details.

RULES FOR DOCUMENT LINKS:
- Look at each document header "--- Document: filename.pdf ---".
- For marksheet_link: put the filename of the document that is a marksheet for that level.
- For experience_letter_link: put the filename of the experience letter document.
- For resume_link: put the filename of the CV/Resume document.
- If a single CV contains all data, use that filename for resume_link and leave marksheet_link empty.

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

    for path in pdf_paths:
        fname = os.path.basename(path)
        # 1. Keep text for python fallback
        doc_text = pdf_to_text(path)
        raw_text += f"\n--- Document: {fname} ---\n{doc_text}"
        
        # 2. Upload file to Gemini directly so it can read scanned images/PDFs natively!
        try:
            print(f"[GEMINI] Uploading {fname} for native OCR...")
            g_file = client.files.upload(file=path, config={'display_name': fname})
            uploaded_files.append(g_file)
            contents.append(f"--- Document: {fname} ---")
            contents.append(g_file)
        except Exception as e:
            print(f"[GEMINI ERROR] Failed to upload {fname}: {e}")
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
