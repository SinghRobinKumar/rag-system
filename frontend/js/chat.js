/**
 * RAG System — Chat Interface Logic
 * Handles message sending, streaming responses, and message rendering.
 */

// ─── Send Message ───────────────────────────────────────────────────────────
async function sendMessage() {
  const input = document.getElementById("chat-input");
  const message = input.value.trim();

  if (!message || state.isStreaming) return;

  // Hide welcome screen
  const welcome = document.getElementById("welcome-screen");
  if (welcome) welcome.style.display = "none";

  // Add user message to UI
  addMessageToUI("user", message);

  // Clear input
  input.value = "";
  input.style.height = "auto";

  // Disable send button
  state.isStreaming = true;
  document.getElementById("btn-send").disabled = true;

  const typingId = addTypingIndicator();
  updateTypingStatus("Analyzing query...");

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: message,
        session_id: state.currentSessionId,
        mode: state.mode,
      }),
    });

    if (!response.ok) throw new Error(`Chat failed: ${response.status}`);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let fullContent = "";
    let metadata = null;
    let assistantMsgEl = null;
    let hasReceivedContent = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const text = decoder.decode(value, { stream: true });
      const lines = text.split("\n");

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;

        try {
          const data = JSON.parse(line.slice(6));

          if (data.type === "metadata") {
            metadata = data;
            if (data.session_id) {
              state.currentSessionId = data.session_id;
            }

            if (data.route?.strategy === "greeting") {
              updateTypingStatus("Responding...");
            } else if (data.sources?.length > 0) {
              updateTypingStatus(
                `Found ${data.sources.length} sources, generating response...`,
              );
            } else {
              updateTypingStatus("Generating response...");
            }
          } else if (data.type === "content") {
            if (!hasReceivedContent) {
              removeTypingIndicator(typingId);
              hasReceivedContent = true;
            }
            if (!assistantMsgEl) {
              assistantMsgEl = addMessageToUI("assistant", "", metadata);
            }
            fullContent += data.content;
            updateMessageContent(assistantMsgEl, fullContent);
          } else if (data.type === "done") {
            loadSessions();
          } else if (data.type === "error") {
            removeTypingIndicator(typingId);
            addMessageToUI("assistant", `⚠️ Error: ${data.content}`);
          }
        } catch (parseErr) {
          // Skip malformed JSON
        }
      }
    }
  } catch (err) {
    removeTypingIndicator(typingId);
    addMessageToUI("assistant", `⚠️ Failed to get response: ${err.message}`);
  } finally {
    state.isStreaming = false;
    document.getElementById("btn-send").disabled = false;
    input.focus();
  }
}

// ─── Message Rendering ──────────────────────────────────────────────────────
function addMessageToUI(role, content, metadata = null) {
  const container = document.getElementById("chat-messages");
  const msgDiv = document.createElement("div");
  msgDiv.className = `message ${role}`;

  const avatarIcon = role === "user" ? "👤" : "🤖";
  const roleName = role === "user" ? "You" : "Assistant";

  msgDiv.innerHTML = `
        <div class="message-avatar">${avatarIcon}</div>
        <div class="message-body">
            <div class="message-role">${roleName}</div>
            <div class="message-content">${role === "user" ? escapeHtml(content) : renderMarkdown(content)}</div>
            ${metadata ? renderMetadata(metadata) : ""}
        </div>
    `;

  container.appendChild(msgDiv);
  scrollToBottom();

  return msgDiv;
}

function updateMessageContent(msgEl, content) {
  const contentEl = msgEl.querySelector(".message-content");
  if (contentEl) {
    contentEl.innerHTML = renderMarkdown(content);
    scrollToBottom();
  }
}

function renderMetadata(metadata) {
  let html = "";

  // Sources
  if (metadata.sources && metadata.sources.length) {
    const uniqueSources = [];
    const seen = new Set();

    for (const s of metadata.sources) {
      // Handle both web sources and document sources
      const key = s.type === "web" ? s.url : `${s.directory}/${s.file}`;
      if (!seen.has(key)) {
        seen.add(key);
        uniqueSources.push(s);
      }
    }

    if (uniqueSources.length > 0) {
      html += `<div class="message-sources">
              <div class="message-sources-title">📚 Sources</div>`;

      uniqueSources.forEach((s) => {
        if (s.type === "web") {
          // Web source
          html += `<div class="message-source-item">
                      🌐 <a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.title)}</a>
                   </div>`;
        } else {
          // Document source
          html += `<div class="message-source-item">
                      📄 ${escapeHtml(s.directory)} / ${escapeHtml(s.file)}
                   </div>`;
        }
      });

      html += `</div>`;
    }
  }

  // Route info (only show for debugging, can be hidden)
  if (metadata.route && metadata.mode === "offline") {
    const r = metadata.route;
    if (r.target_dirs && r.target_dirs.length > 0) {
      html += `<div class="message-route">
              📁 Searched in: ${r.target_dirs.join(", ")}
          </div>`;
    }
  }

  return html;
}

// ─── Simple Markdown Renderer ───────────────────────────────────────────────
function renderMarkdown(text) {
  if (!text) return "";

  let html = escapeHtml(text);

  // Code blocks (```)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre><code class="language-${lang}">${code.trim()}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  // Italic
  html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");

  // Headings
  html = html.replace(/^### (.+)$/gm, "<h4>$1</h4>");
  html = html.replace(/^## (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^# (.+)$/gm, "<h2>$1</h2>");

  // Unordered lists
  html = html.replace(/^[\s]*[-*] (.+)$/gm, "<li>$1</li>");
  html = html.replace(/(<li>.*<\/li>\n?)+/gs, "<ul>$&</ul>");

  // Numbered lists
  html = html.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");

  // Line breaks → paragraphs
  html = html.replace(/\n\n/g, "</p><p>");
  html = html.replace(/\n/g, "<br>");

  // Wrap in paragraph
  if (!html.startsWith("<")) {
    html = `<p>${html}</p>`;
  }

  return html;
}

// ─── Typing Indicator ───────────────────────────────────────────────────────
function addTypingIndicator() {
  const container = document.getElementById("chat-messages");
  const id = "typing-" + Date.now();

  const div = document.createElement("div");
  div.className = "message assistant";
  div.id = id;
  div.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-body">
            <div class="message-role">Assistant</div>
            <div class="typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
            <div class="typing-status" style="font-size:11px;color:var(--text-muted);margin-top:4px;"></div>
        </div>
    `;

  container.appendChild(div);
  scrollToBottom();
  return id;
}

function updateTypingStatus(status) {
  const statusEl = document.querySelector(".typing-status");
  if (statusEl) {
    statusEl.textContent = status;
  }
}

function removeTypingIndicator(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

// ─── Scroll ─────────────────────────────────────────────────────────────────
function scrollToBottom() {
  const container = document.getElementById("chat-messages");
  container.scrollTop = container.scrollHeight;
}
