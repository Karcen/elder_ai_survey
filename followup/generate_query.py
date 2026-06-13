#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「学生随访查询页」query.html（纯前端，任务2）。

读取分配结果 allocation.json + 统一短信模板，为每位受试者把模板里的
{姓名}/{name} 替换成受试者姓名，得到逐人短信，并把数据 + 主题 CSS 全部
内联进一个自包含的 query.html。学生打开后输入自己的姓名即可查询，
支持 tel: 一键拨号、sms: 一键发短信（正文已填好）。

每次需要更换短信内容时，重新运行本脚本生成新的 query.html。

用法：
    python generate_query.py \
        --allocation data/allocation.json \
        --sms-file data/sms_template.txt \
        --out query.html
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SMS = "{姓名}您好，我是适老化调研项目的随访人员，想跟您确认一下问卷回访事宜，方便时请回复，谢谢！"


def render_sms(template: str, name: str) -> str:
    """把模板中的姓名占位替换为受试者姓名。"""
    return (template.replace("{姓名}", name)
                    .replace("{name}", name)
                    .replace("{Name}", name))


def build_html(allocation: dict, sms_template: str, css: str) -> str:
    students = allocation.get("students", [])
    assignments = allocation.get("assignments", [])

    # 逐人短信
    for a in assignments:
        a["sms"] = render_sms(sms_template, a.get("subject_name", ""))

    data = {
        "generated_at": allocation.get("generated_at", ""),
        "sms_template": sms_template,
        "students": students,
        "assignments": assignments,
    }
    data_json = json.dumps(data, ensure_ascii=False)

    return (TEMPLATE
            .replace("/*__CSS__*/", css)
            .replace("/*__DATA__*/", data_json))


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>学生随访查询</title>
<style>
/*__CSS__*/
/* 查询页专属 */
.subject-card { border:1px solid var(--border); border-radius:var(--radius); padding:16px; }
.subject-card + .subject-card { margin-top:12px; }
.subject-head { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
.avatar { width:40px; height:40px; border-radius:50%; background:var(--accent-soft); color:var(--accent);
  display:grid; place-items:center; font-size:18px; flex:none; }
.sms-box { margin-top:12px; background:var(--surface-2); border:1px solid var(--border);
  border-radius:var(--radius-sm); padding:10px 12px; font-size:13px; color:var(--muted); }
.actions { display:flex; gap:8px; flex-wrap:wrap; }
.big-search { font-size:16px; padding:12px 14px; }
</style>
</head>
<body>
<div class="topbar">
  <div class="brand">
    <div class="logo">🔎</div>
    <div>
      <h1>学生随访查询</h1>
      <div class="sub">输入你的姓名，查看分配给你的随访任务</div>
    </div>
  </div>
  <button class="icon-btn" id="themeBtn" title="切换主题">🌙</button>
</div>

<div class="wrap">
  <div class="card">
    <label for="who">你的姓名</label>
    <div class="row">
      <input type="search" id="who" class="big-search" list="studentList"
             placeholder="例如：张伟" autocomplete="off" style="flex:1; min-width:200px">
      <datalist id="studentList"></datalist>
      <button class="btn primary" id="goBtn">查询</button>
    </div>
    <div class="statbar" style="margin-top:14px">
      <span class="pill" id="myCount" style="display:none">我的任务 <b>0</b></span>
      <span class="hint" id="genAt"></span>
    </div>
  </div>

  <div class="card" id="resultCard" style="display:none">
    <div class="row">
      <h2 id="resultTitle" style="margin:0">随访任务</h2>
      <span class="spacer"></span>
      <button class="btn sm" id="copyAllPhones">复制全部电话</button>
    </div>
    <div id="list" style="margin-top:14px"></div>
  </div>
</div>

<div class="foot">随访子系统 · 学生查询 · ElderAI Survey Platform</div>
<div class="toast" id="toast"></div>

<script>
const DATA = /*__DATA__*/;

/* 主题 */
const TK='followup-theme';
function applyTheme(t){ document.documentElement.setAttribute('data-theme',t);
  document.getElementById('themeBtn').textContent = t==='dark'?'☀️':'🌙'; localStorage.setItem(TK,t); }
applyTheme(localStorage.getItem(TK)||'light');
document.getElementById('themeBtn').onclick=()=>applyTheme(
  document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark');

/* 提示 */
let tt; function toast(m){ const e=document.getElementById('toast'); e.textContent=m; e.classList.add('show');
  clearTimeout(tt); tt=setTimeout(()=>e.classList.remove('show'),2000); }

function esc(s){ return (s??'').toString().replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

/* 初始化 */
document.getElementById('genAt').textContent = DATA.generated_at
  ? '名单生成时间：' + DATA.generated_at.slice(0,16).replace('T',' ') : '';
document.getElementById('studentList').innerHTML =
  DATA.students.map(s=>`<option value="${esc(s.student_name)}">`).join('');

function query(){
  const name = document.getElementById('who').value.trim();
  if (!name){ toast('请输入你的姓名'); return; }
  const mine = DATA.assignments.filter(a => a.student_name === name);
  const card = document.getElementById('resultCard');
  const myCount = document.getElementById('myCount');
  card.style.display = '';
  document.getElementById('resultTitle').textContent = `${name} 的随访任务`;
  myCount.style.display=''; myCount.querySelector('b').textContent = mine.length;

  const list = document.getElementById('list');
  if (!mine.length){
    // 是否查无此人
    const known = DATA.students.some(s=>s.student_name===name);
    list.innerHTML = `<div class="empty"><span class="big">${known?'🎉':'🤔'}</span>${
      known ? '你名下暂无随访任务' : '没有找到这个姓名，请确认与名单一致'}</div>`;
    return;
  }
  list.innerHTML = mine.map(a => {
    const tel = (a.phone||'').replace(/[^0-9+]/g,'');
    const smsHref = `sms:${tel}?body=${encodeURIComponent(a.sms||'')}`;
    return `
    <div class="subject-card">
      <div class="subject-head">
        <div class="row" style="gap:12px">
          <div class="avatar">👤</div>
          <div>
            <div style="font-weight:650; font-size:16px">${esc(a.subject_name)}</div>
            <div class="mono muted">${esc(a.phone)}${a.note?' · '+esc(a.note):''}</div>
          </div>
        </div>
        <div class="actions">
          <a class="btn primary sm" href="tel:${tel}">📞 打电话</a>
          <a class="btn sm" href="${smsHref}">💬 发短信</a>
          <button class="btn ghost sm" onclick="copy('${tel}')">复制电话</button>
        </div>
      </div>
      <div class="sms-box">
        <b style="color:var(--text)">短信内容：</b> ${esc(a.sms)}
        <button class="btn ghost sm" style="margin-left:8px" onclick='copyText(${JSON.stringify(a.sms)})'>复制短信</button>
      </div>
    </div>`;
  }).join('');
}
function copy(t){ copyText(t); }
function copyText(t){ navigator.clipboard.writeText(t).then(()=>toast('已复制')).catch(()=>toast('复制失败')); }
document.getElementById('copyAllPhones').onclick=()=>{
  const name=document.getElementById('who').value.trim();
  const phones=DATA.assignments.filter(a=>a.student_name===name).map(a=>a.phone).join(',');
  copyText(phones);
};
document.getElementById('goBtn').onclick=query;
document.getElementById('who').addEventListener('keydown',e=>{ if(e.key==='Enter') query(); });
</script>
</body>
</html>
"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="生成学生随访查询页 query.html")
    p.add_argument("--allocation", default=str(HERE / "data" / "allocation.json"),
                   help="分配结果 JSON（allocation.html 导出）")
    p.add_argument("--sms-file", default=None, help="短信模板文本文件（含 {姓名} 占位）")
    p.add_argument("--sms", default=None, help="直接给出短信模板文本（优先于 --sms-file）")
    p.add_argument("--out", default=str(HERE / "query.html"), help="输出 HTML 路径")
    args = p.parse_args(argv)

    alloc_p = Path(args.allocation)
    if not alloc_p.exists():
        print(f"❌ 找不到分配文件：{alloc_p}\n   请先在分配系统导出 allocation.json。", file=sys.stderr)
        return 1
    try:
        allocation = json.loads(alloc_p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"❌ allocation.json 解析失败：{exc}", file=sys.stderr)
        return 1

    if args.sms is not None:
        sms_template = args.sms
    elif args.sms_file and Path(args.sms_file).exists():
        sms_template = Path(args.sms_file).read_text(encoding="utf-8").strip()
    else:
        sms_template = DEFAULT_SMS
    if not sms_template.strip():
        sms_template = DEFAULT_SMS

    css_path = HERE / "assets" / "theme.css"
    css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""

    html = build_html(allocation, sms_template, css)
    out_p = Path(args.out)
    out_p.write_text(html, encoding="utf-8")

    n = len(allocation.get("assignments", []))
    print(f"✅ 已生成查询页：{out_p}（{n} 条随访任务）")
    if allocation.get("unassigned"):
        print(f"⚠️ 仍有 {len(allocation['unassigned'])} 名受试者未分配，未纳入查询页。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
