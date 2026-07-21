import os
import json
import pandas as pd
from processor import extract_candidate_details

# --------------------------------------------------------------
#  Batch processor - processes all PDFs in a folder
#  and writes results to a CSV tracker
# --------------------------------------------------------------

INPUT_DIR = os.path.join(os.path.dirname(__file__), "input_pdfs")
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "recruitment_tracker.csv")


def flatten_candidate(data: dict, serial: int, pdf_path: str) -> dict:
    """Flatten nested dict into a single-level row for the CSV tracker."""
    row = {
        "Serial Number": serial,
        "Candidate Name": data.get("candidate_name", ""),
        "Candidate Email": data.get("candidate_email", ""),
        "Date of Birth": data.get("date_of_birth", ""),
        "Mobile Number": data.get("mobile_number", ""),
        "Gender": data.get("gender", ""),
        "State": data.get("state", ""),
        # 10th
        "10th Board": data.get("10th", {}).get("board", ""),
        "10th Passing Year": data.get("10th", {}).get("passing_year", ""),
        "10th Percentage": data.get("10th", {}).get("percentage", ""),
        "10th Marksheet Link": "",
        # 12th
        "12th Board": data.get("12th", {}).get("board", ""),
        "12th Passing Year": data.get("12th", {}).get("passing_year", ""),
        "12th Stream": data.get("12th", {}).get("stream", ""),
        "12th Percentage": data.get("12th", {}).get("percentage", ""),
        "12th Marksheet Link": "",
        # Graduation
        "Graduation University": data.get("graduation", {}).get("university", ""),
        "Graduation Degree": data.get("graduation", {}).get("degree", ""),
        "Graduation Passing Year": data.get("graduation", {}).get("passing_year", ""),
        "Graduation Percentage": data.get("graduation", {}).get("percentage", ""),
        "Graduation Marksheet Link": "",
        # Post-Graduation
        "PG University": data.get("post_graduation", {}).get("university", ""),
        "PG Degree": data.get("post_graduation", {}).get("degree", ""),
        "PG Passing Year": data.get("post_graduation", {}).get("passing_year", ""),
        "PG Percentage": data.get("post_graduation", {}).get("percentage", ""),
        "PG Marksheet Link": "",
        # Experience
        "Total Experience": data.get("experience", {}).get("total_years_months", ""),
        "Experience Letter Link": data.get("experience", {}).get("experience_letter_link", ""),
        # Resume
        "Resume Link": os.path.abspath(pdf_path),
    }
    return row


def run_batch():
    """Process every PDF in input_pdfs/ and append rows to the tracker CSV."""
    os.makedirs(INPUT_DIR, exist_ok=True)

    pdf_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(".pdf")]
    if not pdf_files:
        print(f"No PDF files found in {INPUT_DIR}")
        print("Place your resume/marksheet PDFs in the input_pdfs/ folder and run again.")
        return

    # Determine starting serial number
    if os.path.isfile(OUTPUT_CSV):
        existing = pd.read_csv(OUTPUT_CSV)
        start_serial = len(existing) + 1
    else:
        existing = None
        start_serial = 1

    rows = []
    for i, pdf_name in enumerate(pdf_files):
        pdf_path = os.path.join(INPUT_DIR, pdf_name)
        serial = start_serial + i
        print(f"\n[{serial}] Processing: {pdf_name} ...")
        try:
            candidates_list = extract_candidate_details([pdf_path])
            for raw_data in candidates_list:
                row = flatten_candidate(raw_data, serial, pdf_path)
                rows.append(row)
                print(f"    -> Extracted: {row['Candidate Name']} | {row['Candidate Email']}")
        except Exception as e:
            print(f"    -> ERROR processing {pdf_name}: {e}")

    if not rows:
        print("\nNo candidates extracted.")
        return

    new_df = pd.DataFrame(rows)
    if existing is not None:
        final_df = pd.concat([existing, new_df], ignore_index=True)
    else:
        final_df = new_df

    final_df.to_csv(OUTPUT_CSV, index=False)
    print(f"\n{'='*60}")
    print(f"Tracker updated: {OUTPUT_CSV}")
    print(f"Total candidates in tracker: {len(final_df)}")
    print(f"{'='*60}")

    # Also print the JSON for the newly processed candidates
    print("\n=== Newly Extracted Records (JSON) ===")
    print(json.dumps(rows, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run_batch()
