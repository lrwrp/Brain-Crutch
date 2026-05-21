// Minimal, sanitizing Markdown renderer.
//
// Why hand-rolled: the project is no-bundler, no-network, local-first. A
// 200-line subset is easier to audit for XSS than a 10-line "import marked"
// would be to vet for size/dependency creep.
//
// Allowlist (per Phase 4.9 spec):
//   block:  p, h2, h3, h4, ul, ol, li, pre, code
//   inline: strong, em, code, a, img
//   anchors restricted to http(s):// or /api/attachments/ URLs
//   images restricted to /api/attachments/ URLs
// Anything outside the allowlist becomes literal text (escaped).
//
// Strategy: tokenize block-by-block, render inline within each block. Never
// pass user text through innerHTML without first escaping or wrapping it in a
// known-safe constructor.

const ALLOWED_LINK_PREFIXES = ["http://", "https://", "/api/attachments/"];
const ALLOWED_IMG_PREFIX = "/api/attachments/";

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function isAllowedLink(url) {
  return ALLOWED_LINK_PREFIXES.some((p) => url.startsWith(p));
}

function renderInline(text) {
  // Process inline patterns in priority order. Code spans are honored first
  // so their contents aren't re-interpreted as Markdown. Other patterns are
  // greedy-leftmost.
  let out = "";
  let i = 0;
  const n = text.length;

  while (i < n) {
    const ch = text[i];

    // `inline code` — preserve verbatim contents, no further Markdown
    if (ch === "`") {
      const end = text.indexOf("`", i + 1);
      if (end !== -1) {
        out += `<code>${escapeHtml(text.slice(i + 1, end))}</code>`;
        i = end + 1;
        continue;
      }
    }

    // ![alt](src) — image, but only with allowlisted prefix
    if (ch === "!" && text[i + 1] === "[") {
      const close = text.indexOf("]", i + 2);
      if (close !== -1 && text[close + 1] === "(") {
        const parenEnd = text.indexOf(")", close + 2);
        if (parenEnd !== -1) {
          const alt = text.slice(i + 2, close);
          const src = text.slice(close + 2, parenEnd).trim();
          if (src.startsWith(ALLOWED_IMG_PREFIX)) {
            out += `<img src="${escapeHtml(src)}" alt="${escapeHtml(alt)}">`;
          } else {
            // Disallowed src — render the raw Markdown text literally.
            out += escapeHtml(text.slice(i, parenEnd + 1));
          }
          i = parenEnd + 1;
          continue;
        }
      }
    }

    // [text](url) — link
    if (ch === "[") {
      const close = text.indexOf("]", i + 1);
      if (close !== -1 && text[close + 1] === "(") {
        const parenEnd = text.indexOf(")", close + 2);
        if (parenEnd !== -1) {
          const label = text.slice(i + 1, close);
          const url = text.slice(close + 2, parenEnd).trim();
          if (isAllowedLink(url)) {
            out += `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${renderInline(label)}</a>`;
          } else {
            out += escapeHtml(text.slice(i, parenEnd + 1));
          }
          i = parenEnd + 1;
          continue;
        }
      }
    }

    // **bold**
    if (ch === "*" && text[i + 1] === "*") {
      const close = text.indexOf("**", i + 2);
      if (close !== -1) {
        out += `<strong>${renderInline(text.slice(i + 2, close))}</strong>`;
        i = close + 2;
        continue;
      }
    }

    // *italic* or _italic_ — require non-space immediately after the opener
    // so that "5 * 4" doesn't accidentally start italics.
    if ((ch === "*" || ch === "_") && text[i + 1] && text[i + 1] !== " ") {
      const close = text.indexOf(ch, i + 1);
      if (close !== -1 && text[close - 1] !== " ") {
        out += `<em>${renderInline(text.slice(i + 1, close))}</em>`;
        i = close + 1;
        continue;
      }
    }

    out += escapeHtml(ch);
    i++;
  }

  return out;
}

export function renderMarkdown(src) {
  if (!src) return "";
  const lines = String(src).split(/\r?\n/);
  const out = [];
  let i = 0;
  let currentList = null;

  const flushList = () => {
    if (currentList) {
      out.push(`</${currentList.tag}>`);
      currentList = null;
    }
  };

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "") {
      flushList();
      i++;
      continue;
    }

    // Code fence — captures everything until the next ``` or EOF
    if (/^```/.test(line)) {
      flushList();
      i++;
      const codeLines = [];
      while (i < lines.length && !/^```/.test(lines[i])) {
        codeLines.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++; // skip closing fence
      out.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
      continue;
    }

    // ## h2 / ### h3 / #### h4
    const h = line.match(/^(#{2,4})\s+(.+)$/);
    if (h) {
      flushList();
      out.push(`<h${h[1].length}>${renderInline(h[2])}</h${h[1].length}>`);
      i++;
      continue;
    }

    // - item / * item
    const ul = line.match(/^[-*]\s+(.+)$/);
    if (ul) {
      if (!currentList || currentList.tag !== "ul") {
        flushList();
        out.push("<ul>");
        currentList = { tag: "ul" };
      }
      out.push(`<li>${renderInline(ul[1])}</li>`);
      i++;
      continue;
    }

    // 1. item
    const ol = line.match(/^\d+\.\s+(.+)$/);
    if (ol) {
      if (!currentList || currentList.tag !== "ol") {
        flushList();
        out.push("<ol>");
        currentList = { tag: "ol" };
      }
      out.push(`<li>${renderInline(ol[1])}</li>`);
      i++;
      continue;
    }

    // Paragraph — consume consecutive non-blank, non-block-starter lines
    flushList();
    const para = [line];
    i++;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^(#{2,4})\s+/.test(lines[i]) &&
      !/^[-*]\s+/.test(lines[i]) &&
      !/^\d+\.\s+/.test(lines[i]) &&
      !/^```/.test(lines[i])
    ) {
      para.push(lines[i]);
      i++;
    }
    out.push(`<p>${renderInline(para.join(" "))}</p>`);
  }
  flushList();
  return out.join("\n");
}

// Tooltip-safe plaintext. Strips Markdown syntax so a long note like
//   ## Plan\n- [x] [docs](https://example.com)\n
// becomes "Plan · [x] docs", suitable for an HTML `title` attribute (which
// can't render markup anyway).
export function plaintextPreview(src, maxLen = 240) {
  if (!src) return "";
  let text = String(src);
  // Remove fenced blocks entirely.
  text = text.replace(/```[\s\S]*?```/g, "[code]");
  // Inline code: keep contents.
  text = text.replace(/`([^`]+)`/g, "$1");
  // Images and links: keep alt/label.
  text = text.replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1");
  text = text.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
  // Bold/italic markers.
  text = text.replace(/\*\*([^*]+)\*\*/g, "$1");
  text = text.replace(/\*([^*]+)\*/g, "$1");
  text = text.replace(/_([^_]+)_/g, "$1");
  // Heading hashes.
  text = text.replace(/^#{2,4}\s+/gm, "");
  // List markers.
  text = text.replace(/^[-*]\s+/gm, "");
  text = text.replace(/^\d+\.\s+/gm, "");
  // Collapse newlines to a visible separator so multi-line notes are legible
  // when squeezed into a one-line tooltip.
  text = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l)
    .join(" · ");
  if (text.length > maxLen) text = text.slice(0, maxLen - 1) + "…";
  return text;
}
