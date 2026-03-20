const apiurlFn = (typeof window.apiurl === "function" && window.apiurl) || ((p) => p);

const TRAIT_LIBRARY = {
    aptitude: {
        label: "資質與態度",
        dot: "🟣",
        positive: [
            "學習態度認真", "上課專心聽講", "積極參與課堂活動", "主動完成作業", "對學習充滿興趣",
            "勇於發問求知", "能自我要求進步", "學習穩定踏實", "做事負責任", "能按時完成任務",
            "對新知充滿好奇", "願意嘗試不同方法", "課堂表現積極", "能持續專注學習", "遇到困難不輕言放棄",
            "能主動訂正錯誤", "學習目標明確", "課後能自主複習", "能有效安排時間", "具良好學習習慣",
        ],
        negative: [
            "上課專注力仍需提升", "作業完成度有待加強", "學習態度偶有鬆散", "容易分心影響學習", "對學習主動性不足",
            "遇到困難時較易放棄", "作業訂正不夠確實", "時間管理能力需加強", "課堂參與度尚可提升", "學習持續力有待培養",
        ],
    },
    character: {
        label: "個性與品德",
        dot: "🟣",
        positive: [
            "個性溫和有禮", "待人誠懇友善", "具責任感", "品行端正", "誠實守信",
            "懂得尊重他人", "樂於助人", "心地善良", "具同理心", "行為舉止得體",
            "能遵守規範", "情緒穩定", "自律能力佳", "謙虛有禮", "富有耐心",
            "態度誠懇", "能反省自我", "願意改進缺點", "做事踏實穩重", "品德表現優良",
        ],
        negative: [
            "情緒管理仍需學習", "偶有衝動行為", "自我要求尚可提升", "有時較缺乏耐心", "面對挫折較易氣餒",
            "行為規範需再注意", "對他人感受關注不足", "偶有不夠專心情形", "自律能力仍待加強", "需培養更穩定態度",
        ],
    },
    social: {
        label: "團體與人際",
        dot: "🟣",
        positive: [
            "能與同學和睦相處", "具良好合作能力", "樂於參與團體活動", "願意幫助同學", "能尊重他人意見",
            "團隊合作表現佳", "人際關係良好", "溝通能力良好", "能傾聽他人想法", "具團隊精神",
            "與同學互動融洽", "願意分享資源", "能主動協助團隊", "在團體中表現積極", "能適應團體生活",
            "與同學相處愉快", "合作態度良好", "能建立良好關係", "願意接納不同意見", "團體參與度高",
        ],
        negative: [
            "與同學互動仍需提升", "合作態度尚可加強", "溝通表達需更清楚", "偶有不易融入團體", "傾聽他人意見需加強",
            "團隊合作意識不足", "參與團體活動較被動", "人際互動技巧待提升", "容易與同學產生誤會", "分享與互助意願需提升",
        ],
    },
    talent: {
        label: "專長與才藝",
        dot: "🟣",
        positive: [
            "具良好藝術表現能力", "音樂表現優秀", "美術創作能力佳", "運動表現出色", "具創意發想能力",
            "口語表達能力佳", "表演自然大方", "具良好寫作能力", "手作能力優秀", "在活動中表現亮眼",
            "具領導潛能", "科學探究能力佳", "數理能力良好", "語文表達清晰", "創意思考活躍",
            "具良好觀察力", "能展現個人特色", "學習新技能快速", "能發揮個人專長", "才藝發展表現良好",
        ],
        negative: [
            "對才藝表現信心不足", "專長發揮仍待加強", "練習投入度需提升", "表達能力尚可進步", "創意發想可再提升",
            "技能熟練度需加強", "缺乏持續練習習慣", "表現穩定性待提升", "對活動參與較被動", "發展潛力尚待激發",
        ],
    },
};

const state = {
    students: [],
    currentStudent: "",
    currentTab: "all",
    selectedTraits: new Set(),
    customTraits: [],
    comments: [],
};

