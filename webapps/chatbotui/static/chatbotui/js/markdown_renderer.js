(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.ChatbotMarkdownRenderer = api;
})(typeof globalThis !== "undefined" ? globalThis : window, function () {
  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function renderInline(text) {
    let safe = escapeHtml(text);
    safe = safe.replace(/`([^`]+)`/g, "<code>$1</code>");
    safe = safe.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    safe = safe.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    return safe;
  }

  function renderTextBlock(block) {
    const lines = String(block || "").split("\n");
    const out = [];
    let listItems = [];

    function flushList() {
      if (!listItems.length) return;
      out.push(`<ul>${listItems.map((item) => `<li>${renderInline(item)}</li>`).join("")}</ul>`);
      listItems = [];
    }

    lines.forEach((rawLine) => {
      const line = rawLine.trimEnd();
      const trimmed = line.trim();

      if (!trimmed) {
        flushList();
        return;
      }

      if (/^[-*]\s+/.test(trimmed)) {
        listItems.push(trimmed.replace(/^[-*]\s+/, ""));
        return;
      }

      flushList();

      if (/^###\s+/.test(trimmed)) {
        out.push(`<h3>${renderInline(trimmed.replace(/^###\s+/, ""))}</h3>`);
        return;
      }
      if (/^##\s+/.test(trimmed)) {
        out.push(`<h2>${renderInline(trimmed.replace(/^##\s+/, ""))}</h2>`);
        return;
      }
      if (/^#\s+/.test(trimmed)) {
        out.push(`<h1>${renderInline(trimmed.replace(/^#\s+/, ""))}</h1>`);
        return;
      }

      out.push(`<p>${renderInline(trimmed)}</p>`);
    });

    flushList();
    return out.join("");
  }

  function renderMarkdown(text) {
    const source = String(text || "").replace(/\r\n/g, "\n");
    const parts = source.split(/```/);
    const htmlParts = [];

    for (let index = 0; index < parts.length; index += 1) {
      const block = parts[index];
      if (index % 2 === 0) {
        htmlParts.push(renderTextBlock(block));
        continue;
      }

      const lines = block.split("\n");
      let language = "";
      let codeLines = lines;
      if (lines.length && /^[A-Za-z0-9_+-]+$/.test(lines[0].trim())) {
        language = lines[0].trim();
        codeLines = lines.slice(1);
      }
      const code = codeLines.join("\n").replace(/^\n+|\n+$/g, "");
      htmlParts.push(
        `<div class="code-block"><div class="code-head"><span class="code-lang">${escapeHtml(language || "text")}</span><button type="button" class="copy-code-btn" data-copy="${escapeHtml(code)}">Copy</button></div><pre><code>${escapeHtml(code)}</code></pre></div>`
      );
    }

    return htmlParts.join("") || `<p>${renderInline(source)}</p>`;
  }

  return {
    escapeHtml: escapeHtml,
    renderInline: renderInline,
    renderMarkdown: renderMarkdown,
  };
});
