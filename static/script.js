const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const folderInput = document.getElementById('folderInput');
const btnSelectFiles = document.getElementById('btnSelectFiles');
const btnSelectFolder = document.getElementById('btnSelectFolder');
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

const isFolderSelectionSupported = (() => {
    const input = document.createElement('input');
    return 'webkitdirectory' in input || 'directory' in input || 'mozdirectory' in input;
})();

if (!isFolderSelectionSupported && btnSelectFolder) {
    btnSelectFolder.disabled = true;
    btnSelectFolder.title = 'Folder selection is supported only in Chrome/Edge.';
}

let selectedFiles = [];

const ALLOWED_EXTS = ['.pdf', '.png', '.jpg', '.jpeg', '.webp'];

function isSupportedFile(file) {
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    return ALLOWED_EXTS.includes(ext);
}

// Recursive directory traversal for drag & drop
async function traverseFileTree(item, path = "") {
    if (item.isFile) {
        const file = await new Promise((resolve) => item.file(resolve));
        return [file];
    } else if (item.isDirectory) {
        const dirReader = item.createReader();
        const entries = await new Promise((resolve) => {
            const allEntries = [];
            function readAll() {
                dirReader.readEntries((results) => {
                    if (results.length === 0) {
                        resolve(allEntries);
                    } else {
                        allEntries.push(...results);
                        readAll();
                    }
                }, () => resolve(allEntries));
            }
            readAll();
        });
        
        const filePromises = entries.map(entry => traverseFileTree(entry, path + item.name + "/"));
        const filesArrays = await Promise.all(filePromises);
        return filesArrays.flat();
    }
    return [];
}

// ---- Button Click Handlers ----

// "Select Files" button
btnSelectFiles.addEventListener('click', (e) => {
    e.stopPropagation();
    const tempInput = document.createElement('input');
    tempInput.type = 'file';
    tempInput.multiple = true;
    tempInput.accept = '.pdf,.png,.jpg,.jpeg,.webp';
    tempInput.style.display = 'none';
    
    tempInput.addEventListener('change', () => {
        const files = Array.from(tempInput.files).filter(isSupportedFile);
        addFiles(files);
        tempInput.remove();
    });
    
    document.body.appendChild(tempInput);
    tempInput.click();
});

// "Select Folder" button
btnSelectFolder.addEventListener('click', (e) => {
    e.stopPropagation();
    if (!isFolderSelectionSupported) {
        showToast('Folder selection is supported only in Chrome/Edge. Please use a supported browser or drag and drop a folder.', 'error');
        return;
    }
    const tempInput = document.createElement('input');
    tempInput.type = 'file';
    tempInput.setAttribute('webkitdirectory', '');
    tempInput.setAttribute('directory', '');
    tempInput.style.display = 'none';
    
    tempInput.addEventListener('change', () => {
        const files = Array.from(tempInput.files).filter(isSupportedFile);
        addFiles(files);
        tempInput.remove();
    });
    
    document.body.appendChild(tempInput);
    tempInput.click();
});

// Drop zone click opens file picker (only if not clicking a button)
dropZone.addEventListener('click', (e) => {
    if (e.target.closest('button')) return; // let buttons handle themselves
    fileInput.click();
});

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('drag-over');
});

dropZone.addEventListener('drop', async (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    
    const items = Array.from(e.dataTransfer.items || []);
    if (items.length > 0 && items[0].webkitGetAsEntry) {
        const entries = items.map(item => item.webkitGetAsEntry()).filter(Boolean);
        const filesPromises = entries.map(entry => traverseFileTree(entry));
        const filesArrays = await Promise.all(filesPromises);
        const allFiles = filesArrays.flat().filter(isSupportedFile);
        addFiles(allFiles);
    } else {
        const files = Array.from(e.dataTransfer.files).filter(isSupportedFile);
        addFiles(files);
    }
});

fileInput.addEventListener('change', () => {
    const files = Array.from(fileInput.files).filter(isSupportedFile);
    addFiles(files);
    fileInput.value = ''; // reset so same file can be re-added
});

folderInput.addEventListener('change', () => {
    const files = Array.from(folderInput.files).filter(isSupportedFile);
    addFiles(files);
    folderInput.value = ''; // reset
});

// ---- File Management ----

function getFileKey(file) {
    return file.webkitRelativePath || `${file.name}-${file.size}-${file.lastModified}`;
}

function addFiles(newFiles) {
    // Avoid duplicates by full path/identity
    newFiles.forEach(f => {
        if (!selectedFiles.find(sf => getFileKey(sf) === getFileKey(f))) {
            selectedFiles.push(f);
        }
    });
    renderFileList();
}