const el = {
    studentList: document.getElementById("studentList"),
    importFileInput: document.getElementById("importFileInput"),
    studentButtons: document.getElementById("studentButtons"),
    traitTabs: document.getElementById("traitTabs"),
    traitList: document.getElementById("traitList"),
    customTraitInput: document.getElementById("customTraitInput"),
    customTraitList: document.getElementById("customTraitList"),
    customTraitCount: document.getElementById("customTraitCount"),
    selectedTraits: document.getElementById("selectedTraits"),
    commentPreview: document.getElementById("commentPreview"),

    btnSave: document.getElementById("btnSave"),
    btnTogglePreview: document.getElementById("btnTogglePreview"),
    btnResetAll: document.getElementById("btnResetAll"),
    btnImportFile: document.getElementById("btnImportFile"),
    btnGenerateStudents: document.getElementById("btnGenerateStudents"),
    btnResetTraits: document.getElementById("btnResetTraits"),
    btnClearCustomTraits: document.getElementById("btnClearCustomTraits"),
    btnAddCustomTrait: document.getElementById("btnAddCustomTrait"),
    btnClearSelectedTraits: document.getElementById("btnClearSelectedTraits"),
    btnGenerateComment: document.getElementById("btnGenerateComment"),
    btnClearComments: document.getElementById("btnClearComments"),
    btnDownloadTxt: document.getElementById("btnDownloadTxt"),
    btnDownloadCsv: document.getElementById("btnDownloadCsv"),
    btnDownloadWord: document.getElementById("btnDownloadWord"),
};

function parseStudentLines(text) {
    return (text || "")
        .split(/\r?\n/)
        .map((s) => s.replace(/^\s*\d+[.)、．]?\s*/, "").trim())
        .filter(Boolean);
}

function allTraitItems() {
    const out = [];
    Object.entries(TRAIT_LIBRARY).forEach(([key, group]) => {
        group.positive.forEach((name) => out.push({ id: `${key}|+|${name}`, category: key, tone: "positive", name }));
        group.negative.forEach((name) => out.push({ id: `${key}|-|${name}`, category: key, tone: "negative", name }));
    });
    state.customTraits.forEach((name) => out.push({ id: `custom|+|${name}`, category: "custom", tone: "custom", name }));
    return out;
}

function visibleTraitItems() {
    const items = allTraitItems();
    if (state.currentTab === "all") return items;
    return items.filter((x) => x.category === state.currentTab || (state.currentTab === "custom" && x.category === "custom"));
}

function renderStudentButtons() {
    el.studentButtons.innerHTML = "";
    state.students.forEach((name) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `student-btn ${name === state.currentStudent ? "active" : ""}`;
        btn.textContent = name;
        btn.onclick = () => {
            state.currentStudent = name;
            renderStudentButtons();
        };
        el.studentButtons.appendChild(btn);
    });
}

function renderTabs() {
    Array.from(el.traitTabs.querySelectorAll(".tab-btn")).forEach((btn) => {
        const tab = btn.dataset.tab;
        btn.classList.toggle("selected", tab === state.currentTab);
    });
}

function renderTraitList() {
    el.traitList.innerHTML = "";
    visibleTraitItems().forEach((item) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = `pill tone-${item.tone} cat-${item.category} ${state.selectedTraits.has(item.id) ? "selected" : ""}`;
        b.innerHTML = `<span class="dot"></span>${item.name}`;
        b.onclick = () => {
            if (state.selectedTraits.has(item.id)) {
                state.selectedTraits.delete(item.id);
            } else {
                state.selectedTraits.add(item.id);
            }
            renderTraitList();
            renderSelectedTraits();
        };
        el.traitList.appendChild(b);
    });
}

function renderCustomTraitList() {
    el.customTraitList.innerHTML = "";
    state.customTraits.forEach((name, idx) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "pill custom";
        b.textContent = `${name} ×`;
        b.onclick = () => {
            const traitId = `custom|+|${name}`;
            state.selectedTraits.delete(traitId);
            state.customTraits.splice(idx, 1);
            renderCustomTraitList();
            renderTraitList();
            renderSelectedTraits();
        };
        el.customTraitList.appendChild(b);
    });
    el.customTraitCount.textContent = String(state.customTraits.length);
}

