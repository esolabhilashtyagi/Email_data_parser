// ============================================
// RecruitAI - Frontend Logic (Multi-Candidate)
// ============================================

const actionBar = document.getElementById('actionBar');
const processingOverlay = document.getElementById('processingOverlay');
const resultsSection = document.getElementById('resultsSection');
const resultsGrid = document.getElementById('resultsGrid');
const resultsSummary = document.getElementById('resultsSummary');
const errorsPanel = document.getElementById('errorsPanel');
const errorsList = document.getElementById('errorsList');
const trackerSection = document.getElementById('trackerSection');

// Each entry: { name: 'Candidate 1', files: [File, File, ...] }
let candidates = [];

// ---- Candidate Slot Management ----

function addCandidateSlot() {
    const index = candidates.length;
    candidates.push({ name: `Candidate ${index + 1}`, files: [] });
    renderCandidateQueue();
    document.getElementById('actionBar').style.display = 'block';
}

function removeCandidateSlot(index) {
    candidates.splice(index, 1);
    renderCandidateQueue();
    if (candidates.length === 0) {
        document.getElementById('actionBar').style.display = 'none';
    }
}

function handleCandidateFiles(index, filesInput) {
    const newFiles = Array.from(filesInput).filter(f => f.name.toLowerCase().endsWith('.pdf'));
    candidates[index].files = [...candidates[index].files, ...newFiles];
    renderCandidateQueue();
}

function removeCandidateFile(candidateIndex, fileIndex) {
    candidates[candidateIndex].files.splice(fileIndex, 1);
    renderCandidateQueue();
}

function renderCandidateQueue() {
    const queue = document.getElementById('candidateQueue');
    queue.innerHTML = '';

    candidates.forEach((candidate, cIdx) => {
        const card = document.createElement('div');
        card.className = 'candidate-slot';
        card.innerHTML = `
            <div class="candidate-slot-header">
                <span class="material-icons-round">person</span>
                <input class="candidate-name-input" type="text" value="${candidate.name}"
                    onchange="candidates[${cIdx}].name = this.value"
                    placeholder="Candidate Name (optional)" />
                <button class="btn btn-sm btn-danger" onclick="removeCandidateSlot(${cIdx})">
                    <span class="material-icons-round">delete</span>
                </button>
            </div>
            <div class="candidate-drop-zone" id="dropZone-${cIdx}"
                onclick="document.getElementById('fileInput-${cIdx}').click()"
                ondragover="event.preventDefault(); this.classList.add('drag-over')"
                ondragleave="this.classList.remove('drag-over')"
                ondrop="this.classList.remove('drag-over'); handleCandidateFiles(${cIdx}, event.dataTransfer.files)">
                <span class="material-icons-round">cloud_upload</span>
                <span>Drop PDFs here or click to browse</span>
                <input type="file" id="fileInput-${cIdx}" multiple accept=".pdf" hidden
                    onchange="handleCandidateFiles(${cIdx}, this.files)">
            </div>
            <div class="candidate-file-list" id="fileList-${cIdx}">
                ${candidate.files.map((f, fIdx) => `
                    <div class="file-item">
                        <span class="material-icons-round">picture_as_pdf</span>
                        <div class="file-item-info">
                            <div class="file-item-name">${f.name}</div>
                            <div class="file-item-size">${(f.size/1024/1024).toFixed(2)} MB</div>
                        </div>
                        <button class="file-item-remove" onclick="removeCandidateFile(${cIdx}, ${fIdx})">
                            <span class="material-icons-round">close</span>
                        </button>
                    </div>
                `).join('')}
            </div>
        `;
        queue.appendChild(card);
    });
}

// ---- Process All Candidates ----

async function processAllCandidates() {
    const validCandidates = candidates.filter(c => c.files.length > 0);
    if (validCandidates.length === 0) {
        showToast('Please add files for at least one candidate', 'error');
        return;
    }

    processingOverlay.style.display = 'flex';
    resultsSection.style.display = 'none';
    trackerSection.style.display = 'none';

    const allResults = [];
    const allErrors = [];

    for (let i = 0; i < validCandidates.length; i++) {
        const candidate = validCandidates[i];
        const statusEl = document.getElementById('processingStatus');
        if (statusEl) statusEl.textContent = `Processing ${candidate.name} (${i + 1} of ${validCandidates.length})...`;

        const progressEl = document.getElementById('progressFill');
        if (progressEl) progressEl.style.width = `${Math.round(((i) / validCandidates.length) * 100)}%`;

        const formData = new FormData();
        candidate.files.forEach(f => formData.append('files', f));

        try {
            const response = await fetch('/upload', { method: 'POST', body: formData });
            const data = await response.json();
            if (response.ok) {
                allResults.push(...(data.extracted || []));
                allErrors.push(...(data.errors || []));
            } else {
                allErrors.push({ file: candidate.name, error: data.error || 'Upload failed' });
            }
        } catch (err) {
            allErrors.push({ file: candidate.name, error: `Network error: ${err.message}` });
        }
    }

    if (document.getElementById('progressFill'))
        document.getElementById('progressFill').style.width = '100%';

    processingOverlay.style.display = 'none';
    showToast(`Done! ${allResults.length} candidate(s) processed.`, 'success');
    renderResults({ extracted: allResults, errors: allErrors, total_in_tracker: allResults.length });

    // Reset
    candidates = [];
    renderCandidateQueue();
    document.getElementById('actionBar').style.display = 'none';
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
