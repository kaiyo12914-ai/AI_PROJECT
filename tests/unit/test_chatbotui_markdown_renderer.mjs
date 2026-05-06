import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const renderer = require("../../webapps/chatbotui/static/chatbotui/js/markdown_renderer.js");

test("renderMarkdown renders fenced code blocks with language and copy button", () => {
  const html = renderer.renderMarkdown("```js\nconsole.log('hi')\n```");
  assert.match(html, /class="code-block"/);
  assert.match(html, /class="code-lang">js<\/span>/);
  assert.match(html, /class="copy-code-btn"/);
  assert.match(html, /console\.log/);
});

test("renderMarkdown renders unordered lists", () => {
  const html = renderer.renderMarkdown("- one\n- two");
  assert.match(html, /<ul>/);
  assert.match(html, /<li>one<\/li>/);
  assert.match(html, /<li>two<\/li>/);
});

test("renderInline supports inline code and strong text", () => {
  const html = renderer.renderInline("Use `pip` and **run**");
  assert.match(html, /<code>pip<\/code>/);
  assert.match(html, /<strong>run<\/strong>/);
});
