/* webapps/portal/static/portal/aaa_fetch.js */
/* 全站共用：自動把 ?aaa=xxx 附加到所有 fetch()（覆寫 window.fetch） */

(function () {
  function getAaa() {
    try {
      return new URLSearchParams(window.location.search).get("aaa") || "";
    } catch (e) {
      return "";
    }
  }

  function appendAaaToUrl(url, aaa) {
    if (!aaa) return url;

    try {
      const u = new URL(url, window.location.origin);
      if (!u.searchParams.get("aaa")) u.searchParams.set("aaa", aaa);
      return u.toString();
    } catch (e) {
      if (String(url).includes("aaa=")) return String(url);
      return String(url).includes("?")
        ? `${url}&aaa=${encodeURIComponent(aaa)}`
        : `${url}?aaa=${encodeURIComponent(aaa)}`;
    }
  }

  // ✅ 先備份「原生 fetch」，避免覆寫後遞迴
  const nativeFetch = window.fetch.bind(window);

  async function fetchWithAaa(input, init) {
    const aaa = getAaa();

    // 1) input 是 Request 物件
    if (input instanceof Request) {
      const url2 = appendAaaToUrl(input.url, aaa);

      // 用 clone() 避免 body stream 被喫掉
      const req = input.clone();

      // GET/HEAD 不要帶 body
      const method = (req.method || "GET").toUpperCase();
      const body = (method === "GET" || method === "HEAD") ? undefined : req.body;

      const req2 = new Request(url2, {
        method: req.method,
        headers: req.headers,
        body,
        mode: req.mode,
        credentials: req.credentials,
        cache: req.cache,
        redirect: req.redirect,
        referrer: req.referrer,
        referrerPolicy: req.referrerPolicy,
        integrity: req.integrity,
        keepalive: req.keepalive,
        signal: req.signal,
      });

      // ✅ 用 nativeFetch，不要用 fetch（否則遞迴）
      return nativeFetch(req2, init);
    }

    // 2) input 是 string 或 URL
    const url = (input instanceof URL) ? input.toString() : String(input);
    const finalUrl = appendAaaToUrl(url, aaa);

    // ✅ 用 nativeFetch，不要用 fetch（否則遞迴）
    return nativeFetch(finalUrl, init);
  }

  // 讓全站可用
  window.getAaa = getAaa;
  window.fetchWithAaa = fetchWithAaa;

  // 把頁面上的 <a href="..."> 自動補 aaa（你 portal 入口很需要）
  window.patchLinksWithAaa = function patchLinksWithAaa() {
    const aaa = getAaa();
    if (!aaa) return;

    document.querySelectorAll("a[href]").forEach((a) => {
      const href = a.getAttribute("href") || "";
      if (
        !href ||
        href.startsWith("#") ||
        href.startsWith("mailto:") ||
        href.startsWith("tel:") ||
        href.startsWith("javascript:")
      ) return;

      try {
        const u = new URL(href, window.location.origin);
        // 外部連結不動
        if (u.origin !== window.location.origin) return;

        if (!u.searchParams.get("aaa")) {
          u.searchParams.set("aaa", aaa);
          a.setAttribute("href", u.pathname + u.search + u.hash);
        }
      } catch (e) {
        // ignore
      }
    });
  };

  // =========================================================
  // ✅ 全站覆寫 fetch：完全不用改你原本大量 fetch()
  // =========================================================
  window.fetch = function (input, init) {
    return fetchWithAaa(input, init);
  };
})();
