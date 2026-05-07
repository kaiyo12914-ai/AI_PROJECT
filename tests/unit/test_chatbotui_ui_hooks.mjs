import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const js = fs.readFileSync("webapps/chatbotui/static/chatbotui/js/index.js", "utf8");
const html = fs.readFileSync("webapps/chatbotui/templates/chatbotui/index.html", "utf8");

test("chatbotui renders usage meta from response", () => {
  assert.match(js, /function buildMetaText\(message\)/);
  assert.match(js, /attachment_count/);
  assert.match(js, /citation_count/);
  assert.match(js, /rag_reason/);
  assert.match(js, /applyUsageMetaToLatestAssistant/);
  assert.match(js, /renderCitationList/);
  assert.match(js, /message-citations/);
});

test("chatbotui has reset profile config button", () => {
  assert.match(html, /id="resetProfileConfigBtn"/);
});
