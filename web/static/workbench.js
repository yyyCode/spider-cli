(function () {
  "use strict";

  const videoButton = document.getElementById("tool-video");
  const researchButton = document.getElementById("tool-research");
  const videoPanel = document.getElementById("panel-video");
  const researchPanel = document.getElementById("panel-research");
  const researchHost = document.getElementById("research-host");

  let researchPrepared = false;

  const TITLES = {
    video: "Spider · 视频下载器",
    research: "Spider · 研究台",
  };

  const buttons = { video: videoButton, research: researchButton };
  const panels = { video: videoPanel, research: researchPanel };

  function setActive(tool, updateUrl) {
    if (!buttonsValid()) return;

    Object.entries(buttons).forEach(([name, button]) => {
      const selected = name === tool;
      button.classList.toggle("is-active", selected);
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
    });

    Object.entries(panels).forEach(([name, panel]) => {
      panel.hidden = name !== tool;
    });

    if (tool === "research") {
      ensureResearch();
    }

    document.title = TITLES[tool];

    if (updateUrl) {
      const base = window.location.pathname + window.location.search;
      const next = tool === "research" ? `${base}#research` : base;
      window.history.replaceState(null, "", next);
    }
  }

  function buttonsValid() {
    return Boolean(videoButton && researchButton && videoPanel && researchPanel);
  }

  function toolFromHash() {
    return window.location.hash === "#research" ? "research" : "video";
  }

  function bindTabs() {
    if (!buttonsValid()) return;

    videoButton.addEventListener("click", () => setActive("video", true));
    researchButton.addEventListener("click", () => setActive("research", true));

    [videoButton, researchButton].forEach((button) => {
      button.addEventListener("keydown", (event) => {
        if (
          event.key !== "ArrowLeft" &&
          event.key !== "ArrowRight" &&
          event.key !== "Home" &&
          event.key !== "End"
        ) {
          return;
        }
        event.preventDefault();
        const next =
          event.key === "ArrowLeft" || event.key === "Home"
            ? "video"
            : "research";
        setActive(next, true);
        buttons[next].focus();
      });
    });

    window.addEventListener("hashchange", () => {
      setActive(toolFromHash(), false);
    });
  }

  async function fetchText(url) {
    const response = await fetch(url, { cache: "no-cache" });
    if (!response.ok) {
      throw new Error(`${url} 返回 HTTP ${response.status}`);
    }
    return response.text();
  }

  function ensureResearch() {
    if (researchPrepared) return;
    researchPrepared = true;
    prepareResearch();
  }

  async function prepareResearch() {
    if (!researchHost) return;

    try {
      const [markup, baseCss, embedCss] = await Promise.all([
        fetchText("/static/research.html"),
        fetchText("/static/research.css"),
        fetchText("/static/research-embed.css"),
      ]);

      const parsed = new DOMParser().parseFromString(markup, "text/html");
      const room = parsed.querySelector("main.room");
      if (!room) {
        throw new Error("研究台页面结构缺失");
      }
      if (!window.SpiderResearch) {
        throw new Error("研究台脚本未加载");
      }

      room.removeAttribute("id");
      room.classList.add("room--embedded");

      const shadow = researchHost.attachShadow({ mode: "open" });
      const style = document.createElement("style");
      style.textContent = `${baseCss}\n${embedCss}`;

      const fragment = document.createDocumentFragment();
      fragment.append(style, room);
      shadow.append(fragment);

      window.SpiderResearch.init(shadow);
    } catch (error) {
      const message = `研究台加载失败：${error.message}。请刷新页面重试。`;
      const shadow = researchHost.shadowRoot;
      if (shadow) {
        const notice = document.createElement("p");
        notice.className = "research-host__error";
        notice.setAttribute(
          "style",
          "margin:0;padding:24px;color:#f0b1a1;background:#211e1a;" +
            "border:1px dashed #e06a52;font-size:12.5px;line-height:1.7;"
        );
        notice.textContent = message;
        shadow.append(notice);
      } else {
        researchHost.classList.add("research-host--error");
        researchHost.textContent = message;
      }
    }
  }

  function boot() {
    bindTabs();
    if (buttonsValid()) {
      setActive(toolFromHash(), false);
    }
  }

  boot();
})();
