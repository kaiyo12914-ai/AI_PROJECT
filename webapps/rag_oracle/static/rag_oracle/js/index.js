const $ = id => document.getElementById(id);

let lastRag = { answer:"", sources:[] };
let mode = "long";
window.__lastMeetingShort = "";
window.__lastMeetingLong = "";

/** ✅ 專案規範：所有 API 都用 apiUrl(path) 統一組 URL（不要手動加 node） */
const apiurlFn = (typeof window.apiurl === "function" && window.apiurl) || ((p) => p);
function apiUrl(path){
  return apiurlFn(path);
}

function mustDirective(){
  const d = ($("directive").value || "").trim();
  if(!d){
    alert("請先輸入「指裁示事項」");
    return "";
  }
  return d;
}

document.querySelectorAll(".tab").forEach(t=>{
  t.onclick = ()=>{
    document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));
    t.classList.add("active");
    mode = t.dataset.mode;
    $("genOut").textContent =
      mode==="long" ? (window.__lastMeetingLong||"") : (window.__lastMeetingShort||"");
  };
});

async function ragOnly(){
  const q = mustDirective();
  if(!q) return;

  $("btnRag").disabled = true;
  $("ragStatus").textContent = "⏳ RAG 查詢中…";
  $("ragAns").textContent = "⏳ 檢索中…";
  $("ragSrc").textContent = "";

  const fd = new FormData();
  fd.append("q", q);
  fd.append("k", $("k").value || "10");

  try{
    const r = await fetch(apiUrl("ask/"), { method:"POST", body: fd });
    const j = await r.json();
    if(!j.ok) throw new Error(j.error || "RAG 失敗");

    lastRag = { answer:j.answer||"", sources:j.sources||[] };
    $("ragStatus").innerHTML = "<span class='ok'>✅ 完成</span>";
    $("ragAns").textContent = lastRag.answer || "（無）";
    $("ragSrc").textContent = JSON.stringify(lastRag.sources, null, 2);
  }catch(e){
    $("ragStatus").innerHTML = "<span class='err'>❌ "+(e?.message||String(e))+"</span>";
  }finally{
    $("btnRag").disabled = false;
  }
}

async function genWithRag(){
  const d = mustDirective();
  if(!d) return;

  if(!lastRag.sources.length) await ragOnly();

  $("btnGen").disabled = true;
  $("genStatus").textContent = "⏳ 生成中…";
  $("genOut").textContent = "";

  try{
    const payload = {
      directive: d,
      staff: ($("staff").value||"") +
        "\n\n【RAG 檢索參考】\n" + JSON.stringify(lastRag.sources, null, 2)
    };

    // ⚠️ 這裡請填「你實際的 build API 路由」
    // - 若是 rag_oracle 內部 build，可用 "build/"
    const r = await fetch(apiUrl("build/"), {
      method:"POST",
      headers:{ "Content-Type":"application/json" },
      body: JSON.stringify(payload)
    });

    const j = await r.json();
    if(!j.ok) throw new Error(j.error || "生成失敗");

    window.__lastMeetingShort = j.short || "";
    window.__lastMeetingLong  = j.long || "";
    $("genStatus").innerHTML = "<span class='ok'>✅ 完成</span>";
    $("genOut").textContent =
      mode==="long" ? window.__lastMeetingLong : window.__lastMeetingShort;
  }catch(e){
    $("genStatus").innerHTML = "<span class='err'>❌ "+(e?.message||String(e))+"</span>";
  }finally{
    $("btnGen").disabled = false;
  }
}

$("btnRag").onclick = ragOnly;
$("btnGen").onclick = genWithRag;
