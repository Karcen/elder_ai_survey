/* ============================================================
 * ElderAI Survey Builder · 问卷设计器核心逻辑（纯前端，零依赖）
 * 负责：题目增删改 / 拖拽排序 / 逻辑跳转 / 校验 / 流程图 / 预览
 * 生成的 JSON 与 survey/questionnaire.json 结构完全一致。
 * ============================================================ */
"use strict";

/* ---------- 常量 ---------- */
const TYPE_LABELS = {
  single: "单选题", multiple: "多选题", yesno: "是否题",
  rating: "评分题", text: "文本题", number: "数字题", date: "日期题",
};
const OPTION_TYPES = ["single", "multiple", "yesno"]; // 含选项的题型
const NUMERIC_TYPES = ["number", "rating"];           // 数值型答案
const OPERATORS = {
  equals: "等于", not_equals: "不等于", contains: "包含",
  greater_than: "大于", less_than: "小于", between: "介于",
};

/* ---------- 全局状态 ---------- */
let survey = newSurvey();
let selectedId = null;

function newSurvey() {
  return {
    meta: {
      id: "survey_" + Date.now(),
      title: "未命名问卷", description: "", version: "1.0.0",
      author: "", created_at: today(), estimated_minutes: 5,
    },
    settings: { show_progress: true, allow_back: true, shuffle: false, submit_target: "END" },
    questions: [],
  };
}
function today() { return new Date().toISOString().slice(0, 10); }

/* ---------- DOM 小工具 ---------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
function h(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
let toastTimer = null;
function toast(msg, kind = "") {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast " + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 2600);
}

/* ============================================================
 * 题目模型
 * ============================================================ */
function nextQid() {
  let max = 0;
  for (const q of survey.questions) {
    const m = /^Q(\d+)$/.exec(q.id);
    if (m) max = Math.max(max, parseInt(m[1], 10));
  }
  return "Q" + (max + 1);
}

function makeQuestion(type) {
  const base = {
    id: nextQid(), type,
    title: "", description: "", required: true,
    default: null, help: "", voice_text: "",
    options: [], logic: [],
  };
  if (type === "single") base.options = [opt("a", "选项一"), opt("b", "选项二")];
  if (type === "multiple") base.options = [opt("a", "选项一"), opt("b", "选项二"), opt("c", "选项三")];
  if (type === "yesno") base.options = [opt("yes", "是"), opt("no", "否")];
  if (type === "rating") { base.scale = 5; base.min_label = "很不满意"; base.max_label = "很满意"; base.default = 3; }
  if (type === "number") { base.min = 0; base.max = 100; base.unit = ""; base.default = 0; }
  if (type === "text") { base.max_length = 200; base.default = ""; }
  if (type === "date") { base.default = ""; }
  return base;
}
function opt(value, label) { return { value, label }; }

function addQuestion(type) {
  const q = makeQuestion(type);
  survey.questions.push(q);
  selectedId = q.id;
  renderAll();
  toast(`已新增${TYPE_LABELS[type]} ${q.id}`, "ok");
}
function copyQuestion(id) {
  const idx = survey.questions.findIndex(q => q.id === id);
  if (idx < 0) return;
  const clone = JSON.parse(JSON.stringify(survey.questions[idx]));
  clone.id = nextQid();
  clone.logic = []; // 复制题不保留跳转，避免误指向
  survey.questions.splice(idx + 1, 0, clone);
  selectedId = clone.id;
  renderAll();
  toast(`已复制为 ${clone.id}`, "ok");
}
function deleteQuestion(id) {
  const idx = survey.questions.findIndex(q => q.id === id);
  if (idx < 0) return;
  if (!confirm(`确定删除题目 ${id} 吗？`)) return;
  survey.questions.splice(idx, 1);
  // 清理指向该题的跳转
  for (const q of survey.questions) q.logic = (q.logic || []).filter(r => r.goto !== id);
  if (selectedId === id) selectedId = survey.questions[Math.min(idx, survey.questions.length - 1)]?.id || null;
  renderAll();
  toast(`已删除 ${id}`);
}
function moveQuestion(fromId, toId) {
  const from = survey.questions.findIndex(q => q.id === fromId);
  let to = survey.questions.findIndex(q => q.id === toId);
  if (from < 0 || to < 0 || from === to) return;
  const [item] = survey.questions.splice(from, 1);
  to = survey.questions.findIndex(q => q.id === toId);
  survey.questions.splice(to, 0, item);
  renderAll();
}

/* ============================================================
 * 渲染：侧边栏 + 编辑区
 * ============================================================ */
function renderAll() { renderSidebar(); renderEditor(); }