function renderSelectedTraits() {
    const map = new Map(allTraitItems().map((x) => [x.id, x]));
    el.selectedTraits.innerHTML = "";
    Array.from(state.selectedTraits).forEach((id) => {
        const item = map.get(id);
        if (!item) return;
        const tag = document.createElement("button");
        tag.type = "button";
        tag.className = `pill selected tone-${item.tone} cat-${item.category}`;
        tag.innerHTML = `<span class="dot"></span>${item.name} ×`;
        tag.onclick = () => {
            state.selectedTraits.delete(id);
            renderTraitList();
            renderSelectedTraits();
        };
        el.selectedTraits.appendChild(tag);
    });
}


function renderPreview() {
    el.commentPreview.innerHTML = "";
    if (!state.comments.length) {
        el.commentPreview.innerHTML = '<div class="preview-empty">尚未產生評語</div>';
        return;
    }
    state.comments.forEach((item, idx) => {
        const box = document.createElement("div");
        box.className = "preview-item";
        box.innerHTML = `
            <header>
                <span>${idx + 1}. ${item.name}</span>
                <div class="actions">
                    <button class="mini-btn secondary" data-copy="${idx}">複製</button>
                    <button class="mini-btn danger" data-del="${idx}">刪除</button>
                </div>
            </header>
            <div>${item.comment.replace(/\n/g, "<br>")}</div>
        `;
        el.commentPreview.appendChild(box);
    });

    el.commentPreview.querySelectorAll("[data-copy]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const i = Number(btn.dataset.copy);
            try {
                await navigator.clipboard.writeText(state.comments[i].comment);
            } catch (_) {}
        });
    });

    el.commentPreview.querySelectorAll("[data-del]").forEach((btn) => {
        btn.addEventListener("click", () => {
            const i = Number(btn.dataset.del);
            state.comments.splice(i, 1);
            renderPreview();
        });
    });
}

function composeComment(studentName, traitTexts) {
    if (!traitTexts.length) {
        return `${studentName}同學本階段學習態度穩定，能依照課程進度完成學習任務，建議持續保持良好習慣。`;
    }

    const positives = traitTexts.filter((t) => !t.includes("需") && !t.includes("不足") && !t.includes("待"));
    const needs = traitTexts.filter((t) => !positives.includes(t));

    const p = positives.slice(0, 4).join("、");
    const n = needs.slice(0, 2).join("、");

    let out = `${studentName}同學在本階段展現${p || "穩定的學習表現"}。`;
    if (n) {
        out += `另在${n}方面可持續精進，建議透過具體練習逐步強化。`;
    }
    out += "整體而言，學習態度良好，具持續成長潛力。";
    return out;
}

function currentDownloadItems() {
    return state.comments.map((x) => ({ name: x.name, comment: x.comment }));
}

async function downloadFile(endpoint) {
    const items = currentDownloadItems();
    if (!items.length) {
        alert("目前沒有可下載評語");
        return;
    }

    const resp = await fetch(apiurlFn(endpoint), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
    });

    if (!resp.ok) {
        alert(`下載失敗：${resp.status}`);
        return;
    }

    const blob = await resp.blob();
    const cd = resp.headers.get("Content-Disposition") || "";
    const m = cd.match(/filename="?([^";]+)"?/i);
    const filename = (m && m[1]) || "comments.txt";

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

function resetAll() {
    state.students = [];
    state.currentStudent = "";
    state.currentTab = "all";
    state.selectedTraits.clear();
    state.customTraits = [];
    state.comments = [];

    el.studentList.value = "";
    el.customTraitInput.value = "";

    renderTabs();
    renderStudentButtons();
    renderTraitList();
    renderCustomTraitList();
    renderSelectedTraits();
    renderPreview();
}

el.btnGenerateStudents.addEventListener("click", () => {
    state.students = parseStudentLines(el.studentList.value);
    state.currentStudent = state.students[0] || "";
    renderStudentButtons();
});

