// 从 traits.js 导入特质状态
import {
    traitsState,
    renderTraits,
    renderSelectedTraits,
    updateMainTraitsList,
    clearCustomTraits as clearCustomTraitsFunc
} from './traits.js';

// 从 app.js 导入 state
import { state, saveToLocalStorage as saveToLocalStorageApp } from './app.js';

const STORAGE_KEY = "military_comment_generator";

// 初始化存储模块
export function initStorage() {
    // 绑定保存按钮事件
    document.getElementById('btnSave').addEventListener('click', saveToLocalStorage);

    // 重置所有功能
    document.getElementById('btnResetAll').addEventListener('click', resetAll);
}

// 从本地存储加载数据
export function loadFromLocalStorage() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) {
            const data = JSON.parse(raw);

            // 恢复学生列表
            document.getElementById("studentList").value = data.studentList || "";

            // 恢复评论
            state.comments = data.comments || [];

            // 恢复选中的特质
            traitsState.selectedTraits = new Set(data.selectedTraits || []);
            renderSelectedTraits();

            // 恢复自定义特质
            if (data.customTraits && Array.isArray(data.customTraits)) {
                traitsState.customTraits = data.customTraits;
                updateMainTraitsList();
                document.getElementById("customTraitCount").textContent =
                    traitsState.customTraits.length.toString();
            } else {
                clearCustomTraitsFunc();
            }

            // 重新渲染特质列表
            renderTraits();

            // 恢复评论预览
            document.getElementById('commentPreview').innerHTML = "";
            if (state.comments.length > 0) {
                state.comments.forEach(({student, comment}) => {
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
                    document.getElementById('commentPreview').appendChild(div);
                });
            }
        }
    } catch(e) {
        console.error("读取储存失败", e);
    }
}

// 保存到本地存储
export function saveToLocalStorage() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
        studentList: document.getElementById("studentList").value,
        comments: state.comments,
        selectedTraits: Array.from(traitsState.selectedTraits),
        customTraits: traitsState.customTraits
    }));
}

// 重置所有功能
export function resetAll() {
    if (!confirm("確定要清除所有設定？")) return;
    localStorage.removeItem(STORAGE_KEY);

    // 重置学生列表和按钮
    document.getElementById("studentList").value = "";
    document.getElementById("studentButtons").innerHTML = "";

    // 重置特质状态
    traitsState.selectedTraits.clear();
    clearCustomTraitsFunc();

    // 重置评论记录
    state.comments = [];
    state.currentStudent = null;

    // 重新渲染UI
    renderTraits();
    renderSelectedTraits();
    document.getElementById('commentPreview').innerHTML = "";
}