function renderSidebar() {
  $("#surveyTitleMini").textContent = survey.meta.title || "未命名问卷";
  $("#qcount").textContent = survey.questions.length + " 题";
  const list = $("#qlist");
  list.innerHTML = "";
  survey.questions.forEach((q) => {
    const li = h(`
      <li class="qitem ${q.id === selectedId ? "active" : ""}" draggable="true" data-id="${q.id}">
        <span class="grip">⋮⋮</span>
        <span class="qid">${esc(q.id)}</span>
        <span class="qtype-badge">${TYPE_LABELS[q.type] || q.type}</span>
        <span class="qtitle-mini">${esc(q.title || "（未填写题目）")}</span>
        ${q.required ? '<span class="req-dot" title="必答">*</span>' : ""}
      </li>`);
    li.addEventListener("click", () => { selectedId = q.id; renderAll(); });
    wireDrag(li);
    list.appendChild(li);
  });
}

function wireDrag(li) {
  li.addEventListener("dragstart", e => {
    li.classList.add("dragging");
    e.dataTransfer.setData("text/plain", li.dataset.id);
  });
  li.addEventListener("dragend", () => {
    li.classList.remove("dragging");
    $$(".qitem").forEach(x => x.classList.remove("drop-target"));
  });
  li.addEventListener("dragover", e => { e.preventDefault(); li.classList.add("drop-target"); });
  li.addEventListener("dragleave", () => li.classList.remove("drop-target"));
  li.addEventListener("drop", e => {
    e.preventDefault();
    const fromId = e.dataTransfer.getData("text/plain");
    moveQuestion(fromId, li.dataset.id);
  });
}

function currentQuestion() { return survey.questions.find(q => q.id === selectedId) || null; }

