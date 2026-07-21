import os
import re
import json
import uuid
import logging
import threading
import pandas as pd
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
from processor import extract_candidate_details

# Filter out repetitive polling logs from terminal output
class NoPollingFilter(logging.Filter):
    def filter(self, record):
        return '/job/' not in record.getMessage()

logging.getLogger('werkzeug').addFilter(NoPollingFilter())

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config["MAX_CONTENT_LENGTH"] = 150 * 1024 * 1024  # 150 MB max
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "recruitment_tracker.csv")
PORT = int(os.environ.get("PORT", 5030))
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"error": "Total folder/files upload size exceeds the 150MB limit."}), 413

# In-memory job store
jobs = {}


def fix_hyperlink_val(val, base_url: str) -> str:
    """Convert any file:/// or old URL in =HYPERLINK("...", "label") to the current web base_url."""
    if not isinstance(val, str) or not val.startswith("=HYPERLINK("):
        return val
    # Extract filename (after last slash or backslash) and label
    m = re.search(r'=HYPERLINK\(".*?[/\\\\]([^/\\\\]+)"\s*,\s*"([^"]+)"\)', val)
    if m:
        filename = m.group(1)
        label = m.group(2)
        return f'=HYPERLINK("{base_url.rstrip("/")}/uploads/{filename}", "{label}")'
    return val


def fix_hyperlinks_in_df(df: pd.DataFrame, base_url: str) -> pd.DataFrame:
    """Replace all attachment HYPERLINK formulas in a DataFrame with the active web base_url."""
    df_copy = df.copy()
    for col in df_copy.columns:
        if any(k in col.lower() for k in ["attachment", "resume", "letter", "marksheet"]):
            df_copy[col] = df_copy[col].apply(lambda v: fix_hyperlink_val(v, base_url))
    return df_copy


def make_excel_link(filename: str, base_url: str = "") -> str:
    """Format a web URL as a clickable Excel HYPERLINK formula."""
    if not filename:
        return ""
    clean_name = os.path.basename(filename)
    if base_url:
        url = f"{base_url.rstrip('/')}/uploads/{clean_name}"
    else:
        url = f"http://localhost:{PORT}/uploads/{clean_name}"
    return f'=HYPERLINK("{url}", "View Document")'


def flatten_candidate(data: dict, serial: int, pdf_path: str, base_url: str = "") -> dict:
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
        "10th Marksheet (attachment)": make_excel_link(data.get("10th", {}).get("marksheet_link", ""), base_url),
        # 12th
        "12th Board": data.get("12th", {}).get("board", ""),
        "12th Passing Year": data.get("12th", {}).get("passing_year", ""),
        "12th Stream": data.get("12th", {}).get("stream", ""),
        "12th Marks": data.get("12th", {}).get("marks", ""),
        "12th Percentage": data.get("12th", {}).get("percentage", ""),
        "12th Marksheet (attachment)": make_excel_link(data.get("12th", {}).get("marksheet_link", ""), base_url),
        # Graduation
        "Graduation University": data.get("graduation", {}).get("university", ""),
        "Graduation Degree": data.get("graduation", {}).get("degree", ""),
        "Graduation Passing Year": data.get("graduation", {}).get("passing_year", ""),
        "Graduation Marks": data.get("graduation", {}).get("marks", ""),
        "Graduation Percentage": data.get("graduation", {}).get("percentage", ""),
        "Graduation Marksheet (attachment)": make_excel_link(data.get("graduation", {}).get("marksheet_link", ""), base_url),
        # Post-Graduation
        "PG University": data.get("post_graduation", {}).get("university", ""),
        "PG Degree": data.get("post_graduation", {}).get("degree", ""),
        "PG Passing Year": data.get("post_graduation", {}).get("passing_year", ""),
        "PG Marks": data.get("post_graduation", {}).get("marks", ""),
        "PG Percentage": data.get("post_graduation", {}).get("percentage", ""),
        "PG Marksheet (attachment)": make_excel_link(data.get("post_graduation", {}).get("marksheet_link", ""), base_url),
        # Experience
        "Total Experience": data.get("experience", {}).get("total_years_months", ""),
        "Experience Letter (attachment)": make_excel_link(data.get("experience", {}).get("experience_letter_link", ""), base_url),
        # Resume
        "Resume (attachment)": make_excel_link(data.get("resume_link", ""), base_url),
    }


def process_job(job_id, save_paths, base_url=""):
    """Background worker: calls Gemini, saves CSV with fresh upload data, updates job status."""
    try:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["message"] = "Gemini AI is analyzing your documents..."

        candidates_list = extract_candidate_details(save_paths)

        results = []
        for raw_data in candidates_list:
            serial = 1 + len(results)
            flat = flatten_candidate(raw_data, serial, "", base_url)
            results.append(flat)

        # Overwrite tracker CSV with freshly extracted upload data only
        if results:
            final_df = pd.DataFrame(results)
            final_df.to_csv(OUTPUT_CSV, index=False)

        jobs[job_id]["status"] = "done"
        jobs[job_id]["results"] = {
            "success": True,
            "extracted": results,
            "errors": [],
            "total_in_tracker": len(results),
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


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    """Serve uploaded documents via web URL."""
    safe_name = os.path.basename(filename)
    file_path = os.path.join(UPLOAD_FOLDER, safe_name)
    if not os.path.isfile(file_path):
        return jsonify({"error": "File not found"}), 404
    return send_file(file_path)


@app.route("/upload", methods=["POST"])
def upload():
    """Accept PDFs, save them, start background job, return job_id immediately."""
    if "files" not in request.files:
        return jsonify({"error": "No files uploaded"}), 400

    files = request.files.getlist("files")
    if not files or files[0].filename == "":
        return jsonify({"error": "No files selected"}), 400

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

    # Get active base_url from request (e.g. https://email-data-parser.onrender.com)
    base_url = request.host_url.rstrip("/")

    # Create job and start background thread
    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {
        "status": "uploading",
        "message": f"Uploading {len(save_paths)} document(s) to Gemini...",
        "results": None,
    }

    thread = threading.Thread(target=process_job, args=(job_id, save_paths, base_url))
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
    """Return all tracker data as JSON, dynamically updating document URLs for current host."""
    if not os.path.isfile(OUTPUT_CSV):
        return jsonify({"data": []})
    df = pd.read_csv(OUTPUT_CSV)
    base_url = request.host_url.rstrip("/")
    df = fix_hyperlinks_in_df(df, base_url)
    return jsonify({"data": df.fillna("").to_dict(orient="records")})


@app.route("/download")
def download_csv():
    """Download the tracker CSV with working web document links for any user."""
    if not os.path.isfile(OUTPUT_CSV):
        return jsonify({"error": "No tracker file yet"}), 404
    df = pd.read_csv(OUTPUT_CSV)
    base_url = request.host_url.rstrip("/")
    df = fix_hyperlinks_in_df(df, base_url)
    df.to_csv(OUTPUT_CSV, index=False)
    return send_file(OUTPUT_CSV, as_attachment=True, download_name="recruitment_tracker.csv")


if __name__ == "__main__":
    app.run(debug=True, port=PORT)