el.btnImportFile.addEventListener("click", () => el.importFileInput.click());
el.importFileInput.addEventListener("change", async () => {
    const f = el.importFileInput.files && el.importFileInput.files[0];
    if (!f) return;
    const text = await f.text();

    if (f.name.toLowerCase().endsWith(".csv")) {
        const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
        const names = lines.map((l) => l.split(",")[0].replace(/^\d+[.)、．]?\s*/, "").replace(/^"|"$/g, "").trim()).filter(Boolean);
        el.studentList.value = names.join("\n");
    } else {
        el.studentList.value = text;
    }

    state.students = parseStudentLines(el.studentList.value);
    state.currentStudent = state.students[0] || "";
    renderStudentButtons();
});

Array.from(el.traitTabs.querySelectorAll(".tab-btn")).forEach((btn) => {
    btn.addEventListener("click", () => {
        state.currentTab = btn.dataset.tab || "all";
        renderTabs();
        renderTraitList();
    });
});

el.btnAddCustomTrait.addEventListener("click", () => {
    const v = (el.customTraitInput.value || "").trim();
    if (!v) return;
    if (state.customTraits.includes(v)) return;
    if (state.customTraits.length >= 20) {
        alert("自訂特質最多 20 項");
        return;
    }
    state.customTraits.push(v);
    el.customTraitInput.value = "";
    renderCustomTraitList();
    renderTraitList();
});

el.btnClearCustomTraits.addEventListener("click", () => {
    state.customTraits.forEach((n) => state.selectedTraits.delete(`custom|+|${n}`));
    state.customTraits = [];
    renderCustomTraitList();
    renderTraitList();
    renderSelectedTraits();
});

el.btnResetTraits.addEventListener("click", () => {
    state.selectedTraits.clear();
    renderTraitList();
    renderSelectedTraits();
});

el.btnClearSelectedTraits.addEventListener("click", () => {
    state.selectedTraits.clear();
    renderTraitList();
    renderSelectedTraits();
});

el.btnGenerateComment.addEventListener("click", () => {
    if (!state.currentStudent) {
        alert("請先建立並選擇學生");
        return;
    }

    const all = new Map(allTraitItems().map((x) => [x.id, x]));
    const traitTexts = Array.from(state.selectedTraits).map((id) => (all.get(id) || {}).name).filter(Boolean);

    const comment = composeComment(state.currentStudent, traitTexts);
    const idx = state.comments.findIndex((x) => x.name === state.currentStudent);
    if (idx >= 0) {
        state.comments[idx].comment = comment;
        state.comments[idx].traits = traitTexts;
    } else {
        state.comments.push({ name: state.currentStudent, comment, traits: traitTexts });
    }
    renderPreview();
});

el.btnClearComments.addEventListener("click", () => {
    state.comments = [];
    renderPreview();
});

el.btnDownloadTxt.addEventListener("click", () => downloadFile("/student/download/txt/"));
el.btnDownloadCsv.addEventListener("click", () => downloadFile("/student/download/csv/"));
el.btnDownloadWord.addEventListener("click", () => downloadFile("/student/download/word/"));

el.btnSave.addEventListener("click", () => {
    const payload = {
        studentList: el.studentList.value,
        customTraits: state.customTraits,
        currentTab: state.currentTab,
    };
    localStorage.setItem("student_comment_draft", JSON.stringify(payload));
});

el.btnTogglePreview.addEventListener("click", () => {
    el.commentPreview.classList.toggle("hidden");
});

el.btnResetAll.addEventListener("click", () => resetAll());

(function init() {
    try {
        const raw = localStorage.getItem("student_comment_draft");
        if (raw) {
            const d = JSON.parse(raw);
            el.studentList.value = d.studentList || "";
            state.customTraits = Array.isArray(d.customTraits) ? d.customTraits.slice(0, 20) : [];
            state.currentTab = d.currentTab || "all";
            state.students = parseStudentLines(el.studentList.value);
            state.currentStudent = state.students[0] || "";
        }
    } catch (_) {}

    renderTabs();
    renderStudentButtons();
    renderTraitList();
    renderCustomTraitList();
    renderSelectedTraits();
    renderPreview();
})();
