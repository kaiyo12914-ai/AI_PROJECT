const API_EXTRACT = apiurl("extract/");
const API_TXT = apiurl("download/txt/");
const API_DOCX = apiurl("download/docx/");

    const $ = (id) => document.getElementById(id);
    const pdf = $("pdf");
    const out = $("out");
    const status = $("status");

    function setStatus(html) {
      status.innerHTML = html;
    }

    function getFile() {
      const f = pdf.files && pdf.files[0];
      if (!f) {
        alert("請先選擇PDF");
        return null;
      }
      return f;
    }

    async function extract() {
      const f = getFile();
      if (!f) return;

      setStatus("⏳ 擷取中（若啟動OCR會較久）...");
      out.value = "⏳ 擷取中...";

      const fd = new FormData();
      fd.append("pdf", f);
      try {
        const r = await fetch(API_EXTRACT, { method: "POST", body: fd });
        const ct = (r.headers.get("content-type") || "").toLowerCase();
        let j = null;
        if (ct.includes("application/json")) {
          j = await r.json();
        } else {
          const raw = await r.text();
          throw new Error("API 回傳非 JSON（可能路徑錯誤）: " + raw.slice(0, 80));
        }

        if (!r.ok || !j || !j.ok) {
          out.value = "";
          setStatus("<span class='err'>❌ " + ((j && j.error) || ("HTTP " + r.status)) + "</span>");
          return;
        }

        out.value = j.text || "";
        const tag = j.used_ocr ? "（已OCR）" : "（抽字）";
        setStatus(
          "<span class='ok'>✅ 完成</span>" +
            tag +
            "（" +
            (j.filename || "") +
            "，" +
            (j.chars ?? 0) +
            "字元）"
        );
      } catch (e) {
        out.value = "";
        setStatus("<span class='err'>❌ 擷取失敗：" + ((e && e.message) || "未知錯誤") + "</span>");
      }
    }

    async function dl(ep, fallback) {
      const f = getFile();
      if (!f) return;

      const fd = new FormData();
      fd.append("pdf", f);

      const r = await fetch(ep, { method: "POST", body: fd });
      if (!r.ok) {
        alert("下載失敗：" + r.status);
        return;
      }

      const b = await r.blob();

      let fn = fallback;
      const cd = r.headers.get("Content-Disposition") || "";
      const m = cd.match(/filename="([^"]+)"/i);
      if (m && m[1]) fn = m[1];

      const u = URL.createObjectURL(b);
      const a = document.createElement("a");
      a.href = u;
      a.download = fn;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(u), 800);
    }

    $("btnExtract").addEventListener("click", extract);
    $("btnTxt").addEventListener("click", () => dl(API_TXT, "output.txt"));
    $("btnDocx").addEventListener("click", () => dl(API_DOCX, "output.docx"));
