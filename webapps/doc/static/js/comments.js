// 从 app.js 导入 state 和 traitsState
import { state } from './app.js';
import {
    traitsState,
    thoughtCharacteristics,
    characterCharacteristics,
    performanceCharacteristics,
    abilityCharacteristics,
    knowledgeCharacteristics,
    specialNotes
} from './traits.js';

// 生成评语
export function generateComment() {
    if (!state.currentStudent) return alert("請選擇人員！");
    if (traitsState.selectedTraits.size === 0) return alert("請先選擇指標！");

    const traitsArr = Array.from(traitsState.selectedTraits);
    const namePart = state.currentStudent.split(".")[1] || state.currentStudent;

    // 分类正面与负面特质
    const positiveTraits = [];
    const negativeTraits = [];

    // 将特定的负面特质分类
    const specialNegativeTraits = [...specialNotes, "作事精神稍欠積極"];

    traitsArr.forEach(trait => {
        if (specialNegativeTraits.includes(trait)) {
            negativeTraits.push(trait);
        } else {
            positiveTraits.push(trait);
        }
    });

    // 组合评语
    let commentText = `關於${namePart}同仁的考核意見如下：`;

    if (positiveTraits.length > 0) {
        commentText += `\n\n 1.本次考核表現佳，主要體現在：${positiveTraits.join("、")}，符合部隊要求。`;
    }

    if (negativeTraits.length > 0) {
        commentText += `\n\n 2.需加強改進： ${negativeTraits.map((t, i) =>
            i === negativeTraits.length - 1 ? "和" : "")
            .join("")
            + negativeTraits.join("、")}。`;
    }

    if (positiveTraits.length > 0 || negativeTraits.length > 0) {
        commentText += `\n\n 建議：繼續發揮優勢，並對不足之處加強培訓與指導。`;
    } else {
        commentText += "\n\n 均未達標";
    }

    // 添加到评语记录
    state.comments.push({
        student: state.currentStudent,
        comment: commentText
    });

    renderComments();
}

// 渲染评语预览
export function renderComments() {
    const previewEl = document.getElementById("commentPreview");
    previewEl.innerHTML = "";

    if (state.comments.length === 0) {
        const emptyState = document.createElement("div");
        emptyState.textContent = "目前尚無記錄";
        emptyState.style.color = "#6b7280";
        previewEl.appendChild(emptyState);
        return;
    }

    state.comments.slice().reverse().forEach(({student, comment}) => {
        const div = document.createElement("div");
        div.className = "preview-item";

        const header = document.createElement("header");
        header.textContent = student;
        header.style.fontWeight = "500";
        header.style.marginBottom = "6px";

        const content = document.createElement("pre");
        content.textContent = comment;
        content.style.whiteSpace = "pre-wrap";
        content.style.maxWidth = "100%";
        content.style.overflowX = "auto";

        div.appendChild(header);
        div.appendChild(content);

        // 将新项插入最上方
        previewEl.insertBefore(div, previewEl.firstChild);
    });
}

// 下载功能
function downloadTxt() {
    if (state.comments.length === 0) return alert("無記錄可匯出");

    const lines = state.comments.map(c => `${c.student}\t${c.comment}`);
    const blob = new Blob([lines.join("\n")], {type: "text/plain"});
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = `人員考核評語_${new Date().toISOString().slice(0,10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

function downloadCsv() {
    if (state.comments.length === 0) return alert("無記錄可匯出");

    const header = ["人員", "考核意見"];
    const rows = state.comments.map(c =>
        `"${c.student.replace(/"/g, '""')}","${c.comment.replace(/"/g, '""')}"`
    );
    const csv = [header.join(","), ...rows].join("\n");
    const blob = new Blob([csv], {type: "text/csv"});

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `人員考核評語_${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

// 绑定下载按钮事件
document.getElementById('btnDownloadTxt').addEventListener('click', downloadTxt);
document.getElementById('btnDownloadCsv').addEventListener('click', downloadCsv);

// 清除记录功能
document.getElementById('btnClearComments').addEventListener('click', () => {
    if (confirm("確定要清除所有記錄？")) {
        state.comments = [];
        renderComments();
    }
});

// 从 traits.js 和 app.js 导入的 state 和函数
import { toggleTab } from './traits.js';