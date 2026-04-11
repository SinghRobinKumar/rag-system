/**
 * RAG System — File Upload Logic
 * Handles drag-and-drop, file selection, upload, and directory management.
 */

// ─── State ──────────────────────────────────────────────────────────────────
let selectedFiles = [];

// ─── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    setupUploadListeners();
});

function setupUploadListeners() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const browseBtn = document.getElementById('btn-browse');

    // Drag & Drop
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });

    // Click to browse
    dropZone.addEventListener('click', () => fileInput.click());
    browseBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        fileInput.click();
    });

    // File input change
    fileInput.addEventListener('change', () => {
        handleFiles(fileInput.files);
        fileInput.value = ''; // Reset so same file can be selected again
    });

    // Upload button
    document.getElementById('btn-upload').addEventListener('click', uploadFiles);

    // New directory
    document.getElementById('btn-new-dir').addEventListener('click', () => {
        document.getElementById('new-dir-input').style.display = 'block';
        document.getElementById('new-dir-name').focus();
    });
    document.getElementById('btn-cancel-dir').addEventListener('click', () => {
        document.getElementById('new-dir-input').style.display = 'none';
        document.getElementById('new-dir-name').value = '';
    });
    document.getElementById('btn-create-dir').addEventListener('click', createDirectory);
    document.getElementById('new-dir-name').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') createDirectory();
    });

    // Reindex
    document.getElementById('btn-reindex').addEventListener('click', reindexAll);
}

// ─── File Handling ──────────────────────────────────────────────────────────
function handleFiles(fileList) {
    for (const file of fileList) {
        // Avoid duplicates
        if (!selectedFiles.find(f => f.name === file.name && f.size === file.size)) {
            selectedFiles.push(file);
        }
    }
    renderFileQueue();
}

function renderFileQueue() {
    const section = document.getElementById('file-queue-section');
    const queue = document.getElementById('file-queue');

    if (!selectedFiles.length) {
        section.style.display = 'none';
        return;
    }

    section.style.display = 'block';
    queue.innerHTML = selectedFiles.map((f, i) => `
        <div class="file-queue-item">
            <span class="file-name">${escapeHtml(f.name)}</span>
            <span class="file-size">${formatFileSize(f.size)}</span>
            <button class="file-remove" onclick="removeFile(${i})" title="Remove">✕</button>
        </div>
    `).join('');
}

function removeFile(index) {
    selectedFiles.splice(index, 1);
    renderFileQueue();
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// ─── Upload ─────────────────────────────────────────────────────────────────
async function uploadFiles() {
    const dirSelect = document.getElementById('upload-dir-select');
    const directory = dirSelect.value;

    if (!directory) {
        alert('Please select a target directory');
        return;
    }
    if (!selectedFiles.length) {
        alert('Please select files to upload');
        return;
    }

    const uploadBtn = document.getElementById('btn-upload');
    uploadBtn.disabled = true;
    uploadBtn.textContent = 'Uploading...';

    const logSection = document.getElementById('upload-log-section');
    const logContainer = document.getElementById('upload-log');
    logSection.style.display = 'block';
    logContainer.innerHTML = '';

    try {
        const formData = new FormData();
        formData.append('directory', directory);
        selectedFiles.forEach(f => formData.append('files', f));

        const data = await API.postForm('/api/documents/upload', formData);

        // Show results
        (data.results || []).forEach(r => {
            const icon = r.status === 'success' ? '✅' : r.status === 'skipped' ? '⏭️' : '❌';
            logContainer.innerHTML += `
                <div class="upload-log-item">
                    <span class="log-status">${icon}</span>
                    <span class="log-message">${escapeHtml(r.file || r.message || '')} ${r.chunks ? `(${r.chunks} chunks)` : ''}</span>
                </div>
            `;
        });

        // Clear selection
        selectedFiles = [];
        renderFileQueue();

        // Refresh directories
        await loadDirectories();

    } catch (err) {
        logContainer.innerHTML += `
            <div class="upload-log-item">
                <span class="log-status">❌</span>
                <span class="log-message">Upload failed: ${escapeHtml(err.message)}</span>
            </div>
        `;
    } finally {
        uploadBtn.disabled = false;
        uploadBtn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            Upload & Index
        `;
    }
}

// ─── Directory Management ───────────────────────────────────────────────────
async function createDirectory() {
    const nameInput = document.getElementById('new-dir-name');
    const name = nameInput.value.trim();

    if (!name) return;

    try {
        const formData = new FormData();
        formData.append('name', name);

        // Check if a parent directory is selected
        const dirSelect = document.getElementById('upload-dir-select');
        if (dirSelect.value) {
            formData.append('parent', dirSelect.value);
        }

        await API.postForm('/api/documents/directories', formData);

        // Reset
        nameInput.value = '';
        document.getElementById('new-dir-input').style.display = 'none';

        // Refresh
        await loadDirectories();

    } catch (err) {
        alert('Failed to create directory: ' + err.message);
    }
}

// ─── Reindex ────────────────────────────────────────────────────────────────
async function reindexAll() {
    const btn = document.getElementById('btn-reindex');
    btn.disabled = true;
    btn.textContent = '⏳ Re-indexing...';

    try {
        const data = await API.post('/api/documents/reindex', {});

        const logSection = document.getElementById('upload-log-section');
        const logContainer = document.getElementById('upload-log');
        logSection.style.display = 'block';
        logContainer.innerHTML = `
            <div class="upload-log-item">
                <span class="log-status">✅</span>
                <span class="log-message">Re-indexed ${data.indexed || 0} files (${data.errors || 0} errors, ${data.skipped || 0} skipped)</span>
            </div>
        `;

        await loadDirectories();

    } catch (err) {
        alert('Re-indexing failed: ' + err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
            Re-index All Documents
        `;
    }
}
