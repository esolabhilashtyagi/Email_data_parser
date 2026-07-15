// ============================================
// RecruitAI - Frontend Logic
// ============================================

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const fileList = document.getElementById('fileList');
const fileItems = document.getElementById('fileItems');
const actionBar = document.getElementById('actionBar');
const processingOverlay = document.getElementById('processingOverlay');
const resultsSection = document.getElementById('resultsSection');
const resultsGrid = document.getElementById('resultsGrid');
const resultsSummary = document.getElementById('resultsSummary');
const errorsPanel = document.getElementById('errorsPanel');
const errorsList = document.getElementById('errorsList');
const trackerSection = document.getElementById('trackerSection');

let selectedFiles = [];

// --- Drag & Drop Handlers ---
dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('drag-over');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    handleFiles(e.dataTransfer.files);
});

fileInput.addEventListener('change', (e) => {
    handleFiles(e.target.files);
});

function handleFiles(files) {
    const newFiles = Array.from(files).filter(f => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'));
    
    if (newFiles.length === 0) {
        showToast('Please select valid PDF files only', 'error');
        return;
    }

    selectedFiles = [...selectedFiles, ...newFiles];
    renderFileList();
}

function renderFileList() {
    if (selectedFiles.length === 0) {
        fileList.style.display = 'none';
        actionBar.style.display = 'none';
        return;
    }

    fileList.style.display = 'block';
    actionBar.style.display = 'block';
    fileItems.innerHTML = '';

    selectedFiles.forEach((file, index) => {
        const size = (file.size / (1024 * 1024)).toFixed(2); // MB
        
        const item = document.createElement('div');
        item.className = 'file-item';
        item.innerHTML = `
            <span class="material-icons-round">picture_as_pdf</span>
            <div class="file-item-info">
                <div class="file-item-name">${file.name}</div>
                <div class="file-item-size">${size} MB</div>
            </div>
            <button class="file-item-remove" onclick="removeFile(${index})">
                <span class="material-icons-round">close</span>
            </button>
        `;
        fileItems.appendChild(item);
    });
}

function removeFile(index) {
    selectedFiles.splice(index, 1);
    renderFileList();
}

function clearFiles() {
    selectedFiles = [];
    fileInput.value = '';
    renderFileList();
}

// --- Processing ---
async function processFiles() {
    if (selectedFiles.length === 0) return;

    const formData = new FormData();
    selectedFiles.forEach(file => formData.append('files', file));

    // Show processing state
    processingOverlay.style.display = 'flex';
    resultsSection.style.display = 'none';
    trackerSection.style.display = 'none';
    
    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (response.ok) {
            showToast('Processing complete!', 'success');
            renderResults(data);
            clearFiles(); // Reset upload state
        } else {
            showToast(data.error || 'Upload failed', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showToast('An error occurred during processing', 'error');
    } finally {
        processingOverlay.style.display = 'none';
    }
}

function renderResults(data) {
    resultsSection.style.display = 'block';
    resultsGrid.innerHTML = '';
    
    const count = data.extracted ? data.extracted.length : 0;
    resultsSummary.innerText = `Successfully extracted data for ${count} candidate${count !== 1 ? 's' : ''}. Total in tracker: ${data.total_in_tracker || 0}`;

    if (data.extracted && data.extracted.length > 0) {
        data.extracted.forEach(candidate => {
            const initials = (candidate['Candidate Name'] || '??').substring(0, 2).toUpperCase();
            
            const card = document.createElement('div');
            card.className = 'result-card';
            
            // Build the card HTML based on flattened keys from app.py
            card.innerHTML = `
                <div class="result-card-header">
                    <div class="candidate-avatar">${initials}</div>
                    <div class="candidate-info">
                        <h3>${candidate['Candidate Name'] || 'Unknown'}</h3>
                        <p>${candidate['Candidate Email'] || 'No email'} • ${candidate['Mobile Number'] || 'No phone'}</p>
                    </div>
                </div>
                <div class="result-card-body">
                    <div class="detail-group">
                        <div class="detail-group-title"><span class="material-icons-round" style="font-size:14px">person</span> Basic Info</div>
                        <div class="detail-row"><span class="detail-label">Gender</span><span class="detail-value">${candidate['Gender'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Date of Birth</span><span class="detail-value">${candidate['Date of Birth'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">State</span><span class="detail-value">${candidate['State'] || '-'}</span></div>
                    </div>
                    
                    <div class="detail-group">
                        <div class="detail-group-title"><span class="material-icons-round" style="font-size:14px">school</span> 10th Qualification Details</div>
                        <div class="detail-row"><span class="detail-label">Board Name</span><span class="detail-value">${candidate['10th Board'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Passing Year</span><span class="detail-value">${candidate['10th Passing Year'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Marks</span><span class="detail-value">${candidate['10th Marks'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Percentage</span><span class="detail-value highlight">${candidate['10th Percentage'] ? candidate['10th Percentage'] + '%' : '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">10th Marksheet (Link)</span><span class="detail-value">${candidate['10th Marksheet (attachment)'] || '-'}</span></div>
                    </div>

                    <div class="detail-group">
                        <div class="detail-group-title"><span class="material-icons-round" style="font-size:14px">school</span> 12th Qualification Details</div>
                        <div class="detail-row"><span class="detail-label">Board Name</span><span class="detail-value">${candidate['12th Board'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Subject/Stream</span><span class="detail-value">${candidate['12th Stream'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Passing Year</span><span class="detail-value">${candidate['12th Passing Year'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Marks</span><span class="detail-value">${candidate['12th Marks'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Percentage</span><span class="detail-value highlight">${candidate['12th Percentage'] ? candidate['12th Percentage'] + '%' : '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">12th Marksheet (Link)</span><span class="detail-value">${candidate['12th Marksheet (attachment)'] || '-'}</span></div>
                    </div>

                    <div class="detail-group">
                        <div class="detail-group-title"><span class="material-icons-round" style="font-size:14px">school</span> Graduation Details</div>
                        <div class="detail-row"><span class="detail-label">University/Board Name</span><span class="detail-value">${candidate['Graduation University'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Qualifying Degree</span><span class="detail-value">${candidate['Graduation Degree'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Passing Year</span><span class="detail-value">${candidate['Graduation Passing Year'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Marks</span><span class="detail-value">${candidate['Graduation Marks'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Percentage</span><span class="detail-value highlight">${candidate['Graduation Percentage'] ? candidate['Graduation Percentage'] + '%' : '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Grad. Marksheet (Link)</span><span class="detail-value">${candidate['Graduation Marksheet (attachment)'] || '-'}</span></div>
                    </div>

                    <div class="detail-group">
                        <div class="detail-group-title"><span class="material-icons-round" style="font-size:14px">school</span> Post-Graduation Details</div>
                        <div class="detail-row"><span class="detail-label">University/Board Name</span><span class="detail-value">${candidate['PG University'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Qualifying Degree</span><span class="detail-value">${candidate['PG Degree'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Passing Year</span><span class="detail-value">${candidate['PG Passing Year'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">PG Marks</span><span class="detail-value">${candidate['PG Marks'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">PG Percentage</span><span class="detail-value highlight">${candidate['PG Percentage'] ? candidate['PG Percentage'] + '%' : '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">PG Marksheet (Link)</span><span class="detail-value">${candidate['PG Marksheet (attachment)'] || '-'}</span></div>
                    </div>
                    
                    <div class="detail-group">
                        <div class="detail-group-title"><span class="material-icons-round" style="font-size:14px">work</span> Experience & Resume</div>
                        <div class="detail-row"><span class="detail-label">Total Experience</span><span class="detail-value highlight">${candidate['Total Experience'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Exp. Letter (Link)</span><span class="detail-value">${candidate['Experience Letter (attachment)'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">CV/Resume (Link)</span><span class="detail-value highlight">${candidate['Resume (attachment)'] || '-'}</span></div>
                    </div>
                </div>
            `;
            resultsGrid.appendChild(card);
        });
    }

    // Handle Errors
    if (data.errors && data.errors.length > 0) {
        errorsPanel.style.display = 'block';
        errorsList.innerHTML = data.errors.map(err => 
            `<div class="error-item"><strong>${err.file}</strong>: ${err.error}</div>`
        ).join('');
    } else {
        errorsPanel.style.display = 'none';
    }
}

// --- Tracker ---
async function loadTracker() {
    try {
        const response = await fetch('/tracker');
        const data = await response.json();
        
        if (data.data && data.data.length > 0) {
            renderTrackerTable(data.data);
            resultsSection.style.display = 'none'; // Hide results if showing tracker
        } else {
            showToast('Tracker is currently empty', 'info');
        }
    } catch (error) {
        console.error('Error fetching tracker:', error);
        showToast('Failed to load tracker', 'error');
    }
}

function renderTrackerTable(dataArray) {
    trackerSection.style.display = 'block';
    const thead = document.getElementById('trackerHead');
    const tbody = document.getElementById('trackerBody');
    const summary = document.getElementById('trackerSummary');
    
    thead.innerHTML = '';
    tbody.innerHTML = '';
    summary.innerText = `Showing ${dataArray.length} recorded candidates.`;

    // Extract headers from first object keys
    const headers = Object.keys(dataArray[0]);
    
    // Build Header
    const trHead = document.createElement('tr');
    headers.forEach(h => {
        const th = document.createElement('th');
        th.innerText = h;
        trHead.appendChild(th);
    });
    thead.appendChild(trHead);

    // Build Rows
    dataArray.forEach(row => {
        const tr = document.createElement('tr');
        headers.forEach(h => {
            const td = document.createElement('td');
            td.innerText = row[h] !== null && row[h] !== undefined ? row[h] : '';
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
    
    // Scroll to tracker
    trackerSection.scrollIntoView({ behavior: 'smooth' });
}

function downloadCSV() {
    window.location.href = '/download';
}

// --- Toast Notifications ---
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = 'info';
    if (type === 'success') icon = 'check_circle';
    if (type === 'error') icon = 'error';

    toast.innerHTML = `
        <span class="material-icons-round">${icon}</span>
        <span class="toast-text">${message}</span>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(50px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}
