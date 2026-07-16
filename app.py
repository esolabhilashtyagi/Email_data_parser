import os
import json
import uuid
import threading
import pandas as pd
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from processor import extract_candidate_details

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB max
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "recruitment_tracker.csv")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# In-memory job store
jobs = {}


def make_excel_link(filename: str) -> str:
    """Format a local file path as a clickable Excel HYPERLINK formula."""
    if not filename:
        return ""
    abs_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, filename)).replace("\\", "/")
    return f'=HYPERLINK("file:///{abs_path}", "View Document")'


def flatten_candidate(data: dict, serial: int, pdf_path: str) -> dict:
    """Flatten nested dict into a single-level row for the CSV tracker."""
    return {
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
        "10th Marks": data.get("10th", {}).get("marks", ""),
        "10th Percentage": data.get("10th", {}).get("percentage", ""),
        "10th Marksheet (attachment)": make_excel_link(data.get("10th", {}).get("marksheet_link", "")),
        # 12th
        "12th Board": data.get("12th", {}).get("board", ""),
        "12th Passing Year": data.get("12th", {}).get("passing_year", ""),
        "12th Stream": data.get("12th", {}).get("stream", ""),
        "12th Marks": data.get("12th", {}).get("marks", ""),
        "12th Percentage": data.get("12th", {}).get("percentage", ""),
        "12th Marksheet (attachment)": make_excel_link(data.get("12th", {}).get("marksheet_link", "")),
        # Graduation
        "Graduation University": data.get("graduation", {}).get("university", ""),
        "Graduation Degree": data.get("graduation", {}).get("degree", ""),
        "Graduation Passing Year": data.get("graduation", {}).get("passing_year", ""),
        "Graduation Marks": data.get("graduation", {}).get("marks", ""),
        "Graduation Percentage": data.get("graduation", {}).get("percentage", ""),
        "Graduation Marksheet (attachment)": make_excel_link(data.get("graduation", {}).get("marksheet_link", "")),
        # Post-Graduation
        "PG University": data.get("post_graduation", {}).get("university", ""),
        "PG Degree": data.get("post_graduation", {}).get("degree", ""),
        "PG Passing Year": data.get("post_graduation", {}).get("passing_year", ""),
        "PG Marks": data.get("post_graduation", {}).get("marks", ""),
        "PG Percentage": data.get("post_graduation", {}).get("percentage", ""),
        "PG Marksheet (attachment)": make_excel_link(data.get("post_graduation", {}).get("marksheet_link", "")),
        # Experience
        "Total Experience": data.get("experience", {}).get("total_years_months", ""),
        "Experience Letter (attachment)": make_excel_link(data.get("experience", {}).get("experience_letter_link", "")),
        # Resume
        "Resume (attachment)": make_excel_link(data.get("resume_link", "")),
    }


def process_job(job_id, save_paths, start_serial, existing):
    """Background worker: calls Gemini, saves CSV, updates job status."""
    try:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["message"] = "Gemini AI is analyzing your documents..."

        candidates_list = extract_candidate_details(save_paths)

        results = []
        for raw_data in candidates_list:
            serial = start_serial + len(results)
            flat = flatten_candidate(raw_data, serial, "")
            results.append(flat)

        # Append to tracker CSV
        if results:
            new_df = pd.DataFrame(results)
            if existing is not None:
                final_df = pd.concat([existing, new_df], ignore_index=True)
            else:
                final_df = new_df
            final_df.to_csv(OUTPUT_CSV, index=False)

        jobs[job_id]["status"] = "done"
        jobs[job_id]["results"] = {
            "success": True,
            "extracted": results,
            "errors": [],
            "total_in_tracker": (len(existing) if existing is not None else 0) + len(results),
        }
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["results"] = {
            "success": False,
            "extracted": [],
            "errors": [{"file": "Batch Processing", "error": str(e)}],
            "total_in_tracker": 0,
        }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    """Accept PDFs, save them, start background job, return job_id immediately."""
    if "files" not in request.files:
        return jsonify({"error": "No files uploaded"}), 400

    files = request.files.getlist("files")
    if not files or files[0].filename == "":
        return jsonify({"error": "No files selected"}), 400

    # Determine starting serial number
    if os.path.isfile(OUTPUT_CSV):
        existing = pd.read_csv(OUTPUT_CSV)
        start_serial = len(existing) + 1
    else:
        existing = None
        start_serial = 1

    errors = []
    save_paths = []
    ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.webp'}
    for file in files:
        ext = os.path.splitext(file.filename.lower())[1]
        if ext not in ALLOWED_EXTENSIONS:
            errors.append({"file": file.filename, "error": "Unsupported file format. Supported: PDF, PNG, JPG, JPEG, WEBP"})
            continue
        safe_name = f"{uuid.uuid4().hex[:8]}_{secure_filename(file.filename)}"
        save_path = os.path.join(UPLOAD_FOLDER, safe_name)
        file.save(save_path)
        save_paths.append(save_path)

    if not save_paths:
        return jsonify({"error": "No valid files uploaded", "errors": errors}), 400

    # Create job and start background thread
    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {
        "status": "uploading",
        "message": f"Uploading {len(save_paths)} document(s) to Gemini...",
        "results": None,
    }

    thread = threading.Thread(target=process_job, args=(job_id, save_paths, start_serial, existing))
    thread.daemon = True
    thread.start()

    # Return immediately with job_id — frontend will poll /job/<id>
    return jsonify({"job_id": job_id, "file_count": len(save_paths)})


@app.route("/job/<job_id>")
def job_status(job_id):
    """Poll endpoint: returns job status and results when done."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job["status"] in ("done", "error"):
        # Clean up job from memory after delivering results
        results = job["results"]
        del jobs[job_id]
        return jsonify({"status": job["status"], **results})

    return jsonify({"status": job["status"], "message": job.get("message", "Processing...")})


@app.route("/tracker")
def get_tracker():
    """Return all tracker data as JSON."""
    if not os.path.isfile(OUTPUT_CSV):
        return jsonify({"data": []})
    df = pd.read_csv(OUTPUT_CSV)
    return jsonify({"data": df.fillna("").to_dict(orient="records")})


@app.route("/download")
def download_csv():
    """Download the tracker CSV."""
    if not os.path.isfile(OUTPUT_CSV):
        return jsonify({"error": "No tracker file yet"}), 404
    return send_file(OUTPUT_CSV, as_attachment=True, download_name="recruitment_tracker.csv")


if __name__ == "__main__":
    app.run(debug=True, port=5030)