function renderEditor() {
  const editor = $("#editor");
  const q = currentQuestion();
  if (!q) { editor.innerHTML = ""; editor.appendChild($("#emptyHint") || h('<div class="empty-hint"></div>')); ensureEmptyHint(); return; }

  editor.innerHTML = "";
  const card = h(`<div class="edit-card"></div>`);

  // 头部
  const head = h(`
    <div class="edit-head">
      <div><span class="qid-big">${esc(q.id)}</span>
        <span class="qtype-badge">${TYPE_LABELS[q.type]}</span></div>
      <div class="actions">
        <button class="btn" id="btnCopyQ">📋 复制</button>
        <button class="btn btn-danger" id="btnDelQ">🗑 删除</button>
      </div>
    </div>`);
  head.querySelector("#btnCopyQ").onclick = () => copyQuestion(q.id);
  head.querySelector("#btnDelQ").onclick = () => deleteQuestion(q.id);
  card.appendChild(head);

  // 基本字段
  card.appendChild(field("题目标题", `<textarea rows="2" data-k="title" placeholder="请输入题目">${esc(q.title)}</textarea>`));
  card.appendChild(field("题目说明", `<input type="text" data-k="description" value="${esc(q.description)}" placeholder="对题目的补充说明（可选）">`,
    "显示在题目下方"));

  // 题型 + 必答
  const meta2 = h(`<div class="field"><div class="row">
      <label>题目类型
        <select data-k="type">${Object.entries(TYPE_LABELS).map(([v, l]) =>
          `<option value="${v}" ${v === q.type ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label class="check" style="align-self:flex-end;padding-bottom:10px">
        <input type="checkbox" data-k="required" ${q.required ? "checked" : ""}> 必答题</label>
    </div></div>`);
  card.appendChild(meta2);

  // 题型特有参数
  card.appendChild(renderTypeParams(q));

  // 选项编辑（含选项的题型）
  if (OPTION_TYPES.includes(q.type)) {
    card.appendChild(h(`<div class="section-title">选项列表</div>`));
    const box = h(`<div class="options-box" id="optionsBox"></div>`);
    card.appendChild(box);
    renderOptions(q, box);
  }

  // 帮助 / 语音
  card.appendChild(h(`<div class="section-title">无障碍与提示</div>`));
  card.appendChild(field("帮助提示", `<input type="text" data-k="help" value="${esc(q.help)}" placeholder="给答题人的友好提示">`));
  card.appendChild(field("语音播报文本", `<textarea rows="2" data-k="voice_text" placeholder="留空则自动朗读题目与选项">${esc(q.voice_text)}</textarea>`,
    "老人端 TTS 会朗读这段文字"));

  // 逻辑跳转
  card.appendChild(h(`<div class="section-title">逻辑跳转</div>`));
  const logicBox = h(`<div class="logic-box" id="logicBox"></div>`);
  card.appendChild(logicBox);
  renderLogic(q, logicBox);

  editor.appendChild(card);
  bindFieldInputs(card, q);
}

function ensureEmptyHint() {
  if (!$("#emptyHint")) {
    $("#editor").innerHTML = `<div class="empty-hint" id="emptyHint">
      <div class="empty-emoji">🧓📋</div><h2>开始设计适老化问卷</h2>
      <p>点击左上角「＋ 新增题目」添加第一道题。</p></div>`;
  }
}

function field(label, inner, hint = "") {
  return h(`<div class="field"><label>${label}${hint ? `<span class="hint">${hint}</span>` : ""}</label>${inner}</div>`);
}

function renderTypeParams(q) {
  const wrap = h(`<div class="field" id="typeParams"></div>`);
  if (q.type === "rating") {
    wrap.appendChild(h(`<div class="row">
      <label>评分上限<input type="number" data-k="scale" min="2" max="10" value="${q.scale ?? 5}"></label>
      <label>最低分文字<input type="text" data-k="min_label" value="${esc(q.min_label ?? "")}" placeholder="很不满意"></label>
      <label>最高分文字<input type="text" data-k="max_label" value="${esc(q.max_label ?? "")}" placeholder="很满意"></label>
    </div>`));
  } else if (q.type === "number") {
    wrap.appendChild(h(`<div class="row">
      <label>最小值<input type="number" data-k="min" value="${q.min ?? 0}"></label>
      <label>最大值<input type="number" data-k="max" value="${q.max ?? 100}"></label>
      <label>单位<input type="text" data-k="unit" value="${esc(q.unit ?? "")}" placeholder="如：位 / 岁 / 元"></label>
    </div>`));
  } else if (q.type === "text") {
    wrap.appendChild(h(`<div class="row">
      <label>最大字数<input type="number" data-k="max_length" min="1" value="${q.max_length ?? 200}"></label></div>`));
  } else {
    return h(`<div></div>`);
  }
  return wrap;
}

/* ---------- 字段双向绑定 ---------- */
function bindFieldInputs(root, q) {
  $$("[data-k]", root).forEach(el => {
    const key = el.dataset.k;
    const evt = (el.type === "checkbox" || el.tagName === "SELECT") ? "change" : "input";
    el.addEventListener(evt, () => {
      let val = el.type === "checkbox" ? el.checked : el.value;
      if (["scale", "min", "max", "max_length"].includes(key)) val = Number(val);
      if (key === "type") return changeType(q, val);
      q[key] = val;
      if (key === "title" || key === "required") renderSidebar();
    });
  });
}

function changeType(q, newType) {
  // 保留通用字段，重置题型特有字段
  const keep = { id: q.id, title: q.title, description: q.description, required: q.required,
    help: q.help, voice_text: q.voice_text };
  const fresh = makeQuestion(newType);
  Object.assign(fresh, keep, { id: q.id });
  // 用新对象替换
  const idx = survey.questions.findIndex(x => x.id === q.id);
  survey.questions[idx] = fresh;
  renderAll();
}

/* ---------- 选项编辑 ---------- */
function renderOptions(q, box) {
  box.innerHTML = "";
  (q.options || []).forEach((o, i) => {
    const row = h(`<div class="opt-row">
      <span class="opt-idx">${i + 1}</span>
      <input class="opt-label" type="text" value="${esc(o.label)}" placeholder="选项文字（老人看到的）">
      <input class="opt-val" type="text" value="${esc(o.value)}" placeholder="选项值(英文/拼音)">
      <button class="opt-del" title="删除选项">✕</button>
    </div>`);
    row.querySelector(".opt-label").addEventListener("input", e => { o.label = e.target.value; });
    row.querySelector(".opt-val").addEventListener("input", e => { o.value = e.target.value; refreshLogicValueSelects(); });
    row.querySelector(".opt-del").onclick = () => {
      if (q.options.length <= 1) { toast("至少保留一个选项", "err"); return; }
      q.options.splice(i, 1); renderOptions(q, box); refreshLogicValueSelects();
    };
    box.appendChild(row);
  });
  const add = h(`<button class="btn" style="margin-top:6px">＋ 添加选项</button>`);
  add.onclick = () => {
    const n = q.options.length + 1;
    q.options.push(opt("opt" + n, "选项" + n));
    renderOptions(q, box); refreshLogicValueSelects();
  };
  box.appendChild(add);
}

/* ============================================================
 * 逻辑跳转编辑器（可视化，无需手写 JSON）
 * ============================================================ */
function renderLogic(q, box) {
  box.innerHTML = "";
  if (!q.logic) q.logic = [];
  if (q.logic.length === 0) {
    box.appendChild(h(`<div class="logic-empty">暂无跳转规则：默认顺序进入下一题。</div>`));
  }
  q.logic.forEach((rule, i) => box.appendChild(logicRuleRow(q, rule, i)));

  const add = h(`<button class="btn" style="margin-top:4px">＋ 添加跳转规则</button>`);
  add.onclick = () => {
    q.logic.push({ op: "equals", value: defaultLogicValue(q), goto: "END" });
    renderLogic(q, box);
  };
  box.appendChild(add);
}

function defaultLogicValue(q) {
  if (OPTION_TYPES.includes(q.type)) return q.options[0]?.value ?? "";
  return 0;
}

function logicRuleRow(q, rule, i) {
  const row = h(`<div class="logic-rule"></div>`);
  row.appendChild(h(`<span class="tag">当本题答案</span>`));

  // 运算符
  const opSel = h(`<select>${Object.entries(OPERATORS).map(([v, l]) =>
    `<option value="${v}" ${v === rule.op ? "selected" : ""}>${l}</option>`).join("")}</select>`);
  opSel.onchange = () => { rule.op = opSel.value; if (rule.op === "between" && !Array.isArray(rule.value)) rule.value = [0, 0]; renderLogic(q, row.parentElement); };
  row.appendChild(opSel);

  // 值输入（选项题用下拉；数值题用数字框；between 用两个）
  row.appendChild(buildValueInput(q, rule));

  row.appendChild(h(`<span class="tag">就跳转到</span>`));

  // 目标
  const gotoSel = h(`<select class="goto-sel"></select>`);
  fillGotoOptions(gotoSel, q.id, rule.goto);
  gotoSel.onchange = () => { rule.goto = gotoSel.value; };
  row.appendChild(gotoSel);

  const del = h(`<button class="opt-del" title="删除规则">✕</button>`);
  del.onclick = () => { q.logic.splice(i, 1); renderLogic(q, row.parentElement); };
  row.appendChild(del);
  return row;
}

function buildValueInput(q, rule) {
  const span = h(`<span style="display:flex;gap:6px;align-items:center"></span>`);
  if (rule.op === "between") {
    if (!Array.isArray(rule.value)) rule.value = [0, 0];
    const a = h(`<input type="number" value="${rule.value[0] ?? 0}" style="width:80px">`);
    const b = h(`<input type="number" value="${rule.value[1] ?? 0}" style="width:80px">`);
    a.oninput = () => { rule.value[0] = Number(a.value); };
    b.oninput = () => { rule.value[1] = Number(b.value); };
    span.append(a, h(`<span>到</span>`), b);
  } else if (OPTION_TYPES.includes(q.type)) {
    const sel = h(`<select class="logic-val-sel">${(q.options || []).map(o =>
      `<option value="${esc(o.value)}" ${o.value === rule.value ? "selected" : ""}>${esc(o.label)}</option>`).join("")}</select>`);
    sel.onchange = () => { rule.value = sel.value; };
    if (rule.value === undefined || rule.value === null) rule.value = q.options[0]?.value ?? "";
    span.appendChild(sel);
  } else {
    const inp = h(`<input type="number" value="${rule.value ?? 0}" style="width:110px">`);
    inp.oninput = () => { rule.value = Number(inp.value); };
    span.appendChild(inp);
  }
  return span;
}

function fillGotoOptions(sel, selfId, current) {
  const opts = survey.questions.filter(q => q.id !== selfId)
    .map(q => `<option value="${q.id}" ${q.id === current ? "selected" : ""}>${q.id} · ${esc((q.title || "").slice(0, 12))}</option>`);
  opts.push(`<option value="END" ${current === "END" ? "selected" : ""}>🏁 结束 / 提交</option>`);
  sel.innerHTML = opts.join("");
}
function refreshLogicValueSelects() {
  const q = currentQuestion();
  const box = $("#logicBox");
  if (q && box) renderLogic(q, box);
}

/* ============================================================
 * 问卷信息（meta）弹窗
 * ============================================================ */
function openMeta() {
  $("#metaTitle").value = survey.meta.title;
  $("#metaDesc").value = survey.meta.description;
  $("#metaVersion").value = survey.meta.version;
  $("#metaAuthor").value = survey.meta.author;
  $("#metaMinutes").value = survey.meta.estimated_minutes;
  $("#metaProgress").checked = survey.settings.show_progress;
  $("#metaBack").checked = survey.settings.allow_back;
  showModal("#modalMeta");
}
function saveMeta() {
  survey.meta.title = $("#metaTitle").value.trim() || "未命名问卷";
  survey.meta.description = $("#metaDesc").value.trim();
  survey.meta.version = $("#metaVersion").value.trim() || "1.0.0";
  survey.meta.author = $("#metaAuthor").value.trim();
  survey.meta.estimated_minutes = Number($("#metaMinutes").value) || 5;
  survey.settings.show_progress = $("#metaProgress").checked;
  survey.settings.allow_back = $("#metaBack").checked;
  renderSidebar();
}

/* ============================================================
 * 校验引擎（保存前自动检查；发现错误禁止导出）
 * ============================================================ */
function validateSurvey() {
  const errors = [], warnings = [];
  const qs = survey.questions;
  const ids = qs.map(q => q.id);

  if (qs.length === 0) errors.push("问卷为空：至少需要一道题目。");

  // 重复 ID
  const seen = {};
  ids.forEach(id => { seen[id] = (seen[id] || 0) + 1; });
  Object.entries(seen).filter(([, c]) => c > 1).forEach(([id]) => errors.push(`重复的题目 ID：${id}`));

  for (const q of qs) {
    // 空题目
    if (!q.title || !q.title.trim()) errors.push(`${q.id}：题目标题为空。`);
    // 选项校验
    if (OPTION_TYPES.includes(q.type)) {
      const n = (q.options || []).length;
      if (q.type === "yesno" && n !== 2) errors.push(`${q.id}：是否题需要正好 2 个选项。`);
      if ((q.type === "single" || q.type === "multiple") && n < 2) errors.push(`${q.id}：${TYPE_LABELS[q.type]}至少需要 2 个选项。`);
      (q.options || []).forEach((o, i) => {
        if (!o.label || !o.label.trim()) errors.push(`${q.id}：第 ${i + 1} 个选项文字为空。`);
        if (!o.value || !String(o.value).trim()) errors.push(`${q.id}：第 ${i + 1} 个选项值为空。`);
      });
      const vals = (q.options || []).map(o => o.value);
      if (new Set(vals).size !== vals.length) errors.push(`${q.id}：存在重复的选项值。`);
    }
    if (q.type === "rating" && (!q.scale || q.scale < 2)) errors.push(`${q.id}：评分上限至少为 2。`);

    // 逻辑校验
    (q.logic || []).forEach((r, i) => {
      const tag = `${q.id} 第${i + 1}条规则`;
      if (r.goto !== "END" && !ids.includes(r.goto)) errors.push(`${tag}：跳转目标 ${r.goto} 不存在。`);
      if (r.op === "between") {
        if (!Array.isArray(r.value) || r.value.length !== 2 || r.value.some(v => isNaN(Number(v))))
          errors.push(`${tag}：「介于」需要两个数值。`);
      }
      if (["greater_than", "less_than"].includes(r.op) && isNaN(Number(r.value)))
        errors.push(`${tag}：「${OPERATORS[r.op]}」的比较值必须是数字。`);
      if (NUMERIC_TYPES.includes(q.type) === false && ["greater_than", "less_than", "between"].includes(r.op)
          && OPTION_TYPES.includes(q.type))
        warnings.push(`${tag}：对选项题使用数值比较，请确认是否合理。`);
      if (OPTION_TYPES.includes(q.type) && ["equals", "not_equals", "contains"].includes(r.op)) {
        const vals = (q.options || []).map(o => o.value);
        if (!vals.includes(r.value)) warnings.push(`${tag}：比较值「${r.value}」不在选项列表中。`);
      }
    });
  }

  // 图分析：孤立题 / 死循环 / 无终点
  if (qs.length > 0 && Object.values(seen).every(c => c === 1)) {
    const graph = buildGraph();
    // 孤立题目（从首题不可达）
    const reach = bfs(graph, qs[0].id);
    qs.slice(1).forEach(q => { if (!reach.has(q.id)) errors.push(`孤立题目：${q.id} 从问卷开头无法到达。`); });
    // 无终点（无法到达 END）
    const canEnd = reverseReach(graph, "END");
    qs.forEach(q => { if (!canEnd.has(q.id)) errors.push(`无终点路径：${q.id} 无法走到问卷结束。`); });
    // 死循环（存在有向环）
    const cyc = findCycle(graph);
    if (cyc) errors.push(`检测到死循环跳转：${cyc.join(" → ")}`);
  }

  return { errors: dedupe(errors), warnings: dedupe(warnings), ok: errors.length === 0 };
}
function dedupe(a) { return Array.from(new Set(a)); }

/* 构建跳转图：节点=题目 id + "END" */
function buildGraph() {
  const qs = survey.questions;
  const g = {};
  qs.forEach((q, i) => {
    const edges = new Set();
    (q.logic || []).forEach(r => edges.add(r.goto === "END" ? "END" : r.goto));
    // 顺序兜底边（无规则匹配时进入下一题）
    edges.add(i < qs.length - 1 ? qs[i + 1].id : "END");
    g[q.id] = Array.from(edges).filter(t => t === "END" || qs.some(x => x.id === t));
  });
  g["END"] = [];
  return g;
}
function bfs(g, start) {
  const seen = new Set([start]), stack = [start];
  while (stack.length) for (const n of (g[stack.pop()] || [])) if (!seen.has(n)) { seen.add(n); stack.push(n); }
  return seen;
}
function reverseReach(g, target) {
  const rev = {}; Object.keys(g).forEach(k => rev[k] = []);
  Object.entries(g).forEach(([u, vs]) => vs.forEach(v => { (rev[v] = rev[v] || []).push(u); }));
  return bfs(rev, target);
}
function findCycle(g) {
  const WHITE = 0, GRAY = 1, BLACK = 2, color = {}, parent = {};
  Object.keys(g).forEach(k => color[k] = WHITE);
  let cycle = null;
  function dfs(u) {
    color[u] = GRAY;
    for (const v of g[u] || []) {
      if (color[v] === WHITE) { parent[v] = u; if (dfs(v)) return true; }
      else if (color[v] === GRAY) { // 回边 → 环
        cycle = [v]; let x = u;
        while (x !== v && x !== undefined) { cycle.push(x); x = parent[x]; }
        cycle.push(v); cycle.reverse(); return true;
      }
    }
    color[u] = BLACK; return false;
  }
  for (const n of Object.keys(g)) if (color[n] === WHITE && dfs(n)) break;
  return cycle;
}

function showValidation() {
  const { errors, warnings } = validateSurvey();
  const body = $("#validateBody");
  body.innerHTML = "";
  if (errors.length === 0 && warnings.length === 0) {
    body.appendChild(h(`<div class="v-item v-ok">🎉 校验通过，没有发现问题，可以放心导出。</div>`));
  } else {
    errors.forEach(e => body.appendChild(h(`<div class="v-item v-error">❌ ${esc(e)}</div>`)));
    warnings.forEach(w => body.appendChild(h(`<div class="v-item v-warn">⚠️ ${esc(w)}</div>`)));
    if (errors.length === 0)
      body.insertBefore(h(`<div class="v-item v-ok">✅ 无致命错误，可以导出（建议处理以上提醒）。</div>`), body.firstChild);
  }
  showModal("#modalValidate");
  return errors.length === 0;
}

/* ============================================================
 * 导入 / 导出
 * ============================================================ */
function exportJSON() {
  const { errors } = validateSurvey();
  if (errors.length > 0) { showValidation(); toast("校验未通过，已阻止导出", "err"); return; }
  survey.meta.created_at = survey.meta.created_at || today();
  const data = JSON.stringify(survey, null, 2);
  const blob = new Blob([data], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "questionnaire.json";
  a.click();
  URL.revokeObjectURL(a.href);
  toast("已导出 questionnaire.json，请替换到 survey/ 目录", "ok");
}

function doImport() {
  const text = $("#importText").value.trim();
  const finish = (raw) => {
    try {
      const obj = JSON.parse(raw);
      if (!obj.questions || !Array.isArray(obj.questions)) throw new Error("缺少 questions 数组");
      survey = normalizeSurvey(obj);
      selectedId = survey.questions[0]?.id || null;
      hideModal("#modalImport");
      renderAll();
      toast(`已导入《${survey.meta.title}》，共 ${survey.questions.length} 题`, "ok");
    } catch (e) { toast("导入失败：" + e.message, "err"); }
  };
  if (text) return finish(text);
  const file = $("#importFile").files[0];
  if (!file) { toast("请选择文件或粘贴 JSON", "err"); return; }
  const reader = new FileReader();
  reader.onload = () => finish(reader.result);
  reader.readAsText(file, "utf-8");
}

function normalizeSurvey(obj) {
  const s = newSurvey();
  Object.assign(s.meta, obj.meta || {});
  Object.assign(s.settings, obj.settings || {});
  s.questions = (obj.questions || []).map(q => ({
    id: q.id, type: q.type || "single", title: q.title || "",
    description: q.description || "", required: q.required !== false,
    default: q.default ?? null, help: q.help || "", voice_text: q.voice_text || "",
    options: q.options || [], logic: q.logic || [],
    ...(q.scale !== undefined ? { scale: q.scale, min_label: q.min_label, max_label: q.max_label } : {}),
    ...(q.min !== undefined ? { min: q.min, max: q.max, unit: q.unit } : {}),
    ...(q.max_length !== undefined ? { max_length: q.max_length } : {}),
  }));
  return s;
}

/* ============================================================
 * 流程图（自动生成）
 * ============================================================ */
function showFlow() {
  const body = $("#flowBody");
  body.innerHTML = "";
  if (survey.questions.length === 0) { body.appendChild(h(`<div class="muted">暂无题目</div>`)); showModal("#modalFlow"); return; }
  survey.questions.forEach((q, i) => {
    body.appendChild(h(`<div class="flow-node"><span class="fn-id">${q.id}</span> · ${esc((q.title || "未命名").slice(0, 22))}
      <div class="muted">${TYPE_LABELS[q.type]}</div></div>`));
    (q.logic || []).forEach(r => {
      const label = describeRule(q, r);
      const tgt = r.goto === "END" ? "🏁 结束" : r.goto;
      body.appendChild(h(`<div class="flow-branch">${esc(label)} → ${esc(tgt)}</div>`));
    });
    const next = i < survey.questions.length - 1 ? survey.questions[i + 1].id : "🏁 结束";
    body.appendChild(h(`<div class="flow-arrow">↓ <span class="muted">默认 → ${esc(next)}</span></div>`));
  });
  body.appendChild(h(`<div class="flow-node flow-end">🏁 问卷结束</div>`));
  showModal("#modalFlow");
}
function describeRule(q, r) {
  if (r.op === "between") return `若 ${OPERATORS[r.op]} ${r.value?.[0]}~${r.value?.[1]}`;
  let v = r.value;
  if (OPTION_TYPES.includes(q.type)) { const o = (q.options || []).find(o => o.value === r.value); if (o) v = o.label; }
  return `若答案${OPERATORS[r.op]}「${v}」`;
}

/* ============================================================
 * 预览：模拟真实答题（逻辑跳转 + 语音）
 * ============================================================ */
let pv = { answers: {}, history: [], current: null };

function startPreview() {
  if (survey.questions.length === 0) { toast("请先添加题目", "err"); return; }
  const { errors } = validateSurvey();
  if (errors.length) { showValidation(); return; }
  pv = { answers: {}, history: [], current: survey.questions[0].id };
  showModal("#modalPreview");
  renderPreview();
}

function renderPreview() {
  const body = $("#previewBody");
  body.innerHTML = "";
  if (pv.current === "END") {
    body.appendChild(h(`<div class="pv-done"><div class="big">🎉</div><h2>问卷完成！</h2>
      <p class="muted">共回答 ${Object.keys(pv.answers).length} 题。这是老人端真实流程的模拟。</p></div>`));
    $("#previewProgress").textContent = "已完成";
    $("#btnNextQ").textContent = "重新预览";
    $("#btnPrevQ").disabled = pv.history.length === 0;
    return;
  }
  const q = survey.questions.find(x => x.id === pv.current);
  const idx = survey.questions.findIndex(x => x.id === pv.current);
  $("#previewProgress").textContent = `第 ${idx + 1} / ${survey.questions.length} 题`;
  $("#btnNextQ").textContent = "下一题 →";
  $("#btnPrevQ").disabled = pv.history.length === 0;

  body.appendChild(h(`<div class="pv-title">${esc(q.title || "（未命名题目）")} ${q.required ? '<span style="color:#e11d48">*</span>' : ""}</div>`));
  if (q.description) body.appendChild(h(`<div class="pv-desc">${esc(q.description)}</div>`));
  body.appendChild(renderPreviewInput(q));
  if (q.help) body.appendChild(h(`<div class="pv-help">💡 ${esc(q.help)}</div>`));
  speakQuestion(q);
}

function renderPreviewInput(q) {
  const wrap = h(`<div></div>`);
  const cur = pv.answers[q.id];
  if (q.type === "single" || q.type === "yesno") {
    (q.options || []).forEach(o => {
      const b = h(`<button class="pv-option ${cur === o.value ? "selected" : ""}">${esc(o.label)}</button>`);
      b.onclick = () => { pv.answers[q.id] = o.value; renderPreview(); };
      wrap.appendChild(b);
    });
  } else if (q.type === "multiple") {
    const set = new Set(Array.isArray(cur) ? cur : []);
    (q.options || []).forEach(o => {
      const on = set.has(o.value);
      const b = h(`<button class="pv-option ${on ? "selected" : ""}">${on ? "☑" : "☐"} ${esc(o.label)}</button>`);
      b.onclick = () => { on ? set.delete(o.value) : set.add(o.value); pv.answers[q.id] = Array.from(set); renderPreview(); };
      wrap.appendChild(b);
    });
  } else if (q.type === "rating") {
    const stars = h(`<div class="pv-stars"></div>`);
    const val = Number(cur ?? q.default ?? 0);
    for (let i = 1; i <= (q.scale || 5); i++) {
      const s = h(`<span class="pv-star ${i <= val ? "on" : ""}">★</span>`);
      s.onclick = () => { pv.answers[q.id] = i; renderPreview(); };
      stars.appendChild(s);
    }
    wrap.appendChild(stars);
    wrap.appendChild(h(`<div class="muted">${esc(q.min_label || "")} … ${esc(q.max_label || "")}（当前：${val}）</div>`));
  } else if (q.type === "number") {
    const inp = h(`<input class="pv-input" type="number" value="${cur ?? q.default ?? ""}" placeholder="请输入数字">`);
    inp.oninput = () => { pv.answers[q.id] = inp.value === "" ? null : Number(inp.value); };
    wrap.appendChild(inp);
    if (q.unit) wrap.appendChild(h(`<span style="font-size:20px"> ${esc(q.unit)}</span>`));
  } else if (q.type === "date") {
    const inp = h(`<input class="pv-input" type="date" value="${esc(cur ?? "")}">`);
    inp.oninput = () => { pv.answers[q.id] = inp.value; };
    wrap.appendChild(inp);
  } else { // text
    const inp = h(`<textarea class="pv-input" rows="3" maxlength="${q.max_length || 500}" placeholder="请输入">${esc(cur ?? "")}</textarea>`);
    inp.oninput = () => { pv.answers[q.id] = inp.value; };
    wrap.appendChild(inp);
  }
  return wrap;
}

function previewNext() {
  if (pv.current === "END") { startPreview(); return; }
  const q = survey.questions.find(x => x.id === pv.current);
  const ans = pv.answers[q.id];
  if (q.required && (ans === undefined || ans === null || ans === "" || (Array.isArray(ans) && ans.length === 0))) {
    toast("这是必答题，请先作答", "err"); return;
  }
  pv.history.push(pv.current);
  pv.current = computeNext(q, ans);
  renderPreview();
}
function previewPrev() {
  if (pv.history.length === 0) return;
  pv.current = pv.history.pop();
  renderPreview();
}

/* 逻辑跳转求值（与 Python questionnaire_engine 保持一致） */
function computeNext(q, answer) {
  for (const r of (q.logic || [])) {
    if (evalRule(r, answer)) return r.goto;
  }
  const idx = survey.questions.findIndex(x => x.id === q.id);
  return idx < survey.questions.length - 1 ? survey.questions[idx + 1].id : "END";
}
function evalRule(r, answer) {
  const num = Number(answer);
  switch (r.op) {
    case "equals": return Array.isArray(answer) ? answer.includes(r.value) : String(answer) === String(r.value);
    case "not_equals": return Array.isArray(answer) ? !answer.includes(r.value) : String(answer) !== String(r.value);
    case "contains": return Array.isArray(answer) ? answer.includes(r.value) : String(answer ?? "").includes(String(r.value));
    case "greater_than": return !isNaN(num) && num > Number(r.value);
    case "less_than": return !isNaN(num) && num < Number(r.value);
    case "between": return !isNaN(num) && Array.isArray(r.value) && num >= Number(r.value[0]) && num <= Number(r.value[1]);
    default: return false;
  }
}

/* ---------- 语音播报（浏览器 TTS） ---------- */
function speakQuestion(q) {
  if (!("speechSynthesis" in window)) return;
  // 自动重读：进入题目即朗读（可通过“朗读”按钮手动触发）
}
function speakCurrent() {
  if (!("speechSynthesis" in window)) { toast("当前浏览器不支持语音", "err"); return; }
  const q = survey.questions.find(x => x.id === pv.current);
  if (!q) return;
  let text = q.voice_text;
  if (!text) {
    text = q.title;
    if (OPTION_TYPES.includes(q.type)) text += "。选项有：" + (q.options || []).map(o => o.label).join("，");
  }
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "zh-CN"; u.rate = 0.9;
  window.speechSynthesis.speak(u);
}

/* ============================================================
 * 弹窗辅助
 * ============================================================ */
function showModal(sel) { $(sel).classList.remove("hidden"); }
function hideModal(sel) { $(sel).classList.add("hidden"); }

/* ============================================================
 * 事件绑定
 * ============================================================ */
function init() {
  // 新增题目菜单
  const addMenu = $("#addMenu");
  $("#btnAddMenu").onclick = (e) => { e.stopPropagation(); addMenu.classList.toggle("hidden"); };
  $$("#addMenu div").forEach(d => d.onclick = () => { addMenu.classList.add("hidden"); addQuestion(d.dataset.type); });
  document.addEventListener("click", () => addMenu.classList.add("hidden"));

  // 工具栏
  $("#btnMeta").onclick = openMeta;
  $("#btnImport").onclick = () => { $("#importText").value = ""; showModal("#modalImport"); };
  $("#btnFlow").onclick = showFlow;
  $("#btnValidate").onclick = showValidation;
  $("#btnPreview").onclick = startPreview;
  $("#btnExport").onclick = exportJSON;

  // 弹窗关闭
  $$("[data-close]").forEach(b => b.onclick = () => {
    const modal = b.closest(".modal");
    if (modal.id === "modalMeta") saveMeta();
    modal.classList.add("hidden");
  });
  $$(".modal").forEach(m => m.addEventListener("click", e => { if (e.target === m) m.classList.add("hidden"); }));

  // 导入 / 预览导航 / 语音
  $("#btnDoImport").onclick = doImport;
  $("#btnNextQ").onclick = previewNext;
  $("#btnPrevQ").onclick = previewPrev;
  $("#btnSpeak").onclick = speakCurrent;

  // 载入示例问卷（首次打开有内容可看）
  loadSampleOrEmpty();
  renderAll();
}

function loadSampleOrEmpty() {
  // 内置一个最小示例，方便初次使用者理解
  survey = normalizeSurvey({
    meta: { title: "示例问卷（可删除后重建）", description: "演示单选 + 逻辑跳转", author: "课题组" },
    questions: [
      { id: "Q1", type: "yesno", title: "您平时使用智能手机吗？", required: true,
        options: [{ value: "yes", label: "是" }, { value: "no", label: "否" }],
        logic: [{ op: "equals", value: "no", goto: "Q3" }] },
      { id: "Q2", type: "single", title: "您每天使用手机多长时间？", required: true,
        options: [{ value: "lt1", label: "1小时以内" }, { value: "1_3", label: "1到3小时" }, { value: "gt3", label: "3小时以上" }] },
      { id: "Q3", type: "rating", title: "您对智能设备的总体满意度？", required: true, scale: 5, min_label: "很不满意", max_label: "很满意", default: 3 },
    ],
  });
  selectedId = survey.questions[0].id;
}

document.addEventListener("DOMContentLoaded", init);
