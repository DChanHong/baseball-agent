const messages = document.querySelector("#messages");
const chatForm = document.querySelector("#chatForm");
const messageInput = document.querySelector("#messageInput");
const favoriteTeamInput = document.querySelector("#favoriteTeamInput");
const originInput = document.querySelector("#originInput");
const preferencesInput = document.querySelector("#preferencesInput");
const sendButton = document.querySelector("#sendButton");
const clearButton = document.querySelector("#clearButton");
const healthStatus = document.querySelector("#healthStatus");
let isSending = false;
let isComposing = false;
let lastSubmitAt = 0;
let lastSubmittedMessage = "";
let sessionId = null;

function sanitizeMessage(value) {
  return value
    .replace(/\x1B\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/[\u0000-\u001F\u007F-\u009F]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function compactValue(value, maxLength = 600) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  if (!text || text.length <= maxLength) {
    return value;
  }
  return `${text.slice(0, maxLength)}...`;
}

function compactMetadata(metadata) {
  if (!metadata) {
    return null;
  }

  return {
    intent: metadata.intent,
    primary_intent: metadata.primary_intent,
    resolved_intents: metadata.resolved_intents || [],
    agent_mode: metadata.agent_mode,
    trace_summary: metadata.trace_summary,
    usage: metadata.usage,
    tools_used: metadata.tools_used || [],
    observations: (metadata.observations || []).map((observation) => ({
      step: observation.step,
      tool: observation.tool,
      arguments: compactValue(observation.arguments, 420),
      result: observation.result,
      observation_excerpt: compactValue(observation.observation_excerpt, 900),
    })),
    stop_reason: metadata.stop_reason,
    iterations: metadata.iterations,
    elapsed_ms: metadata.elapsed_ms,
    fallback_used: metadata.fallback_used,
  };
}

function appendMessage(role, text, metadata) {
  const article = document.createElement("article");
  article.className = `message ${role}`;

  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = text;
  article.appendChild(body);

  if (metadata) {
    const details = document.createElement("details");
    details.className = "metadata";

    const summary = document.createElement("summary");
    const tools = metadata.tools_used?.length ? metadata.tools_used.join(" -> ") : "tool 없음";
    summary.textContent = `${metadata.stop_reason || "unknown"} · ${tools}`;
    details.appendChild(summary);

    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(compactMetadata(metadata), null, 2);
    details.appendChild(pre);
    article.appendChild(details);
  }

  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
}

function parsePreferences(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildPayload() {
  const userContext = {
    favorite_team: favoriteTeamInput.value.trim() || null,
    origin: originInput.value.trim() || null,
    preferences: parsePreferences(preferencesInput.value),
  };

  const hasContext = userContext.favorite_team || userContext.origin || userContext.preferences.length;
  return {
    message: sanitizeMessage(messageInput.value),
    user_context: hasContext ? userContext : null,
    session_id: sessionId,
  };
}

async function sendMessage() {
  const now = Date.now();
  if (isSending || now - lastSubmitAt < 350) {
    return;
  }

  const payload = buildPayload();
  if (!payload.message || payload.message.length < 2) {
    messageInput.focus();
    return;
  }
  if (payload.message === lastSubmittedMessage && now - lastSubmitAt < 2000) {
    return;
  }

  isSending = true;
  lastSubmitAt = now;
  lastSubmittedMessage = payload.message;
  appendMessage("user", payload.message);
  messageInput.value = "";
  sendButton.disabled = true;
  sendButton.textContent = "처리 중";

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (data.metadata?.session_id) {
      sessionId = data.metadata.session_id;
    }
    if (!response.ok) {
      appendMessage("agent", data.detail || "요청 처리에 실패했습니다.");
      return;
    }

    appendMessage("agent", data.answer, data.metadata);
  } catch (error) {
    appendMessage("agent", `네트워크 오류: ${error.message}`);
  } finally {
    isSending = false;
    sendButton.disabled = false;
    sendButton.textContent = "전송";
    messageInput.focus();
  }
}

async function checkHealth() {
  try {
    const response = await fetch("/health");
    const data = await response.json();
    healthStatus.textContent = data.status === "ok" ? "온라인" : "확인 필요";
    healthStatus.dataset.state = data.status === "ok" ? "ok" : "warn";
    if (data.default_session_id) {
      sessionId = data.default_session_id;
    }
  } catch {
    healthStatus.textContent = "오프라인";
    healthStatus.dataset.state = "error";
  }
}

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (isComposing) {
    return;
  }
  sendMessage();
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !isComposing && !event.isComposing) {
    event.preventDefault();
    sendMessage();
  }
});

messageInput.addEventListener("compositionstart", () => {
  isComposing = true;
});

messageInput.addEventListener("compositionend", () => {
  isComposing = false;
});

clearButton.addEventListener("click", () => {
  messages.replaceChildren();
  messageInput.value = "";
  favoriteTeamInput.value = "";
  originInput.value = "";
  preferencesInput.value = "";
  lastSubmittedMessage = "";
  messageInput.focus();
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    messageInput.value = button.dataset.prompt;
    messageInput.focus();
  });
});

appendMessage("agent", "경기 날짜와 팀을 포함해서 물어보면 좌석, 예매, 원정 동선을 함께 확인합니다.");
checkHealth();
