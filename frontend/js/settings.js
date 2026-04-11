/**
 * RAG System — Settings Modal Logic
 * Handles model switching, status display, and statistics.
 */

function openSettings() {
    document.getElementById('settings-modal').style.display = 'flex';
    loadSettingsData();
}

function closeSettings() {
    document.getElementById('settings-modal').style.display = 'none';
}

async function loadSettingsData() {
    try {
        // Load models
        const modelsData = await API.get('/api/settings/models');
        const models = modelsData.models || [];
        const current = modelsData.current || {};

        // Chat model dropdown
        const chatSelect = document.getElementById('settings-chat-model');
        chatSelect.innerHTML = models.map(m =>
            `<option value="${m.name}" ${m.name === current.chat_model ? 'selected' : ''}>${m.name}</option>`
        ).join('');
        chatSelect.onchange = async () => {
            await switchModel('chat', chatSelect.value);
            // Update sidebar dropdown too
            document.getElementById('model-select').value = chatSelect.value;
        };

        // Embed model dropdown
        const embedSelect = document.getElementById('settings-embed-model');
        embedSelect.innerHTML = models.map(m =>
            `<option value="${m.name}" ${m.name === current.embed_model ? 'selected' : ''}>${m.name}</option>`
        ).join('');
        embedSelect.onchange = async () => {
            await switchModel('embed', embedSelect.value);
        };

        // Load status
        const statusData = await API.get('/api/settings/status');

        const statusGrid = document.getElementById('settings-status-grid');
        statusGrid.innerHTML = `
            <div class="status-card">
                <div class="card-label">Ollama</div>
                <div class="card-value ${statusData.ollama?.available ? 'success' : 'error'}">
                    ${statusData.ollama?.available ? '● Online' : '● Offline'}
                </div>
            </div>
            <div class="status-card">
                <div class="card-label">File Watcher</div>
                <div class="card-value ${statusData.file_watcher?.running ? 'success' : 'error'}">
                    ${statusData.file_watcher?.running ? '● Active' : '● Stopped'}
                </div>
            </div>
            <div class="status-card">
                <div class="card-label">Chat Model</div>
                <div class="card-value">${current.chat_model || 'None'}</div>
            </div>
            <div class="status-card">
                <div class="card-label">Embed Model</div>
                <div class="card-value">${current.embed_model || 'None'}</div>
            </div>
        `;

        // Load stats
        const statsData = await API.get('/api/documents/stats');
        const vsStats = statsData.vector_store || {};

        const statsGrid = document.getElementById('settings-stats-grid');
        statsGrid.innerHTML = `
            <div class="stats-card">
                <div class="card-label">Files on Disk</div>
                <div class="card-value">${statsData.files_on_disk || 0}</div>
            </div>
            <div class="stats-card">
                <div class="card-label">Total Chunks</div>
                <div class="card-value">${vsStats.total_chunks || 0}</div>
            </div>
            ${Object.entries(vsStats.directory_counts || {}).map(([dir, count]) => `
                <div class="stats-card">
                    <div class="card-label">📁 ${dir}</div>
                    <div class="card-value">${count} chunks</div>
                </div>
            `).join('')}
        `;

    } catch (err) {
        console.error('Failed to load settings:', err);
    }
}
