/**
 * RAG System — Main Application Logic
 * Handles initialization, API calls, state management, and UI updates.
 */

const state = {
  currentSessionId: null,
  sessions: [],
  directories: [],
  isStreaming: false,
  mode: "offline",
};

// ─── API Helper ─────────────────────────────────────────────────────────────
const API = {
  async get(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`GET ${url} failed: ${res.status}`);
    return res.json();
  },
  async post(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`POST ${url} failed: ${res.status}`);
    return res.json();
  },
  async postForm(url, formData) {
    const res = await fetch(url, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) throw new Error(`POST ${url} failed: ${res.status}`);
    return res.json();
  },
  async put(url, body) {
    const res = await fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`PUT ${url} failed: ${res.status}`);
    return res.json();
  },
  async delete(url) {
    const res = await fetch(url, { method: "DELETE" });
    if (!res.ok) throw new Error(`DELETE ${url} failed: ${res.status}`);
    return res.json();
  },
};

// ─── Initialization ─────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initApp();
});

async function initApp() {
  // Load initial data
  await Promise.all([
    loadSessions(),
    loadDirectories(),
    loadModels(),
    checkStatus(),
  ]);

  // Set up event listeners
  setupEventListeners();

  // Auto-check status every 30s
  setInterval(checkStatus, 30000);
}

// ─── Sessions ───────────────────────────────────────────────────────────────
async function loadSessions() {
  try {
    const data = await API.get("/api/chat/sessions");
    state.sessions = data.sessions || [];
    renderSessions();
  } catch (e) {
    console.error("Failed to load sessions:", e);
  }
}

function renderSessions() {
  const container = document.getElementById("session-list");
  if (!state.sessions.length) {
    container.innerHTML =
      '<div style="padding:8px 10px;color:var(--text-muted);font-size:12px;">No conversations yet</div>';
    return;
  }

  container.innerHTML = state.sessions
    .map(
      (s) => `
        <div class="session-item ${s.session_id === state.currentSessionId ? "active" : ""}"
             data-id="${s.session_id}" onclick="switchSession('${s.session_id}')">
            <span class="session-title">${escapeHtml(s.title)}</span>
            <button class="session-delete" onclick="event.stopPropagation();deleteSession('${s.session_id}')" title="Delete">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
        </div>
    `,
    )
    .join("");
}

async function switchSession(sessionId) {
  state.currentSessionId = sessionId;
  const session = state.sessions.find((s) => s.session_id === sessionId);
  if (session) {
    document.getElementById("chat-title").textContent = session.title;
  }
  renderSessions();
  clearChatUI();

  // Load historical messages from the backend
  try {
    const data = await API.get(`/api/chat/sessions/${sessionId}`);
    if (data && data.messages && data.messages.length > 0) {
      // Replay messages into the UI
      data.messages.forEach((msg) => {
        // Determine if we have metadata to show. The backend doesn't store metadata
        // explicitly in the messages list, so we'll just render it as a plain message.
        // It will be visually identical to after a page reload.
        addMessageToUI(msg.role, msg.content, null);
      });
    }
  } catch (e) {
    console.error("Failed to load session history:", e);
  }
}

async function deleteSession(sessionId) {
  try {
    await API.delete(`/api/chat/sessions/${sessionId}`);
    if (state.currentSessionId === sessionId) {
      state.currentSessionId = null;
      document.getElementById("chat-title").textContent = "New Chat";
      showWelcome();
    }
    await loadSessions();
  } catch (e) {
    console.error("Failed to delete session:", e);
  }
}

async function createNewSession() {
  state.currentSessionId = null;
  document.getElementById("chat-title").textContent = "New Chat";
  showWelcome();
  renderSessions();
}

// ─── Directories ────────────────────────────────────────────────────────────
async function loadDirectories() {
  try {
    const data = await API.get("/api/documents/directories");
    state.directories = data.directories || [];
    renderDirectoryTree();
    updateUploadDirDropdown();
  } catch (e) {
    console.error("Failed to load directories:", e);
  }
}

function renderDirectoryTree() {
  const container = document.getElementById("directory-tree");
  if (!container) return; // Element may be commented out in HTML
  if (!state.directories.length) {
    container.innerHTML =
      '<div style="padding:6px 8px;color:var(--text-muted);font-size:12px;">No folders yet</div>';
    return;
  }

  container.innerHTML = renderDirItems(state.directories);
}

function renderDirItems(dirs, depth = 0) {
  return dirs
    .map(
      (d) => `
        <div class="dir-item" style="padding-left:${8 + depth * 16}px;">
            <span class="dir-icon">📁</span>
            <span class="dir-name">${escapeHtml(d.name)}</span>
            <span class="dir-count">${d.file_count}</span>
        </div>
        ${d.children && d.children.length ? renderDirItems(d.children, depth + 1) : ""}
    `,
    )
    .join("");
}

function updateUploadDirDropdown() {
  const select = document.getElementById("upload-dir-select");
  const options = ['<option value="">Select directory...</option>'];

  function addDirOptions(dirs, prefix = "") {
    dirs.forEach((d) => {
      options.push(`<option value="${d.path}">${prefix}${d.name}</option>`);
      if (d.children && d.children.length) {
        addDirOptions(d.children, prefix + "  └─ ");
      }
    });
  }

  addDirOptions(state.directories);
  select.innerHTML = options.join("");
}

