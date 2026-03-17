/* =========================================================
 * apiurl_factory.js
 * ---------------------------------------------------------
 * Project Standard API URL Factory
 *
 * Rules:
 * 1) baseUrl from <body data-base-url>
 * 2) never derive /djangoai prefix on client
 * 3) apiurl('node/path/') -> baseUrl + path
 * 4) when ?aaa= exists, propagate to API/fetch/links
 * ========================================================= */

(function (global) {
  "use strict";

  function _normPrefix(p) {
    p = String(p || "").trim();
    if (!p) return "";
    if (!p.startsWith("/")) p = "/" + p;
    while (p.length > 1 && p.endsWith("/")) p = p.slice(0, -1);
    return p === "/" ? "" : p;
  }

  function _getBaseUrl() {
    const body = document.body;
    if (!body || !body.dataset) return "";
    return _normPrefix(body.dataset.baseUrl || "");
  }

  function _getAaaFromCookie() {
    try {
      const m = document.cookie.match(/(?:^|; )aaa=([^;]+)/);
      return m ? decodeURIComponent(m[1]) : "";
    } catch (e) {
      return "";
    }
  }

  function _setAaaCookie(aaa) {
    if (!aaa) return;
    try {
      document.cookie = `aaa=${encodeURIComponent(aaa)}; path=/; SameSite=Lax`;
    } catch (e) {
      // ignore
    }
  }

  function _getAaa() {
    let aaa = "";
    try {
      aaa = new URLSearchParams(window.location.search).get("aaa") || "";
    } catch (e) {
      // ignore
    }

    if (!aaa) {
      try {
        aaa = window.localStorage.getItem("aaa") || "";
      } catch (e) {
        // ignore
      }
    }

    if (!aaa) {
      aaa = _getAaaFromCookie() || "";
    }

    if (aaa) {
      try { window.localStorage.setItem("aaa", aaa); } catch (e) {}
      _setAaaCookie(aaa);
    }

    return aaa;
  }

  function _appendAaa(url) {
    const aaa = _getAaa();
    if (!aaa) return url;

    try {
      const u = new URL(url, window.location.origin);
      if (u.origin !== window.location.origin) return url;
      if (!u.searchParams.get("aaa")) u.searchParams.set("aaa", aaa);
      return u.pathname + u.search + u.hash;
    } catch (e) {
      if (String(url).includes("aaa=")) return String(url);
      return String(url).includes("?")
        ? `${url}&aaa=${encodeURIComponent(aaa)}`
        : `${url}?aaa=${encodeURIComponent(aaa)}`;
    }
  }

  function apiurl(path) {
    const base = _getBaseUrl(); // "" or "/djangoai"
    let p = String(path || "").trim();

    if (!p) return _appendAaa(base || "/");

    // absolute URL -> return as-is (but still append aaa if same-origin)
    if (p.startsWith("http://") || p.startsWith("https://")) return _appendAaa(p);

    if (!p.startsWith("/")) p = "/" + p;

    // avoid double prefix
    if (base && (p === base || p.startsWith(base + "/"))) {
      p = p.slice(base.length) || "/";
      if (!p.startsWith("/")) p = "/" + p;
    }

    return _appendAaa(base + p);
  }

  // ======================================================
  // Global fetch wrapper: auto-append aaa (same-origin only)
  // ======================================================
  const nativeFetch = window.fetch ? window.fetch.bind(window) : null;
  if (nativeFetch) {
    window.fetch = function fetchWithAaa(input, init) {
      const aaa = _getAaa();
      if (!aaa) return nativeFetch(input, init);

      if (input instanceof Request) {
        const url2 = _appendAaa(input.url);
        if (url2 === input.url) return nativeFetch(input, init);

        const req = input.clone();
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

        return nativeFetch(req2, init);
      }

      const url = (input instanceof URL) ? input.toString() : String(input);
      return nativeFetch(_appendAaa(url), init);
    };
  }

  // ======================================================
  // Patch same-origin links with aaa
  // ======================================================
  function patchLinksWithAaa() {
    const aaa = _getAaa();
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
        if (u.origin !== window.location.origin) return;
        if (!u.searchParams.get("aaa")) {
          u.searchParams.set("aaa", aaa);
          a.setAttribute("href", u.pathname + u.search + u.hash);
        }
      } catch (e) {
        // ignore
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", patchLinksWithAaa);
  } else {
    patchLinksWithAaa();
  }

  // ======================================================
  // Expose
  // ======================================================
  global.apiurl = apiurl;
  global.patchLinksWithAaa = patchLinksWithAaa;
})(window);