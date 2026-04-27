// 特质数据
export const thoughtCharacteristics = [
    "聰敏機靈",       // Smart and quick-witted
    "個性均衡",       // Balanced personality
    "任事積極",       // Proactive in tasks
    "思維活絡",       // Agile thinking
    "樂觀進取",       // Optimistic and enterprising
    "進取心強",       // Strong drive for advancement
    "主動向上",       // Actively upward-moving
    "主動積極",       // Proactive and active
    "具企圖心與朝氣活力", // Ambitious with energy and vitality
    "作事精神稍欠積極",   // Slightly lacks work spirit
    "思慮周深",       // Deep thinking
    "參謀作業能力佳",   // Excellent staff operations ability
    "開創性較不足",    // Lacking creativity
    "決斷力稍待加強",   // Decision-making needs improvement
    "處事保守",       // Conservative in handling matters
    "應變能力待加強"   // Adaptability needs improvement
];

export const characterCharacteristics = [
    "服從命令",       // Obeys orders
    "貫徹命令",       // Follows through on commands
    "遵守規範",       // Follows rules
    "職業操守佳",     // Excellent professional integrity
    "人際關係佳",     // Good interpersonal relationships
    "服從紀律",       // Follows discipline
    "誠信與奉獻",     // Honesty and dedication
    "負責盡職",       // Responsible and diligent
    "謹守本份",       // Stays within assigned role
    "為人忠厚木訥",   // Honest but somewhat dull (直率但不圓融)
    "認真負責",       // Serious and responsible
    "奉公守法",       // Follows laws and regulations
    "任勞任怨",       // Endures hard work without complaining
    "待人誠懇踏實",   // Sincere and down-to-earth in dealing with others
    "和藹親切",       // Kind and friendly
    "個性剛直",       // Frank and straightforward (but may lack flexibility)
    "主觀意識稍強",   // Slightly strong subjective awareness (可能不夠客觀)
    "安份守己",       // Content with the status quo
    "遇事沉著",       // Calm in facing matters
    "缺乏擔當"        // Lacks initiative or courage (主動性不足)
];

export const performanceCharacteristics = [
    "成果表現佳",     // Excellent results
    "績效卓越",       // Outstanding performance
    "工作效率高",     // High work efficiency
    "圓滿達成任務",   // Fully accomplish tasks
    "對命令全力貫徹", // Follows through on commands fully
    "成效優異",       // Exceptional results
    "本職學能優異",   // Excellent core skills (本職專業能力)
    "處事主動積極",   // Proactive in handling matters
    "作事精神稍欠積極", // Slightly lacks work spirit
    "表現待加強",     // Performance needs improvement
    "工作效率待加強"   // Work efficiency needs improvement
];

export const abilityCharacteristics = [
    "本職才能精湛",       // Expertise in core skills
    "專業技術強",         // Strong professional technical ability
    "溝通能力佳",         // Excellent communication skills
    "表達能力佳",         // Strong expressive ability (口頭或書面)
    "解決問題能力",       // Problem-solving ability
    "說服力強",           // Persuasive power
    "參謀作業能力佳",     // Excellent staff/planning abilities
    "業務嫻熟",          // Business-savvy (業務熟練)
    "思維縝密",          // Analytical thinking
    "反應敏捷",          // Quick response time
    "表達伶俐",          // Articulate expression
    "協調能力佳",         // Excellent coordination skills
    "思慮清晰",          // Clear reasoning
    "個性較保守",        // Relatively conservative personality (可能影響創新)
    "表達能力待加強",     // Needs improvement in expression
    "應變能力待加強",     // Needs stronger adaptability
    "協調能力欠圓融",     // Coordination lacks smoothness (可能影響團隊合作)
    "體能待加強"          // Physical fitness needs improvement
];

export const knowledgeCharacteristics = [
    "學習能力佳",         // Strong learning ability
    "知識淵博",           // Deep knowledge base
    "專業素養高",         // High professional competence
    "專業學養豐富",       // Rich professional foundation
    "業務法律嫻熟",       // Proficient in business laws/regulations
    "學有專長",           // Specialized expertise
    "主動學習進取",       // Actively self-improving
    "思維邏輯清晰",       // Clear logical thinking,
    "學習能力不足",        // Insufficient learning ability
    "專業素養不足",        // Lacking professional foundation
    "個人學識待精進",     // Needs to deepen personal knowledge
    "學習領域待拓展",      // Should broaden study areas
    "理論與實務需更平衡", // Theory vs. practice needs balancing,
    "思維邏輯待加強"       // Logical thinking needs improvement
];

export const specialNotes = [
    "缺乏運動",            // Needs more exercise
    "應注意身心健康",      // Should pay attention to mental/physical health
    "應多安排休閒活動",    // Should schedule more leisure activities
    "缺乏生涯規劃"         // Lacks career planning
];

// 特质模块状态
let traitsState = {
    traits: [],
    selectedTraits: new Set(),
    customTraits: [],
    activeTab: 'all'
};

// 初始化特质数据
export function initTraits() {
    traitsState.traits = [
        ...thoughtCharacteristics,
        ...characterCharacteristics,
        ...performanceCharacteristics,
        ...abilityCharacteristics,
        ...knowledgeCharacteristics,
        ...specialNotes
 ];
}

// 切换分页标签
export function toggleTab(tab) {
    document.querySelectorAll('#tabs button').forEach(btn => btn.classList.remove('active'));
    document.querySelector(`#tabs button[data-tab="${tab}"]`).classList.add('active');
    traitsState.activeTab = tab;
    renderTraits();
}