function removeFile(index) {
    selectedFiles.splice(index, 1);
    renderFileList();
}

function clearFiles() {
    selectedFiles = [];
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

    fileItems.innerHTML = selectedFiles.map((f, i) => {
        const displayName = f.webkitRelativePath || f.name;
        const ext = '.' + f.name.split('.').pop().toLowerCase();
        const icon = ext === '.pdf' ? 'picture_as_pdf' : 'image';
        return `
        <div class="file-item">
            <span class="material-icons-round">${icon}</span>
            <div class="file-item-info">
                <div class="file-item-name">${displayName}</div>
                <div class="file-item-size">${(f.size / 1024 / 1024).toFixed(2)} MB</div>
            </div>
            <button class="file-item-remove" onclick="removeFile(${i})">
                <span class="material-icons-round">close</span>
            </button>
        </div>
        `;
    }).join('');
}

// ---- Process Files ----
// Upload files → get job_id → poll /job/<id> until done.
// This avoids Render's 30-second request timeout.

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function processFiles() {
    if (selectedFiles.length === 0) {
        showToast('Please select at least one supported file (PDF or Image)', 'error');
        return;
    }

    processingOverlay.style.display = 'flex';
    resultsSection.style.display = 'none';
    trackerSection.style.display = 'none';
    errorsPanel.style.display = 'none';

    const statusEl = document.getElementById('processingStatus');
    const progressEl = document.getElementById('progressFill');

    if (statusEl) statusEl.textContent = `Uploading ${selectedFiles.length} file(s)...`;
    if (progressEl) progressEl.style.width = '10%';

    const formData = new FormData();
    selectedFiles.forEach(f => formData.append('files', f));

    let allResults = [];
    let allErrors = [];

    try {
        // Step 1: Upload files and get job_id (returns instantly)
        const uploadResp = await fetch('/upload', { method: 'POST', body: formData });
        const uploadData = await uploadResp.json();

        if (!uploadResp.ok || !uploadData.job_id) {
            allErrors.push({ file: 'Upload', error: uploadData.error || 'Upload failed' });
            throw new Error('Upload failed');
        }

        const jobId = uploadData.job_id;
        if (statusEl) statusEl.textContent = `Gemini AI is analyzing ${uploadData.file_count} document(s)...`;
        if (progressEl) progressEl.style.width = '30%';

        // Step 2: Poll until done — no timeout, wait as long as it takes
        let attempts = 0;
        const startTime = Date.now();

        while (true) {
            await sleep(2000);
            attempts++;

            // Animate progress bar (30% → 88%, slows down over time)
            const progress = 30 + Math.min(58, attempts * 0.5);
            if (progressEl) progressEl.style.width = `${progress}%`;

            if (statusEl) {
                const elapsed = Math.floor((Date.now() - startTime) / 1000);
                const mins = Math.floor(elapsed / 60);
                const secs = elapsed % 60;
                const timeStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
                const dots = '.'.repeat((attempts % 3) + 1);
                statusEl.textContent = `Gemini AI analyzing documents${dots} (${timeStr} elapsed)`;
            }

            try {
                const pollResp = await fetch(`/job/${jobId}`);
                const pollData = await pollResp.json();

                if (pollData.status === 'done') {
                    allResults = pollData.extracted || [];
                    allErrors = pollData.errors || [];
                    break;
                } else if (pollData.status === 'error') {
                    allErrors = pollData.errors || [{ file: 'Processing', error: 'Unknown error' }];
                    break;
                }
                // else: still processing, keep polling
            } catch (pollErr) {
                // Network blip — retry silently
                console.warn('Poll error, retrying...', pollErr);
            }
        }

    } catch (err) {
        if (allErrors.length === 0) {
            allErrors.push({ file: 'Processing', error: `Error: ${err.message}` });
        }
    }

    if (progressEl) progressEl.style.width = '100%';

    processingOverlay.style.display = 'none';
    showToast(`Done! ${allResults.length} candidate(s) extracted from ${selectedFiles.length} files.`, 'success');
    renderResults({ extracted: allResults, errors: allErrors, total_in_tracker: allResults.length });

    // Reset
    selectedFiles = [];
    renderFileList();
}



