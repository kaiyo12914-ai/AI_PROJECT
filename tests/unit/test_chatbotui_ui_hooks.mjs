import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const js = fs.readFileSync("webapps/chatbotui/static/chatbotui/js/index.js", "utf8");
const html = fs.readFileSync("webapps/chatbotui/templates/chatbotui/index.html", "utf8");
const css = fs.readFileSync("webapps/chatbotui/static/chatbotui/css/index.css", "utf8");

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

test("chatbotui scrolls to the latest message after changing conversations", () => {
  assert.match(js, /scrollConversationToLatest\(\);/);
  assert.match(js, /document\.scrollingElement \|\| document\.documentElement/);
  assert.match(js, /page\.scrollTop = page\.scrollHeight/);
  assert.match(js, /window\.setTimeout\(scrollToLatest, 120\)/);
  assert.match(js, /window\.requestAnimationFrame\(scrollToLatest\)/);
});

test("chatbotui starts each page visit with a new conversation", () => {
  assert.match(js, /await loadConversations\(\);\s+await loadOllamaModels\(\);[\s\S]*?await createConversation\(\);/);
  assert.doesNotMatch(js, /if \(state\.conversations\.length === 0\) \{\s+await createConversation\(\);/);
});

test("chatbotui uploads images pasted into the message input", () => {
  assert.match(js, /function pastedImageFile\(event\)/);
  assert.match(js, /startsWith\("image\/"\)/);
  assert.match(js, /elements\.messageInput\.addEventListener\("paste"/);
  assert.match(js, /uploadAttachment\(image\)\.catch\(handleUiError\)/);
});

test("chatbotui renders pasted images with an original-size link", () => {
  assert.match(js, /function renderMessageImageAttachments\(conversation, message\)/);
  assert.match(js, /link\.target = "_blank"/);
  assert.match(js, /link\.title = "點擊放大檢視內容"/);
  assert.match(js, /message-image-attachments/);
});

test("chatbotui edits a prior message in the composer before resending", () => {
  assert.match(js, /function beginResendFromMessage\(messageIdValue\)/);
  assert.match(js, /state\.resendTargetMessageId = messageIdValue/);
  assert.match(js, /return resendFromMessage\(state\.resendTargetMessageId, text\)/);
  assert.match(js, /beginResendFromMessage\(id\)/);
});

test("chatbotui hides empty conversations from the sidebar", () => {
  assert.match(js, /const hasMessages = Number\(item\.message_count \|\| 0\) > 0/);
  assert.match(js, /if \(!hasMessages\) return false/);
});

test("chatbotui shows an animated SVG indicator while sending", () => {
  assert.match(html, /id="sendProgress"/);
  assert.match(html, /class="send-progress-spinner"/);
  assert.match(js, /elements\.sendProgress\.classList\.toggle\("hidden", !state\.sending\)/);
  assert.match(css, /@keyframes send-progress-spin/);
});test("chatbotui provides fallbackCopyText when navigator.clipboard is unavailable", () => {
  assert.match(js, /function fallbackCopyText\(text\)/);
  assert.match(js, /document\.execCommand\("copy"\)/);
  assert.match(js, /if \(!success\)/);
});