// 渲染特质按钮
export function renderTraits() {
    const traitListEl = document.getElementById("traitList");
    traitListEl.innerHTML = "";

    let traitsToRender;

    switch(traitsState.activeTab) {
        case 'thought':
            traitsToRender = thoughtCharacteristics;
            break;
        case 'character':
            traitsToRender = characterCharacteristics;
            break;
        case 'performance':
            traitsToRender = performanceCharacteristics;
            break;
        case 'ability':
            traitsToRender = abilityCharacteristics;
            break;
        case 'knowledge':
            traitsToRender = knowledgeCharacteristics;
            break;
        case 'special':
            traitsToRender = specialNotes;
            break;
        default:
            traitsToRender = traitsState.traits;
    }

    traitsToRender.forEach(trait => {
        const btn = document.createElement("button");
        btn.className = "pill";
        if (traitsState.selectedTraits.has(trait)) {
            btn.classList.add("selected");

            // 设定负面特质样式
            if ([...specialNotes, "作事精神稍欠積極"].includes(trait)) {
                btn.classList.add("negative-trait");
            }
        }

        btn.textContent = trait;
        btn.addEventListener("click", () => toggleTrait(trait));
        document.getElementById('traitList').appendChild(btn);
    });

    // 渲染已选特质
    renderSelectedTraits();
}

// 切换特质选择
function toggleTrait(trait) {
    if (traitsState.selectedTraits.has(trait)) {
        traitsState.selectedTraits.delete(trait);
    } else {
        traitsState.selectedTraits.add(trait);
    }
    renderTraits();
}

// 渲染已选特质
export function renderSelectedTraits() {
    const selectedTraitsEl = document.getElementById("selectedTraits");
    selectedTraitsEl.innerHTML = "";

    if (traitsState.selectedTraits.size === 0) {
        const p = document.createElement("p");
        p.textContent = "未選擇任何指標";
        p.style.color = "#6b7280";
        selectedTraitsEl.appendChild(p);
        return;
    }

    Array.from(traitsState.selectedTraits).forEach(trait => {
        const span = document.createElement("span");
        span.className = "pill selected";

        if ([...specialNotes, "作事精神稍欠積極"].includes(trait)) {
            span.classList.add("negative-trait");
        }

        span.textContent = trait;
        // 添加删除按钮
        const deleteBtn = document.createElement("button");
        deleteBtn.innerHTML = '&times;';
        deleteBtn.style.marginLeft = '6px';
        deleteBtn.style.background = 'none';
        deleteBtn.style.border = 'none';
        deleteBtn.style.color = '#ffffff';
        deleteBtn.style.cursor = 'pointer';
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleTrait(trait);
        });

        span.appendChild(deleteBtn);
        selectedTraitsEl.appendChild(span);
    });
}

// 自定义特质功能
export function addCustomTrait() {
    const input = document.getElementById("customTraitInput");
    const value = input.value.trim();
    if (!value) return;

    if (traitsState.customTraits.length >= 10) {
        alert("自訂指標最多 10 個！");
        return;
    }

    traitsState.customTraits.push(value);
    traitsState.traits.push(value);
    input.value = "";
    document.getElementById("customTraitCount").textContent = traitsState.customTraits.length.toString();
    renderCustomTraits();

    // 如果该特质已被选中，更新状态
    if (document.querySelector(`#traitList button.selected`)?.textContent === value) {
        traitsState.selectedTraits.add(value);
    }
}

export function clearCustomTraits() {
    traitsState.customTraits = [];
    document.getElementById("customTraitCount").textContent = "0";
    renderCustomTraits();
    // 更新主特质列表
    updateMainTraitsList();
}

// 渲染自定义特质
function renderCustomTraits() {
    const customTraitListEl = document.getElementById("customTraitList");
    customTraitListEl.innerHTML = "";

    traitsState.customTraits.forEach(trait => {
        const pill = document.createElement("span");
        pill.className = "pill";
        pill.textContent = trait;

        // 如果特质已被选中，添加相应样式
        if (traitsState.selectedTraits.has(trait)) {
            pill.classList.add("selected");
        }

        // 添加删除按钮
        const deleteBtn = document.createElement("button");
        deleteBtn.innerHTML = '&times;';
        deleteBtn.style.marginLeft = '6px';
        deleteBtn.style.background = 'none';
        deleteBtn.style.border = 'none';
        deleteBtn.style.color = 'inherit';
        deleteBtn.style.cursor = 'pointer';

        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            // 从自定义特质中移除
            traitsState.customTraits.splice(traitsState.customTraits.indexOf(trait), 1);
            // 从主特质列表中移除（如果存在）
            updateMainTraitsList();
            // 从已选中状态中移除
            if (traitsState.selectedTraits.has(trait)) {
                traitsState.selectedTraits.delete(trait);
                renderSelectedTraits();
            }
            document.getElementById("customTraitCount").textContent = traitsState.customTraits.length.toString();
            renderCustomTraits();
        });

        pill.appendChild(deleteBtn);
        pill.addEventListener('click', () => toggleTrait(trait));
        customTraitListEl.appendChild(pill);
    });
}

// 更新主特质列表（移除不再存在的自定义特质）
function updateMainTraitsList() {
    traitsState.traits = [
        ...thoughtCharacteristics,
        ...characterCharacteristics,
        ...performanceCharacteristics,
        ...abilityCharacteristics,
        ...knowledgeCharacteristics,
        ...specialNotes,
        ...traitsState.customTraits
    ];
}

// 从 app.js 导入的 state 和函数
import { state } from './app.js';