// ---- Render Results ----

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
                        <div class="detail-group-title"><span class="material-icons-round" style="font-size:14px">school</span> 10th Details</div>
                        <div class="detail-row"><span class="detail-label">Board</span><span class="detail-value">${candidate['10th Board'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Passing Year</span><span class="detail-value">${candidate['10th Passing Year'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Marks</span><span class="detail-value">${candidate['10th Marks'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Percentage</span><span class="detail-value highlight">${candidate['10th Percentage'] ? candidate['10th Percentage'] + '%' : '-'}</span></div>
                    </div>

                    <div class="detail-group">
                        <div class="detail-group-title"><span class="material-icons-round" style="font-size:14px">school</span> 12th Details</div>
                        <div class="detail-row"><span class="detail-label">Board</span><span class="detail-value">${candidate['12th Board'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Stream</span><span class="detail-value">${candidate['12th Stream'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Passing Year</span><span class="detail-value">${candidate['12th Passing Year'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Marks</span><span class="detail-value">${candidate['12th Marks'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Percentage</span><span class="detail-value highlight">${candidate['12th Percentage'] ? candidate['12th Percentage'] + '%' : '-'}</span></div>
                    </div>

                    <div class="detail-group">
                        <div class="detail-group-title"><span class="material-icons-round" style="font-size:14px">school</span> Graduation Details</div>
                        <div class="detail-row"><span class="detail-label">University</span><span class="detail-value">${candidate['Graduation University'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Degree</span><span class="detail-value">${candidate['Graduation Degree'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Passing Year</span><span class="detail-value">${candidate['Graduation Passing Year'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Marks</span><span class="detail-value">${candidate['Graduation Marks'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Percentage</span><span class="detail-value highlight">${candidate['Graduation Percentage'] ? candidate['Graduation Percentage'] + '%' : '-'}</span></div>
                    </div>

                    <div class="detail-group">
                        <div class="detail-group-title"><span class="material-icons-round" style="font-size:14px">school</span> Post-Graduation Details</div>
                        <div class="detail-row"><span class="detail-label">University</span><span class="detail-value">${candidate['PG University'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Degree</span><span class="detail-value">${candidate['PG Degree'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">Passing Year</span><span class="detail-value">${candidate['PG Passing Year'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">PG Marks</span><span class="detail-value">${candidate['PG Marks'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">PG Percentage</span><span class="detail-value highlight">${candidate['PG Percentage'] ? candidate['PG Percentage'] + '%' : '-'}</span></div>
                    </div>

                    <div class="detail-group">
                        <div class="detail-group-title"><span class="material-icons-round" style="font-size:14px">work</span> Experience & Resume</div>
                        <div class="detail-row"><span class="detail-label">Total Experience</span><span class="detail-value highlight">${candidate['Total Experience'] || '-'}</span></div>
                        <div class="detail-row"><span class="detail-label">CV/Resume</span><span class="detail-value highlight">${candidate['Resume (attachment)'] || '-'}</span></div>
                    </div>
                </div>
            `;
            resultsGrid.appendChild(card);
        });
    }

    if (data.errors && data.errors.length > 0) {
        errorsPanel.style.display = 'block';
        errorsList.innerHTML = data.errors.map(err =>
            `<div class="error-item"><strong>${err.file}</strong>: ${err.error}</div>`
        ).join('');
    } else {
        errorsPanel.style.display = 'none';
    }
}

// ---- Tracker ----

async function loadTracker() {
    try {
        const response = await fetch('/tracker');
        const data = await response.json();

        if (data.data && data.data.length > 0) {
            renderTrackerTable(data.data);
            resultsSection.style.display = 'none';
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

    const headers = Object.keys(dataArray[0]);

    const trHead = document.createElement('tr');
    headers.forEach(h => {
        const th = document.createElement('th');
        th.innerText = h;
        trHead.appendChild(th);
    });
    thead.appendChild(trHead);

    dataArray.forEach(row => {
        const tr = document.createElement('tr');
        headers.forEach(h => {
            const td = document.createElement('td');
            td.innerText = row[h] !== null && row[h] !== undefined ? row[h] : '';
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });

    trackerSection.scrollIntoView({ behavior: 'smooth' });
}

function downloadCSV() {
    window.location.href = '/download';
}

// ---- Toast Notifications ----

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

// ---- Background Particles ----
(function initParticles() {
    const container = document.getElementById('bgParticles');
    if (!container) return;
    for (let i = 0; i < 20; i++) {
        const p = document.createElement('div');
        p.className = 'particle';
        p.style.cssText = `
            position: absolute;
            width: ${Math.random() * 6 + 2}px;
            height: ${Math.random() * 6 + 2}px;
            background: rgba(99,102,241,${Math.random() * 0.3 + 0.1});
            border-radius: 50%;
            left: ${Math.random() * 100}%;
            top: ${Math.random() * 100}%;
            animation: float ${Math.random() * 10 + 8}s ease-in-out infinite;
            animation-delay: -${Math.random() * 10}s;
        `;
        container.appendChild(p);
    }
})();
