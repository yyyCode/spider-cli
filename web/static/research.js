(function () {
  "use strict";

  let root = document;
  let ui = null;

  const $ = (id) => root.querySelector(`#${id}`);

  const state = {
    mode: "search",
    busy: false,
    configured: false,
    defaultsApplied: false,
    results: [],
    lastQuery: "",
    reading: null,
  };

  const SEARCH_LABEL = "开始检索";
  const SEARCH_BUSY_LABEL = "检索中…";
  const FETCH_LABEL = "抓取正文";
  const FETCH_BUSY_LABEL = "抓取中…";
  const DEFAULT_COUNT = 10;
  const MAX_COUNT = 50;

  function clampCount(value) {
    const parsed = Number.parseInt(value, 10);
    if (!Number.isFinite(parsed)) return DEFAULT_COUNT;
    return Math.min(MAX_COUNT, Math.max(1, parsed));
  }

  function formatHost(value) {
    if (!value) return "";
    try {
      return new URL(value).host;
    } catch (_) {
      return "";
    }
  }

  function safeHttpUrl(value) {
    if (typeof value !== "string" || !value.trim()) return null;
    try {
      const parsed = new URL(value.trim());
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        return null;
      }
      return parsed.href;
    } catch (_) {
      return null;
    }
  }

  function hostnameOf(value) {
    const safe = safeHttpUrl(value);
    if (!safe) return "";
    try {
      return new URL(safe).hostname.replace(/^www\./i, "");
    } catch (_) {
      return "";
    }
  }

  function formatDate(value) {
    if (!value) return "";
    const text = String(value);
    const match = text.match(/^(\d{4}-\d{2}-\d{2})/);
    return match ? match[1] : text;
  }

  function hideViews() {
    ui.empty.hidden = true;
    ui.loading.hidden = true;
    ui.error.hidden = true;
    ui.resultsView.hidden = true;
    ui.readingView.hidden = true;
  }

  function scrollToWorkspace() {
    if (window.innerWidth > 760) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    ui.workspace.scrollIntoView({
      behavior: reduced ? "auto" : "smooth",
      block: "start",
    });
  }

  function showEmpty() {
    hideViews();
    ui.empty.hidden = false;
  }

  function showLoading(text) {
    hideViews();
    ui.loadingText.textContent = text;
    ui.loading.hidden = false;
    scrollToWorkspace();
  }

  function showError(message) {
    hideViews();
    ui.errorText.textContent = message || "请求失败，请稍后重试。";
    ui.error.hidden = false;
    scrollToWorkspace();
  }

  function showResults(results, query) {
    state.results = Array.isArray(results) ? results : [];
    state.lastQuery = query || "";
    activateTab("search", false);
    hideViews();
    ui.resultsView.hidden = false;
    renderResults(state.results, state.lastQuery);
    scrollToWorkspace();
  }

  function showReading(reading) {
    state.reading = reading;
    hideViews();
    ui.readingView.hidden = false;
    ui.readingTitle.textContent = reading.title || "未命名网页";
    ui.readingKind.textContent = reading.kind || "正文";
    ui.readingContent.textContent = reading.content || "";

    const source = safeHttpUrl(reading.url);
    if (source) {
      ui.readingSource.href = source;
      ui.readingSource.textContent = reading.url;
      ui.readingSource.hidden = false;
    } else {
      ui.readingSource.removeAttribute("href");
      ui.readingSource.textContent = "";
      ui.readingSource.hidden = true;
    }

    ui.backBtn.textContent = state.results.length ? "返回结果" : "清空";
    ui.backBtn.hidden = false;
    scrollToWorkspace();
  }

  function updateButtons() {
    const disabled = state.busy || !state.configured;
    ui.searchBtn.disabled = disabled;
    ui.fetchBtn.disabled = disabled;
  }

  function setBusy(busy, mode, loadingText) {
    state.busy = busy;
    ui.searchBtn.textContent =
      busy && mode === "search" ? SEARCH_BUSY_LABEL : SEARCH_LABEL;
    ui.fetchBtn.textContent =
      busy && mode === "fetch" ? FETCH_BUSY_LABEL : FETCH_LABEL;
    updateButtons();
    if (busy) {
      showLoading(loadingText || "正在处理…");
    }
  }

  function setConfigured(configured, message) {
    state.configured = configured;
    ui.apiStatus.classList.remove(
      "api-status--checking",
      "api-status--ready",
      "api-status--missing",
      "api-status--error"
    );
    if (configured) {
      ui.apiStatus.classList.add("api-status--ready");
      ui.apiStatusText.textContent = "API 已就绪";
      ui.configBanner.hidden = true;
      ui.recheckBtn.hidden = true;
    } else {
      ui.apiStatus.classList.add("api-status--missing");
      ui.apiStatusText.textContent = "API 未配置";
      ui.configMessage.textContent = message || "未配置 DeepSeek API Key。";
      ui.configBanner.hidden = false;
      ui.recheckBtn.hidden = false;
      ui.baseUrl.textContent = "";
    }
    updateButtons();
  }

  function setApiFailure(message) {
    state.configured = false;
    ui.apiStatus.classList.remove(
      "api-status--checking",
      "api-status--ready",
      "api-status--missing"
    );
    ui.apiStatus.classList.add("api-status--error");
    ui.apiStatusText.textContent = "无法读取配置";
    ui.configMessage.textContent =
      message || "无法读取服务状态，请确认 Web 服务正在运行。";
    ui.configBanner.hidden = false;
    ui.recheckBtn.hidden = false;
    ui.baseUrl.textContent = "";
    updateButtons();
  }

  async function readJson(response) {
    try {
      return await response.json();
    } catch (_) {
      return {};
    }
  }

  async function loadStatus() {
    ui.apiStatus.classList.remove(
      "api-status--ready",
      "api-status--missing",
      "api-status--error"
    );
    ui.apiStatus.classList.add("api-status--checking");
    ui.apiStatusText.textContent = "检查配置…";
    ui.recheckBtn.hidden = true;

    try {
      const response = await fetch("/api/research/status", {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      const data = await readJson(response);
      if (!response.ok) {
        throw new Error(data.detail || `读取配置失败（${response.status}）`);
      }
      if (data.configured) {
        if (!state.defaultsApplied) {
          ui.countInput.value = String(clampCount(data.default_count));
          ui.contentInput.checked = Boolean(data.default_need_content);
          state.defaultsApplied = true;
        }
        const host = formatHost(data.base_url);
        ui.baseUrl.textContent = host ? `接口 ${host}` : "";
        setConfigured(true);
      } else {
        setConfigured(false, data.message);
      }
    } catch (error) {
      setApiFailure(error && error.message ? error.message : "无法读取服务状态。");
    }
  }

  function createElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  }

  function addMeta(container, className, text) {
    if (text === undefined || text === null || text === "") return;
    container.appendChild(createElement("span", className, text));
  }

  function renderResults(results, query) {
    ui.resultsList.replaceChildren();

    if (!results.length) {
      ui.resultsMeta.textContent = `共 0 条，关键词“${query}”`;
      const empty = createElement("div", "result result--empty");
      empty.appendChild(createElement("h3", "", "没有找到结果"));
      empty.appendChild(
        createElement("p", "", "换一个关键词，或减少 site:、after: 等限定条件。")
      );
      ui.resultsList.appendChild(empty);
      return;
    }

    ui.resultsMeta.textContent = `共 ${results.length} 条，关键词“${query}”`;

    results.forEach((result, index) => {
      if (!result || typeof result !== "object") return;

      const article = createElement("article", "result");
      article.appendChild(
        createElement(
          "div",
          "result__rank",
          String(index + 1).padStart(2, "0")
        )
      );

      const body = createElement("div", "result__body");
      const meta = createElement("div", "result__meta");
      addMeta(
        meta,
        "result__site",
        result.site_name || hostnameOf(result.url) || "来源未知"
      );
      addMeta(meta, "result__date", formatDate(result.date));

      if (
        typeof result.rerank_score === "number" &&
        Number.isFinite(result.rerank_score)
      ) {
        const score = result.rerank_score;
        const scoreNode = createElement(
          "span",
          "result__score" + (score >= 1.5 ? "" : " result__score--low"),
          `相关度 ${score.toFixed(1)}`
        );
        scoreNode.title = "相关度 0–3，1.5 分以上为优质结果";
        meta.appendChild(scoreNode);
      }

      if (typeof result.authority === "number") {
        const authority = result.authority;
        const label = authority < 0 ? "权威 未知" : `权威 ${authority}`;
        meta.appendChild(
          createElement(
            "span",
            "result__authority" +
              (authority >= 3 ? " result__authority--high" : ""),
            label
          )
        );
      }

      body.appendChild(meta);

      const title = createElement("h3", "result__title");
      const safeUrl = safeHttpUrl(result.url);
      if (safeUrl) {
        const link = createElement("a", "", result.title || "未命名结果");
        link.href = safeUrl;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        title.appendChild(link);
      } else {
        title.textContent = result.title || "未命名结果";
      }
      body.appendChild(title);

      if (result.url) {
        const url = createElement("p", "result__url", result.url);
        url.title = result.url;
        body.appendChild(url);
      }

      const teaser = result.snippet || result.summary || "";
      if (teaser) {
        body.appendChild(createElement("p", "result__snippet", teaser));
      }

      if (result.summary && result.summary !== teaser) {
        const details = createElement("details", "result__summary");
        details.appendChild(createElement("summary", "", "展开长摘要"));
        details.appendChild(createElement("p", "", result.summary));
        body.appendChild(details);
      }

      const actions = createElement("div", "result__actions");
      if (typeof result.content === "string" && result.content.trim()) {
        const open = createElement("button", "link-button", "查看正文");
        open.type = "button";
        open.addEventListener("click", () => {
          showReading({
            title: result.title || hostnameOf(result.url) || "搜索结果正文",
            url: result.url,
            content: result.content,
            kind: "搜索结果正文",
          });
        });
        actions.appendChild(open);
      } else if (safeUrl) {
        const fetchButton = createElement("button", "link-button", "抓取正文");
        fetchButton.type = "button";
        fetchButton.addEventListener("click", () => {
          fetchPage(result.url, { title: result.title });
        });
        actions.appendChild(fetchButton);
      }

      if (actions.childElementCount) body.appendChild(actions);
      article.appendChild(body);
      ui.resultsList.appendChild(article);
    });
  }

  async function search(query) {
    const payload = {
      query,
      count: clampCount(ui.countInput.value),
      need_content: ui.contentInput.checked,
    };
    ui.countInput.value = String(payload.count);

    const original = ui.questionInput.value.trim();
    if (original) payload.ori_question = original;
    const localization = ui.localizationInput.value.trim();
    if (localization) payload.localization = localization;

    setBusy(true, "search", "正在检索…");
    try {
      const response = await fetch("/api/research/search", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(payload),
      });
      const data = await readJson(response);
      if (!response.ok) {
        throw new Error(data.detail || `搜索失败（${response.status}）`);
      }
      if (!Array.isArray(data.results)) {
        throw new Error("服务返回了无法识别的搜索结果。");
      }
      showResults(data.results, query);
    } catch (error) {
      showError(error && error.message ? error.message : "搜索失败，请稍后重试。");
    } finally {
      setBusy(false);
    }
  }

  async function fetchPage(rawUrl, info) {
    const safeUrl = safeHttpUrl(rawUrl);
    if (!safeUrl) {
      showError("请输入以 http:// 或 https:// 开头的完整网页地址。");
      return;
    }

    setBusy(true, "fetch", "正在抓取…");
    try {
      const response = await fetch("/api/research/fetch", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ url: safeUrl }),
      });
      const data = await readJson(response);
      if (!response.ok) {
        throw new Error(data.detail || `抓取失败（${response.status}）`);
      }
      const content = typeof data.content === "string" ? data.content : "";
      if (!content.trim()) {
        throw new Error(
          "没有取到正文。目标站点可能拒绝了访问，或页面没有可提取的 Markdown。"
        );
      }
      showReading({
        title:
          data.title ||
          (info && info.title) ||
          hostnameOf(safeUrl) ||
          "未命名网页",
        url: safeUrl,
        content,
        kind: "Markdown 正文",
      });
    } catch (error) {
      showError(error && error.message ? error.message : "抓取失败，请稍后重试。");
    } finally {
      setBusy(false);
    }
  }

  function activateTab(mode, focus) {
    state.mode = mode;
    const isSearch = mode === "search";
    ui.tabSearch.classList.toggle("tab--active", isSearch);
    ui.tabFetch.classList.toggle("tab--active", !isSearch);
    ui.tabSearch.setAttribute("aria-selected", String(isSearch));
    ui.tabFetch.setAttribute("aria-selected", String(!isSearch));
    ui.tabSearch.tabIndex = isSearch ? 0 : -1;
    ui.tabFetch.tabIndex = isSearch ? -1 : 0;
    ui.panelSearch.hidden = !isSearch;
    ui.panelFetch.hidden = isSearch;
    if (focus) {
      (isSearch ? ui.queryInput : ui.fetchInput).focus();
    }
  }

  function handleTabKeys(event) {
    if (
      event.key !== "ArrowLeft" &&
      event.key !== "ArrowRight" &&
      event.key !== "Home" &&
      event.key !== "End"
    ) {
      return;
    }
    event.preventDefault();
    activateTab(state.mode === "search" ? "fetch" : "search", true);
  }

  function flashButton(button, text) {
    if (button._restoreTimer) {
      clearTimeout(button._restoreTimer);
    }
    if (!button._originalLabel) {
      button._originalLabel = button.textContent;
    }
    button.textContent = text;
    button._restoreTimer = setTimeout(() => {
      button.textContent = button._originalLabel;
      button._restoreTimer = null;
    }, 1600);
  }

  async function copyReading() {
    const content = state.reading ? state.reading.content : "";
    if (!content) return;
    let copied = false;
    try {
      await navigator.clipboard.writeText(content);
      copied = true;
    } catch (_) {
      copied = fallbackCopy(content);
    }
    flashButton(ui.copyBtn, copied ? "已复制" : "复制失败");
  }

  function fallbackCopy(text) {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "-1000px";
    document.body.appendChild(area);
    area.select();
    let copied = false;
    try {
      copied = document.execCommand("copy");
    } catch (_) {
      copied = false;
    }
    area.remove();
    return copied;
  }

  function sanitizeFilename(value) {
    const base = String(value || "page")
      .replace(/[\\/:*?"<>|\u0000-\u001f]/g, "")
      .replace(/\s+/g, "-")
      .replace(/^[.-]+|[.-]+$/g, "")
      .slice(0, 60)
      .replace(/[.-]+$/, "");
    if (!base) return "page";
    if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(base)) {
      return `page-${base}`;
    }
    return base;
  }

  function saveReading() {
    const content = state.reading ? state.reading.content : "";
    if (!content) return;
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${sanitizeFilename(state.reading.title)}.md`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    flashButton(ui.saveBtn, "已保存");
  }

  function goBack() {
    if (state.results.length) {
      showResults(state.results, state.lastQuery);
      return;
    }
    showEmpty();
  }

  function clearResults() {
    state.results = [];
    state.lastQuery = "";
    showEmpty();
    (state.mode === "search" ? ui.queryInput : ui.fetchInput).focus();
  }

  function bindEvents() {
    ui.tabSearch.addEventListener("click", () => activateTab("search", false));
    ui.tabFetch.addEventListener("click", () => activateTab("fetch", false));
    ui.tabSearch.addEventListener("keydown", handleTabKeys);
    ui.tabFetch.addEventListener("keydown", handleTabKeys);

    ui.searchForm.addEventListener("submit", (event) => {
      event.preventDefault();
      if (state.busy || !state.configured) return;
      const query = ui.queryInput.value.trim();
      if (!query) {
        showError("先输入搜索词。");
        ui.queryInput.focus();
        return;
      }
      search(query);
    });

    ui.fetchForm.addEventListener("submit", (event) => {
      event.preventDefault();
      if (state.busy || !state.configured) return;
      const url = ui.fetchInput.value.trim();
      if (!url) {
        showError("先输入网页地址。");
        ui.fetchInput.focus();
        return;
      }
      fetchPage(url);
    });

    [
      ui.queryInput,
      ui.questionInput,
      ui.localizationInput,
      ui.fetchInput,
    ].forEach((input) => {
      input.addEventListener("keydown", (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
          event.preventDefault();
          (state.mode === "search" ? ui.searchForm : ui.fetchForm).requestSubmit();
        }
      });
    });

    root.querySelectorAll(".sample").forEach((button) => {
      button.addEventListener("click", () => {
        activateTab("search", false);
        ui.queryInput.value = button.dataset.query || "";
        ui.queryInput.focus();
      });
    });

    ui.recheckBtn.addEventListener("click", loadStatus);
    ui.clearResults.addEventListener("click", clearResults);
    ui.backBtn.addEventListener("click", goBack);
    ui.copyBtn.addEventListener("click", copyReading);
    ui.saveBtn.addEventListener("click", saveReading);
  }

  function init(researchRoot) {
    if (ui) return;
    root = researchRoot || document;

    ui = {
      apiStatus: $("api-status"),
      apiStatusText: $("api-status-text"),
      recheckBtn: $("recheck-btn"),
      configBanner: $("config-banner"),
      configMessage: $("config-message"),
      tabSearch: $("tab-search"),
      tabFetch: $("tab-fetch"),
      panelSearch: $("panel-search"),
      panelFetch: $("panel-fetch"),
      searchForm: $("search-form"),
      queryInput: $("query-input"),
      countInput: $("count-input"),
      contentInput: $("content-input"),
      questionInput: $("question-input"),
      localizationInput: $("localization-input"),
      searchBtn: $("search-btn"),
      fetchForm: $("fetch-form"),
      fetchInput: $("fetch-input"),
      fetchBtn: $("fetch-btn"),
      workspace: $("workspace"),
      empty: $("workspace-empty"),
      loading: $("workspace-loading"),
      loadingText: $("loading-text"),
      error: $("workspace-error"),
      errorText: $("error-text"),
      resultsView: $("results-view"),
      resultsMeta: $("results-meta"),
      resultsList: $("results-list"),
      clearResults: $("clear-results"),
      readingView: $("reading-view"),
      backBtn: $("back-btn"),
      readingKind: $("reading-kind"),
      readingTitle: $("reading-title"),
      readingSource: $("reading-source"),
      readingContent: $("reading-content"),
      copyBtn: $("copy-btn"),
      saveBtn: $("save-btn"),
      baseUrl: $("base-url"),
    };

    bindEvents();
    showEmpty();
    loadStatus();
  }

  window.SpiderResearch = { init };

  if (document.querySelector("#research-page")) {
    init(document);
  }
})();
