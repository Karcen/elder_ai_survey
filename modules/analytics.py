# -*- coding: utf-8 -*-
"""
analytics.py · 数据分析中心

两部分：
    Analyzer        —— 纯统计核心（无界面，可独立测试）：
                       概览指标、单题统计（人数/比例/均值/中位数/标准差）、
                       交叉分析、按日趋势。所有结果均为普通 dict，便于
                       传给大屏 / AI / 报告模块复用。
    AnalyticsCenter —— tkinter 管理界面：查看 / 筛选 / 搜索 / 删除 / 导出 /
                       查看统计 / 交叉分析。

统计完全由问卷结构驱动，不写死任何题目。
"""
from __future__ import annotations

import logging
import statistics
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional, Tuple

from modules import data_manager as dm
from modules.questionnaire_engine import Questionnaire

log = logging.getLogger("analytics")

BASE_DIR = Path(__file__).resolve().parent.parent

OPTION_TYPES = {"single", "multiple", "yesno"}
NUMERIC_TYPES = {"number", "rating"}


# ======================================================================
# 统计核心
# ======================================================================
class Analyzer:
    """问卷答卷统计分析核心。"""

    def __init__(self, questionnaire: Questionnaire,
                 data_manager: Optional[dm.DataManager] = None,
                 records: Optional[List[Dict[str, Any]]] = None) -> None:
        self.q = questionnaire
        self.data = data_manager
        self._records = records  # 允许直接注入（测试用）

    @property
    def records(self) -> List[Dict[str, Any]]:
        if self._records is not None:
            return self._records
        return self.data.load_responses() if self.data else []

    def refresh(self) -> None:
        self._records = None

    # ---------------- 概览 ----------------
    def summary(self) -> Dict[str, Any]:
        recs = self.records
        total = len(recs)
        completed = sum(1 for r in recs if r.get("completed"))
        durations = [float(r.get("duration_seconds") or 0) for r in recs if r.get("duration_seconds")]
        avg_dur = statistics.mean(durations) if durations else 0.0
        today = datetime.now().strftime("%Y-%m-%d")
        today_new = sum(1 for r in recs if str(r.get("started_at", "")).startswith(today))
        return {
            "total": total,
            "completed": completed,
            "incomplete": total - completed,
            "completion_rate": (completed / total) if total else 0.0,
            "avg_duration_seconds": round(avg_dur, 1),
            "avg_duration_text": self._fmt_duration(avg_dur),
            "today_new": today_new,
            "by_date": self.count_by_date(),
        }

    @staticmethod
    def _fmt_duration(seconds: float) -> str:
        seconds = int(seconds)
        m, s = divmod(seconds, 60)
        return f"{m}分{s}秒" if m else f"{s}秒"

    def count_by_date(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for r in self.records:
            d = str(r.get("started_at", ""))[:10]
            if d:
                out[d] = out.get(d, 0) + 1
        return dict(sorted(out.items()))

    # ---------------- 取某题的答案序列 ----------------
    def _answers_for(self, qid: str) -> List[Any]:
        out = []
        for r in self.records:
            v = r.get("answers", {}).get(qid)
            if v is None or v == "":
                continue
            out.append(v)
        return out

    # ---------------- 单题统计 ----------------
    def question_stats(self, qid: str) -> Dict[str, Any]:
        q = self.q.get(qid)
        if not q:
            return {}
        qtype = q.get("type")
        answers = self._answers_for(qid)
        base = {"id": qid, "title": q.get("title", ""), "type": qtype, "answered": len(answers)}

        if qtype in OPTION_TYPES:
            counts: Dict[str, int] = {}
            for a in answers:
                vals = a if isinstance(a, list) else (a.split("|") if isinstance(a, str) and "|" in a else [a])
                for v in vals:
                    counts[str(v)] = counts.get(str(v), 0) + 1
            denom = len(answers) or 1
            dist = []
            # 按问卷定义的选项顺序输出，未出现的也列为 0
            seen = set()
            for o in q.get("options", []):
                val = str(o.get("value"))
                c = counts.get(val, 0)
                dist.append({"value": val, "label": o.get("label", val),
                             "count": c, "ratio": c / denom})
                seen.add(val)
            for val, c in counts.items():
                if val not in seen:
                    dist.append({"value": val, "label": val, "count": c, "ratio": c / denom})
            dist.sort(key=lambda x: x["count"], reverse=True)
            base["distribution"] = dist
            top = dist[0] if dist else None
            base["top"] = top
        elif qtype in NUMERIC_TYPES:
            nums = []
            for a in answers:
                try:
                    nums.append(float(a))
                except (TypeError, ValueError):
                    pass
            base.update(self._numeric_stats(nums))
            if qtype == "rating":
                base["scale"] = q.get("scale", 5)
                base["distribution"] = self._rating_distribution(q, nums)
        elif qtype == "text":
            non_empty = [str(a).strip() for a in answers if str(a).strip()]
            base["filled"] = len(non_empty)
            base["samples"] = non_empty[:8]
        return base

    @staticmethod
    def _numeric_stats(nums: List[float]) -> Dict[str, Any]:
        if not nums:
            return {"n": 0, "mean": 0, "median": 0, "std": 0, "min": 0, "max": 0}
        return {
            "n": len(nums),
            "mean": round(statistics.mean(nums), 2),
            "median": round(statistics.median(nums), 2),
            "std": round(statistics.pstdev(nums), 2) if len(nums) > 1 else 0.0,
            "min": round(min(nums), 2),
            "max": round(max(nums), 2),
        }

    @staticmethod
    def _rating_distribution(q: Dict[str, Any], nums: List[float]) -> List[Dict[str, Any]]:
        scale = int(q.get("scale", 5))
        denom = len(nums) or 1
        dist = []
        for v in range(1, scale + 1):
            c = sum(1 for n in nums if int(round(n)) == v)
            dist.append({"value": v, "label": f"{v}分", "count": c, "ratio": c / denom})
        return dist

    def all_question_stats(self) -> List[Dict[str, Any]]:
        return [self.question_stats(q["id"]) for q in self.q.questions]

    # ---------------- 交叉分析 ----------------
    def crosstab(self, qid_row: str, qid_col: str) -> Dict[str, Any]:
        """两道题的交叉列联表（计数）。仅支持单选/是否/评分（标量答案）。"""
        qr, qc = self.q.get(qid_row), self.q.get(qid_col)
        if not qr or not qc:
            return {}
        row_opts = self._scalar_labels(qr)
        col_opts = self._scalar_labels(qc)
        row_index = {v: i for i, (v, _) in enumerate(row_opts)}
        col_index = {v: i for i, (v, _) in enumerate(col_opts)}
        matrix = [[0] * len(col_opts) for _ in row_opts]

        for r in self.records:
            a = r.get("answers", {}).get(qid_row)
            b = r.get("answers", {}).get(qid_col)
            if a is None or b is None or isinstance(a, list) or isinstance(b, list):
                continue
            ra, cb = str(a), str(b)
            if ra in row_index and cb in col_index:
                matrix[row_index[ra]][col_index[cb]] += 1

        row_totals = [sum(row) for row in matrix]
        col_totals = [sum(matrix[r][c] for r in range(len(row_opts))) for c in range(len(col_opts))]
        total = sum(row_totals)
        return {
            "row_title": qr.get("title", qid_row),
            "col_title": qc.get("title", qid_col),
            "row_labels": [lab for _, lab in row_opts],
            "col_labels": [lab for _, lab in col_opts],
            "matrix": matrix,
            "row_totals": row_totals,
            "col_totals": col_totals,
            "total": total,
        }

    @staticmethod
    def _scalar_labels(q: Dict[str, Any]) -> List[Tuple[str, str]]:
        """返回 [(value, label)]，评分题用 1..scale。"""
        if q.get("type") in OPTION_TYPES:
            return [(str(o.get("value")), o.get("label", str(o.get("value")))) for o in q.get("options", [])]
        if q.get("type") == "rating":
            return [(str(v), f"{v}分") for v in range(1, int(q.get("scale", 5)) + 1)]
        return []

    def crossable_questions(self) -> List[Dict[str, str]]:
        """可用于交叉分析的题目（单选/是否/评分）。"""
        return [{"id": q["id"], "title": q.get("title", q["id"])}
                for q in self.q.questions if q.get("type") in (OPTION_TYPES | {"rating"})]

    def suggested_crosstabs(self) -> List[Tuple[str, str]]:
        """启发式推荐若干交叉对（前若干个可交叉题两两组合）。"""
        ids = [c["id"] for c in self.crossable_questions()]
        pairs = []
        for i in range(min(3, len(ids))):
            for j in range(i + 1, min(i + 3, len(ids))):
                pairs.append((ids[i], ids[j]))
        return pairs[:5]


# ======================================================================
# 管理界面
# ======================================================================
class AnalyticsCenter:
    """数据分析中心 GUI。"""

    def __init__(self, config: Dict[str, Any], master: Optional[tk.Misc] = None,
                 base_dir: Path = BASE_DIR) -> None:
        self.config = config
        self.q = Questionnaire.load(config=config, base_dir=base_dir)
        self.data = dm.DataManager(config=config, base_dir=base_dir,
                                   question_ids=[x.get("id") for x in self.q.questions])
        self.analyzer = Analyzer(self.q, self.data)
        self.base_dir = base_dir

        if master is not None:
            self.win: tk.Misc = tk.Toplevel(master)
            self.owns_loop = False
        else:
            self.win = tk.Tk()
            self.owns_loop = True
        self.win.title("数据分析中心")
        self.win.geometry("1180x760")
        self.win.configure(bg="#f4f6fb")
        self._search_var = tk.StringVar()
        self._completed_only = tk.BooleanVar(value=False)
        self._build_ui()
        self.refresh()

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        top = tk.Frame(self.win, bg="#0d1b2a", height=64)
        top.pack(side="top", fill="x")
        tk.Label(top, text="📊 数据分析中心", font=("Microsoft YaHei", 20, "bold"),
                 bg="#0d1b2a", fg="#e0e1dd").pack(side="left", padx=20, pady=12)
        self.summary_lbl = tk.Label(top, text="", font=("Microsoft YaHei", 13),
                                    bg="#0d1b2a", fg="#9fb3d1")
        self.summary_lbl.pack(side="right", padx=20)

        # 工具条
        bar = tk.Frame(self.win, bg="#e6edfb", height=52)
        bar.pack(side="top", fill="x")
        tk.Label(bar, text="搜索：", bg="#e6edfb", font=("Microsoft YaHei", 12)).pack(side="left", padx=(14, 4))
        ent = tk.Entry(bar, textvariable=self._search_var, font=("Microsoft YaHei", 12), width=24)
        ent.pack(side="left", pady=10)
        ent.bind("<Return>", lambda e: self.refresh())
        tk.Checkbutton(bar, text="只看已完成", variable=self._completed_only, bg="#e6edfb",
                       font=("Microsoft YaHei", 12), command=self.refresh).pack(side="left", padx=10)

        def tb(txt, cmd, color="#2563eb"):
            return tk.Button(bar, text=txt, command=cmd, font=("Microsoft YaHei", 12, "bold"),
                             bg=color, fg="white", relief="flat", padx=12, pady=5, cursor="hand2")

        tb("🔄 刷新", self.refresh, "#475569").pack(side="left", padx=6)
        tb("📈 单题统计", self.show_stats).pack(side="left", padx=4)
        tb("🔀 交叉分析", self.show_crosstab).pack(side="left", padx=4)
        tb("📤 导出Excel", self.export_excel, "#0ea5a4").pack(side="left", padx=4)
        tb("🗑 删除选中", self.delete_selected, "#e11d48").pack(side="left", padx=4)

        # 数据表
        wrap = tk.Frame(self.win, bg="#f4f6fb")
        wrap.pack(side="top", fill="both", expand=True, padx=12, pady=10)
        cols = ("response_id", "started_at", "duration", "completed", "preview")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="extended")
        for c, txt, w in [("response_id", "编号", 170), ("started_at", "开始时间", 160),
                          ("duration", "用时", 80), ("completed", "完成", 60), ("preview", "答案预览", 560)]:
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor="w")
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._show_detail)

    # ---------------- 数据 ----------------
    def _filtered_records(self) -> List[Dict[str, Any]]:
        self.analyzer.refresh()
        recs = self.analyzer.records
        kw = self._search_var.get().strip()
        if self._completed_only.get():
            recs = [r for r in recs if r.get("completed")]
        if kw:
            def hit(r):
                blob = r.get("response_id", "") + " " + " ".join(
                    self.q.answer_display(qid, v) for qid, v in r.get("answers", {}).items())
                return kw.lower() in blob.lower()
            recs = [r for r in recs if hit(r)]
        return recs

    def refresh(self) -> None:
        for i in self.tree.get_children():
            self.tree.delete(i)
        recs = self._filtered_records()
        for r in recs:
            preview = "  ".join(
                f"{qid}:{self.q.answer_display(qid, v)}"
                for qid, v in list(r.get("answers", {}).items())[:4])
            self.tree.insert("", "end", iid=r["response_id"], values=(
                r["response_id"], r.get("started_at", ""),
                Analyzer._fmt_duration(float(r.get("duration_seconds") or 0)),
                "✓" if r.get("completed") else "—", preview))
        s = self.analyzer.summary()
        self.summary_lbl.configure(
            text=f"共 {s['total']} 份 · 完成率 {s['completion_rate']*100:.1f}% · "
                 f"平均 {s['avg_duration_text']} · 今日 +{s['today_new']}")

    def _show_detail(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        rec = next((r for r in self.analyzer.records if r["response_id"] == sel[0]), None)
        if not rec:
            return
        win = tk.Toplevel(self.win)
        win.title("答卷详情 · " + rec["response_id"])
        win.geometry("640x720")
        txt = tk.Text(win, font=("Microsoft YaHei", 12), wrap="word", padx=14, pady=14)
        txt.pack(fill="both", expand=True)
        txt.insert("end", f"编号：{rec['response_id']}\n开始：{rec.get('started_at')}\n"
                          f"用时：{Analyzer._fmt_duration(float(rec.get('duration_seconds') or 0))}\n"
                          f"完成：{'是' if rec.get('completed') else '否'}\n" + "—" * 30 + "\n\n")
        for q in self.q.questions:
            qid = q["id"]
            if qid in rec.get("answers", {}):
                txt.insert("end", f"{qid}. {q.get('title','')}\n   ▸ {self.q.answer_display(qid, rec['answers'][qid])}\n\n")
        txt.configure(state="disabled")

    def delete_selected(self) -> None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择要删除的答卷。")
            return
        if not messagebox.askyesno("确认删除", f"确定删除选中的 {len(sel)} 份答卷吗？此操作不可恢复。"):
            return
        for rid in sel:
            self.data.delete_response(rid)
        self.refresh()
        messagebox.showinfo("完成", f"已删除 {len(sel)} 份答卷。")

    # ---------------- 统计弹窗 ----------------
    def show_stats(self) -> None:
        win = tk.Toplevel(self.win)
        win.title("单题统计")
        win.geometry("820x760")
        win.configure(bg="#ffffff")
        canvas = tk.Canvas(win, bg="#ffffff", highlightthickness=0)
        sb = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        frame = tk.Frame(canvas, bg="#ffffff")
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        for st in self.analyzer.all_question_stats():
            self._render_stat_block(frame, st)

    def _render_stat_block(self, parent, st: Dict[str, Any]) -> None:
        tk.Label(parent, text=f"{st['id']}. {st['title']}", font=("Microsoft YaHei", 14, "bold"),
                 bg="#ffffff", fg="#1b263b", wraplength=760, justify="left", anchor="w").pack(fill="x", padx=16, pady=(16, 4))
        info = tk.Frame(parent, bg="#ffffff")
        info.pack(fill="x", padx=24)
        if "distribution" in st:
            maxc = max((d["count"] for d in st["distribution"]), default=1) or 1
            for d in st["distribution"]:
                row = tk.Frame(info, bg="#ffffff")
                row.pack(fill="x", pady=2)
                tk.Label(row, text=d["label"], width=16, anchor="w", bg="#ffffff",
                         font=("Microsoft YaHei", 11)).pack(side="left")
                bar = tk.Canvas(row, height=18, width=360, bg="#eef2ff", highlightthickness=0)
                bar.pack(side="left", padx=6)
                bar.create_rectangle(0, 0, int(360 * d["count"] / maxc), 18, fill="#2563eb", width=0)
                tk.Label(row, text=f"{d['count']} ({d['ratio']*100:.0f}%)", bg="#ffffff",
                         font=("Microsoft YaHei", 11)).pack(side="left", padx=6)
        if st.get("type") in NUMERIC_TYPES and st.get("n"):
            tk.Label(info, text=f"样本 {st['n']} · 均值 {st['mean']} · 中位数 {st['median']} · "
                                f"标准差 {st['std']} · 范围 {st['min']}~{st['max']}",
                     bg="#ffffff", fg="#475569", font=("Microsoft YaHei", 11)).pack(anchor="w", pady=4)
        if st.get("type") == "text":
            tk.Label(info, text=f"填写 {st.get('filled',0)} 条。示例：" + "；".join(st.get("samples", [])[:3]),
                     bg="#ffffff", fg="#475569", font=("Microsoft YaHei", 11), wraplength=740,
                     justify="left", anchor="w").pack(anchor="w", pady=4)
        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=16, pady=8)

    # ---------------- 交叉分析弹窗 ----------------
    def show_crosstab(self) -> None:
        win = tk.Toplevel(self.win)
        win.title("交叉分析")
        win.geometry("820x620")
        win.configure(bg="#ffffff")
        opts = self.analyzer.crossable_questions()
        if len(opts) < 2:
            tk.Label(win, text="可交叉分析的题目不足（需至少两道单选/是否/评分题）。",
                     bg="#ffffff", font=("Microsoft YaHei", 13)).pack(pady=40)
            return
        labels = [f"{o['id']} · {o['title'][:14]}" for o in opts]
        ids = [o["id"] for o in opts]

        ctrl = tk.Frame(win, bg="#ffffff")
        ctrl.pack(fill="x", pady=10, padx=10)
        tk.Label(ctrl, text="行：", bg="#ffffff", font=("Microsoft YaHei", 12)).pack(side="left")
        row_cb = ttk.Combobox(ctrl, values=labels, state="readonly", width=24)
        row_cb.current(0); row_cb.pack(side="left", padx=4)
        tk.Label(ctrl, text="列：", bg="#ffffff", font=("Microsoft YaHei", 12)).pack(side="left", padx=(12, 0))
        col_cb = ttk.Combobox(ctrl, values=labels, state="readonly", width=24)
        col_cb.current(min(1, len(labels) - 1)); col_cb.pack(side="left", padx=4)

        holder = tk.Frame(win, bg="#ffffff")
        holder.pack(fill="both", expand=True, padx=12, pady=8)

        def render():
            for w in holder.winfo_children():
                w.destroy()
            ct = self.analyzer.crosstab(ids[row_cb.current()], ids[col_cb.current()])
            if not ct or ct["total"] == 0:
                tk.Label(holder, text="暂无足够数据。", bg="#ffffff", font=("Microsoft YaHei", 12)).pack(pady=20)
                return
            tk.Label(holder, text=f"{ct['row_title']}  ×  {ct['col_title']}（n={ct['total']}）",
                     bg="#ffffff", font=("Microsoft YaHei", 13, "bold")).pack(anchor="w", pady=6)
            grid = tk.Frame(holder, bg="#ffffff")
            grid.pack(fill="both", expand=True)
            # 表头
            tk.Label(grid, text="", bg="#dbe4f5", width=14, relief="solid", bd=1).grid(row=0, column=0, sticky="nsew")
            for j, cl in enumerate(ct["col_labels"]):
                tk.Label(grid, text=cl, bg="#dbe4f5", width=10, relief="solid", bd=1,
                         font=("Microsoft YaHei", 10, "bold")).grid(row=0, column=j + 1, sticky="nsew")
            tk.Label(grid, text="合计", bg="#c7d2fe", width=8, relief="solid", bd=1,
                     font=("Microsoft YaHei", 10, "bold")).grid(row=0, column=len(ct["col_labels"]) + 1, sticky="nsew")
            for i, rl in enumerate(ct["row_labels"]):
                tk.Label(grid, text=rl, bg="#dbe4f5", width=14, relief="solid", bd=1,
                         font=("Microsoft YaHei", 10, "bold")).grid(row=i + 1, column=0, sticky="nsew")
                for j, _ in enumerate(ct["col_labels"]):
                    c = ct["matrix"][i][j]
                    rt = ct["row_totals"][i] or 1
                    tk.Label(grid, text=f"{c}\n{c/rt*100:.0f}%", bg="#ffffff", relief="solid", bd=1,
                             font=("Microsoft YaHei", 10)).grid(row=i + 1, column=j + 1, sticky="nsew")
                tk.Label(grid, text=str(ct["row_totals"][i]), bg="#eef2ff", relief="solid", bd=1,
                         font=("Microsoft YaHei", 10, "bold")).grid(row=i + 1, column=len(ct["col_labels"]) + 1, sticky="nsew")

        row_cb.bind("<<ComboboxSelected>>", lambda e: render())
        col_cb.bind("<<ComboboxSelected>>", lambda e: render())
        render()

    # ---------------- 导出 ----------------
    def export_excel(self) -> None:
        try:
            from modules import report_generator
            path = report_generator.export_excel(self.config, self.q, self.analyzer, base_dir=self.base_dir)
            messagebox.showinfo("导出成功", f"已导出到：\n{path}")
        except ImportError:
            messagebox.showwarning("提示", "导出模块尚未就绪（第八阶段提供）。")
        except Exception as exc:  # noqa: BLE001
            log.exception("导出失败")
            messagebox.showerror("导出失败", str(exc))

    def run(self) -> None:
        if self.owns_loop:
            self.win.mainloop()


# ======================================================================
# 入口
# ======================================================================
def launch(config: Dict[str, Any], master: Optional[tk.Misc] = None) -> Optional[AnalyticsCenter]:
    app = AnalyticsCenter(config, master=master)
    app.run()
    return app
