import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync("webapps/chatbotui/static/chatbotui/js/index.js", "utf8");
const factory = fs.readFileSync("webapps/portal/static/portal/js/apiurl_factory.js", "utf8");
function node() {
  return { children: [], handlers: {}, classList: {
    hidden: true,
    remove() { this.hidden = false; },
    add() { this.hidden = true; },
  }, appendChild(child) { this.children.push(child); },
  addEventListener(name, handler) { this.handlers[name] = handler; } };
}
function functionSource(name) {
  const start = source.indexOf(`  function ${name}(`);
  assert.ok(start >= 0);
  return source.slice(start, source.indexOf("\n  }", start) + 4);
}
for (const prefix of ["", "/djangoai"]) {
  test(`attachment thumbnails and modal preserve prefix and authentication: ${prefix || "direct"}`, () => {
    const attachment = { id: 1, message_id: 7, filename: "paste.png", image_url: "/media/chatbotui/demo/paste.png" };
    const conversation = { attachments: [attachment] };
    const elements = { attachmentList: node(), imageModal: node(), imageModalImg: node(), imageModalExternalLink: node() };
    const document = { body: { dataset: { baseUrl: prefix } }, cookie: "", readyState: "loading", addEventListener() {}, createElement: node };
    const window = { location: { origin: "https://example.test", search: "?aaa=test-login" }, localStorage: { getItem() { return ""; }, setItem() {} } };
    const context = vm.createContext({ window, document, URL, URLSearchParams, elements,
      activeConversation: () => conversation, messageId: message => message.id });
    vm.runInContext(factory, context);
    vm.runInContext(["url", "openImageModal", "closeImageModal", "renderMessageImageAttachments", "renderAttachmentList"].map(functionSource).join("\n"), context);
    const expected = `${prefix}/media/chatbotui/demo/paste.png?aaa=test-login`;
    context.renderAttachmentList();
    const previewLink = elements.attachmentList.children[0].children[0];
    assert.equal(previewLink.href, expected);
    assert.equal(previewLink.children[0].src, expected);
    previewLink.handlers.click({ preventDefault() {} });
    assert.equal(elements.imageModalImg.src, expected);
    assert.equal(elements.imageModalExternalLink.href, expected);
    assert.equal(elements.imageModal.classList.hidden, false);
    context.closeImageModal();
    assert.equal(elements.imageModal.classList.hidden, true);
    const messageLink = context.renderMessageImageAttachments(conversation, { role: "user", id: 7 }).children[0];
    assert.equal(messageLink.href, expected);
    assert.equal(messageLink.children[0].src, expected);
    messageLink.handlers.click({ preventDefault() {} });
    assert.equal(elements.imageModalImg.src, expected);
    attachment.image_url = expected;
    context.renderAttachmentList();
    assert.equal(elements.attachmentList.children.at(-1).children[0].href, expected);
  });
}
