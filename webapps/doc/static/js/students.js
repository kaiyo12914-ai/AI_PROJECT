// 从 app.js 导入 state
import { state } from '../app.js';

// 生成人员按钮
export function generateStudentButtons() {
    const studentListEl = document.getElementById("studentList");
    const lines = studentListEl.value.split("\n")
        .map(l => l.trim())
        .filter(Boolean);

    if (lines.length === 0) return alert("請先輸入人員列表！");

    const studentButtonsEl = document.getElementById("studentButtons");
    studentButtonsEl.innerHTML = "";
    state.currentStudent = null;

    lines.forEach(line => {
        const btn = document.createElement("button");
        btn.className = "student-btn";
        btn.textContent = line;
        btn.addEventListener("click", () => {
            // 取消所有按钮的active状态
            Array.from(studentButtonsEl.children).forEach(b =>
                b.classList.remove("active"));
            state.currentStudent = line;
            btn.classList.add("active");
        });
        studentButtonsEl.appendChild(btn);
    });

    if (lines.length > 0) {
        const firstBtn = studentButtonsEl.firstElementChild;
        if (firstBtn) {
            state.currentStudent = lines[0];
            firstBtn.classList.add("active");
        }
    }
}