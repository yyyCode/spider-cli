const form = document.getElementById("download-form");
const input = document.getElementById("url-input");
const button = document.getElementById("submit-btn");
const buttonLabel = button.querySelector(".button__label");
const badge = document.getElementById("platform-badge");
const badgeText = document.getElementById("platform-text");
const statusBox = document.getElementById("status");
const statusText = document.getElementById("status-text");
const statusPercent = document.getElementById("status-percent");
const statusSize = document.getElementById("status-size");
const progress = document.getElementById("progress");
const progressBar = document.getElementById("progress-bar");

const URL_RE = /https?:\/\/[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+/;
const PLATFORM_HOSTS = {
  douyin: [/(^|\.)douyin\.com$/i, /(^|\.)iesdouyin\.com$/i],
  xhs: [/(^|\.)xiaohongshu\.com$/i, /(^|\.)xhslink\.com$/i],
};
const PENDING_MESSAGES = [
  "正在解析链接…",
  "正在准备浏览器…",
  "正在等待视频流…",
];

let busy = false;

function detectPlatform(text) {
  const match = text.match(URL_RE);
  if (!match) return null;
  try {
    const host = new URL(match[0]).hostname.toLowerCase();
    for (const [platform, patterns] of Object.entries(PLATFORM_HOSTS)) {
      if (patterns.some((pattern) => pattern.test(host))) return platform;
    }
  } catch (_) {
    return null;
  }
  return null;
}

function updateBadge() {
  const platform = detectPlatform(input.value);
  badge.className = "stamp";

  if (platform === "douyin") {
    badgeText.textContent = "抖音视频";
    badge.classList.add("stamp--douyin");
  } else if (platform === "xhs") {
    badgeText.textContent = "小红书视频";
    badge.classList.add("stamp--xhs");
  } else if (input.value.trim()) {
    badgeText.textContent = "未识别链接";
    badge.classList.add("stamp--invalid");
  } else {
    badgeText.textContent = "等待链接";
    badge.classList.add("stamp--idle");
  }

  button.disabled = busy || !platform;
}

function setLoading(loading) {
  busy = loading;
  button.classList.toggle("is-loading", loading);
  button.setAttribute("aria-busy", String(loading));
  buttonLabel.textContent = loading ? "接收中…" : "下载视频";
  updateBadge();
}

function showStatus(kind, text, percent = "") {
  statusBox.className = `readout readout--${kind}`;
  statusText.textContent = text;
  statusPercent.textContent = percent;
}

function setProgress(percent) {
  progressBar.style.width = `${percent}%`;
  progress.setAttribute("aria-valuenow", String(percent));
}

function setIndeterminate(active) {
  progress.classList.toggle("progress--indeterminate", active);
  if (active) {
    progress.removeAttribute("aria-valuenow");
  } else {
    progress.setAttribute("aria-valuenow", "0");
  }
}

function resetStatus() {
  showStatus("idle", "待机", "0%");
  statusSize.textContent = "0 B";
  setIndeterminate(false);
  setProgress(0);
}

function formatSize(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1
  );
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function parseFilename(header) {
  if (!header) return null;
  const encoded = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].trim());
    } catch (_) {
      /* 继续尝试普通 filename */
    }
  }
  const plain = header.match(/filename="?([^";]+)"?/i);
  return plain ? plain[1].trim() : null;
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

async function download(rawUrl) {
  setLoading(true);
  resetStatus();
  showStatus("processing", PENDING_MESSAGES[0], "…");
  setIndeterminate(true);

  let messageIndex = 0;
  let receiving = false;
  const messageTimer = setInterval(() => {
    if (receiving) return;
    messageIndex = Math.min(messageIndex + 1, PENDING_MESSAGES.length - 1);
    showStatus("processing", PENDING_MESSAGES[messageIndex], "…");
  }, 4000);

  try {
    const response = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: rawUrl }),
    });

    if (!response.ok) {
      let detail = `请求失败（${response.status}）`;
      try {
        const data = await response.json();
        if (data && data.detail) detail = data.detail;
      } catch (_) {
        /* 保留默认错误文案 */
      }
      throw new Error(detail);
    }

    const filename =
      parseFilename(response.headers.get("Content-Disposition")) || "video.mp4";
    const total = Number(response.headers.get("Content-Length")) || 0;
    const contentType = response.headers.get("Content-Type") || "video/mp4";

    receiving = true;
    setIndeterminate(false);
    setProgress(0);
    statusSize.textContent = "0 B";
    showStatus("processing", "正在接收视频…", total ? "0%" : "…");
    if (!total) setIndeterminate(true);

    const reader = response.body.getReader();
    const chunks = [];
    let received = 0;
    let lastRender = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      received += value.length;

      const now = performance.now();
      if (now - lastRender < 120) continue;
      lastRender = now;
      statusSize.textContent = formatSize(received);

      if (total) {
        const percent = Math.min(100, Math.round((received / total) * 100));
        setProgress(percent);
        showStatus("processing", "正在接收视频…", `${percent}%`);
      }
    }

    const blob = new Blob(chunks, { type: contentType });
    saveBlob(blob, filename);
    setIndeterminate(false);
    setProgress(100);
    statusSize.textContent = formatSize(blob.size);
    showStatus("success", `已保存 ${filename}`, "100%");
  } catch (error) {
    setIndeterminate(false);
    setProgress(0);
    statusSize.textContent = "—";
    showStatus("error", error.message || "下载失败，请稍后重试", "");
  } finally {
    clearInterval(messageTimer);
    setLoading(false);
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (busy || !detectPlatform(input.value)) return;
  download(input.value.trim());
});

input.addEventListener("input", updateBadge);

input.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    form.requestSubmit();
  }
});

updateBadge();
resetStatus();