// ─── Models ─────────────────────────────────────────────────────────────────
async function loadModels() {
  try {
    const data = await API.get("/api/settings/models");
    const models = data.models || [];
    const current = data.current || {};

    // Populate sidebar model dropdown
    const select = document.getElementById("model-select");
    select.innerHTML = models
      .map(
        (m) =>
          `<option value="${m.name}" ${m.name === current.chat_model ? "selected" : ""}>${m.name}</option>`,
      )
      .join("");

    if (!models.length) {
      select.innerHTML = "<option>No models found</option>";
    }

    // Add change handler
    select.onchange = async () => {
      await switchModel("chat", select.value);
    };
  } catch (e) {
    console.error("Failed to load models:", e);
    document.getElementById("model-select").innerHTML =
      "<option>Error loading</option>";
  }
}

async function switchModel(type, name) {
  try {
    await API.put("/api/settings/model", {
      model_type: type,
      model_name: name,
    });
    console.log(`Switched ${type} model to ${name}`);
  } catch (e) {
    console.error("Failed to switch model:", e);
  }
}

// ─── Status ─────────────────────────────────────────────────────────────────
async function checkStatus() {
  try {
    const data = await API.get("/api/settings/status");
    const dot = document.getElementById("status-dot");
    const text = document.getElementById("status-text");

    if (data.ollama?.available) {
      dot.className = "status-dot online";
      text.textContent = "Ollama Online";
    } else {
      dot.className = "status-dot offline";
      text.textContent = "Ollama Offline";
    }
  } catch (e) {
    const dot = document.getElementById("status-dot");
    const text = document.getElementById("status-text");
    dot.className = "status-dot offline";
    text.textContent = "Server Error";
  }
}

// ─── UI Helpers ─────────────────────────────────────────────────────────────
function showWelcome() {
  const welcome = document.getElementById("welcome-screen");
  const messages = document.getElementById("chat-messages");

  // Remove all messages except welcome
  const children = [...messages.children];
  children.forEach((c) => {
    if (c.id !== "welcome-screen") c.remove();
  });

  if (welcome) welcome.style.display = "flex";
}

function clearChatUI() {
  const messages = document.getElementById("chat-messages");
  const children = [...messages.children];
  children.forEach((c) => {
    if (c.id !== "welcome-screen") c.remove();
  });

  const welcome = document.getElementById("welcome-screen");
  if (welcome) welcome.style.display = "none";
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function useSuggestion(btn) {
  const text = btn.textContent.replace(/^[^\s]+\s/, ""); // Remove emoji prefix
  document.getElementById("chat-input").value = text;
  document.getElementById("chat-input").focus();
}

// ─── Event Listeners ────────────────────────────────────────────────────────
function setupEventListeners() {
  // Sidebar toggle
  document
    .getElementById("btn-toggle-sidebar")
    .addEventListener("click", () => {
      document.getElementById("sidebar").classList.toggle("collapsed");
    });

  // New chat
  document
    .getElementById("btn-new-chat")
    .addEventListener("click", createNewSession);

  // Mode toggle
  document
    .getElementById("mode-offline")
    .addEventListener("click", () => switchMode("offline"));
  document
    .getElementById("mode-web")
    .addEventListener("click", () => switchMode("web"));

  // Upload panel toggle
  const openUpload = () => {
    document.getElementById("upload-panel").classList.add("open");
    document.getElementById("upload-overlay").classList.add("active");
  };
  const btnOpenUpload = document.getElementById("btn-open-upload");
  if (btnOpenUpload) {
    btnOpenUpload.addEventListener("click", openUpload);
  }
  document
    .getElementById("btn-open-upload-main")
    .addEventListener("click", openUpload);
  document
    .getElementById("btn-close-upload")
    .addEventListener("click", closeUploadPanel);
  document
    .getElementById("upload-overlay")
    .addEventListener("click", closeUploadPanel);

  // Settings modal
  document
    .getElementById("btn-settings")
    .addEventListener("click", openSettings);
  document
    .getElementById("btn-close-settings")
    .addEventListener("click", closeSettings);
  document.getElementById("settings-modal").addEventListener("click", (e) => {
    if (e.target === document.getElementById("settings-modal")) closeSettings();
  });

  // Textarea auto-resize
  const textarea = document.getElementById("chat-input");
  textarea.addEventListener("input", () => {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + "px";
  });

  // Send on Enter
  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  document.getElementById("btn-send").addEventListener("click", sendMessage);
}

function closeUploadPanel() {
  document.getElementById("upload-panel").classList.remove("open");
  document.getElementById("upload-overlay").classList.remove("active");
}

function switchMode(mode) {
  state.mode = mode;

  document.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.classList.remove("active");
  });

  document.getElementById(`mode-${mode}`).classList.add("active");

  const input = document.getElementById("chat-input");
  if (mode === "web") {
    input.placeholder = "Ask anything... (searches the web)";
  } else {
    input.placeholder =
      "Ask about your documents... (use @folder to target specific directories)";
  }
}
