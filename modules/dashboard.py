# -*- coding: utf-8 -*-
"""
dashboard.py · 科交会展示大屏

特性：
    - 全屏、科技蓝主题；
    - 数据驾驶舱：累计问卷 / 今日新增 / 完成率 / 平均时长 / 年龄结构 / 性别结构；
    - 多种图表：饼图 / 柱状图 / 折线图 / 雷达图 / 排行图（matplotlib 嵌入）；
    - 展厅模式：总览→统计图→趋势图→AI分析→报告页，每 10 秒自动轮播；
    - 实时刷新：每 5 秒重新读取数据。

数据统一来自 analytics.Analyzer，图表由问卷结构驱动，不写死题目。
快捷键：Esc 退出，空格 暂停/继续轮播，← → 手动翻页。
"""
from __future__ import annotations

import logging
import tkinter as tk
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules import data_manager as dm
from modules.analytics import Analyzer
from modules.questionnaire_engine import Questionnaire

log = logging.getLogger("dashboard")

BASE_DIR = Path(__file__).resolve().parent.parent

# 科技蓝配色
C = {
    "bg": "#0a1628", "panel": "#0f2038", "card": "#13294b",
    "fg": "#e6f0ff", "sub": "#7fa0c8", "accent": "#22d3ee",
    "accent2": "#3b82f6", "good": "#34d399", "warn": "#fbbf24", "line": "#1e3a5f",
}
# 图表配色循环
PALETTE = ["#22d3ee", "#3b82f6", "#34d399", "#fbbf24", "#f472b6", "#a78bfa", "#fb7185", "#60a5fa"]


# ---------------------------------------------------------------------------
# matplotlib 初始化（含中文字体），失败则标记不可用
# ---------------------------------------------------------------------------
def _init_matplotlib():
    try:
        import matplotlib
        matplotlib.use("TkAgg")
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: F401
        # 中文字体候选（macOS / Windows / Linux 常见）
        plt.rcParams["font.sans-serif"] = [
            "Arial Unicode MS", "PingFang SC", "Heiti TC", "STHeiti",
            "Microsoft YaHei", "SimHei", "WenQuanYi Zen Hei", "Noto Sans CJK SC",
        ]
        plt.rcParams["axes.unicode_minus"] = False
        return plt, FigureCanvasTkAgg
    except Exception as exc:  # noqa: BLE001
        log.warning("matplotlib 不可用，大屏图表降级为文字：%s", exc)
        return None, None


# ======================================================================
# 大屏
# ======================================================================
class ScienceDashboard:
    """科交会数据驾驶舱大屏。"""

    def __init__(self, config: Dict[str, Any], master: Optional[tk.Misc] = None,
                 base_dir: Path = BASE_DIR) -> None:
        self.config = config
        self.base_dir = base_dir
        dconf = config.get("dashboard", {})
        self.refresh_interval = int(dconf.get("refresh_interval_seconds", 5)) * 1000
        self.carousel_interval = int(dconf.get("carousel_interval_seconds", 10)) * 1000
        self.pages: List[str] = dconf.get(
            "carousel_pages", ["overview", "charts", "trends", "ai", "report"])

        self.q = Questionnaire.load(config=config, base_dir=base_dir)
        self.data = dm.DataManager(config=config, base_dir=base_dir,
                                   question_ids=[x.get("id") for x in self.q.questions])
        self.analyzer = Analyzer(self.q, self.data)

        self.plt, self.FigureCanvas = _init_matplotlib()
        self._canvases: List[Any] = []  # 当前页的 matplotlib canvas（便于清理）
        self._figs: List[Any] = []

        self.page_index = 0
        self.paused = False
        self._carousel_job: Optional[str] = None
        self._refresh_job: Optional[str] = None

        if master is not None:
            self.win: tk.Misc = tk.Toplevel(master)
            self.owns_loop = False
        else:
            self.win = tk.Tk()
            self.owns_loop = True
        self.win.title("科交会展示大屏")
        self.win.configure(bg=C["bg"])
        try:
            self.win.attributes("-fullscreen", True)
        except tk.TclError:
            self.win.geometry("1280x800")

        self._build_chrome()
        self._bind_keys()
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- 框架 ----------------
    def _build_chrome(self) -> None:
        self.header = tk.Frame(self.win, bg=C["panel"], height=84)
        self.header.pack(side="top", fill="x")
        tk.Label(self.header, text="适老化智能问卷 · 数据驾驶舱",
                 font=("Microsoft YaHei", 26, "bold"), bg=C["panel"], fg=C["fg"]).pack(side="left", padx=30, pady=16)
        self.clock = tk.Label(self.header, text="", font=("Microsoft YaHei", 16),
                              bg=C["panel"], fg=C["accent"])
        self.clock.pack(side="right", padx=30)
        self.page_tag = tk.Label(self.header, text="", font=("Microsoft YaHei", 16, "bold"),
                                 bg=C["panel"], fg=C["sub"])
        self.page_tag.pack(side="right", padx=10)

        self.body = tk.Frame(self.win, bg=C["bg"])
        self.body.pack(side="top", fill="both", expand=True, padx=22, pady=14)

        # 底部页码指示 + 署名
        self.footer = tk.Frame(self.win, bg=C["panel"], height=40)
        self.footer.pack(side="bottom", fill="x")
        self._build_credit()  # 先占右侧
        self.dots = tk.Label(self.footer, text="", font=("Microsoft YaHei", 14),
                             bg=C["panel"], fg=C["sub"])
        self.dots.pack(side="left", expand=True, pady=8)

    def _build_credit(self) -> None:
        """大屏页脚署名 + 可点击联系链接。"""
        about = self.config.get("about", {})
        author = about.get("author", "Jiacheng Zheng")
        credit = about.get("credit", "使用 Claude Code 辅助开发")
        label = about.get("contact_label", "联系我")
        url = about.get("contact_url", "")
        box = tk.Frame(self.footer, bg=C["panel"])
        box.pack(side="right", padx=20)
        tk.Label(box, text=f"{author} · {credit} · ", font=("Microsoft YaHei", 11),
                 bg=C["panel"], fg=C["sub"]).pack(side="left")
        link = tk.Label(box, text=label, font=("Microsoft YaHei", 11, "underline"),
                        bg=C["panel"], fg=C["accent"], cursor="hand2")
        link.pack(side="left")
        if url:
            link.bind("<Button-1>", lambda e: webbrowser.open(url))
            link.bind("<Enter>", lambda e: link.configure(fg="#67e8f9"))
            link.bind("<Leave>", lambda e: link.configure(fg=C["accent"]))

    # ---------------- 数据/页面刷新 ----------------
    def _clear_body(self) -> None:
        for cv in self._canvases:
            try:
                cv.get_tk_widget().destroy()
            except Exception:  # noqa: BLE001
                pass
        if self.plt:
            for fig in self._figs:
                try:
                    self.plt.close(fig)
                except Exception:  # noqa: BLE001
                    pass
        self._canvases.clear()
        self._figs.clear()
        for w in self.body.winfo_children():
            w.destroy()

    def render_page(self, name: str) -> None:
        self.analyzer.refresh()
        self._clear_body()
        self.page_tag.configure(text="◉ " + PAGE_TITLES.get(name, name))
        self._update_dots()
        try:
            getattr(self, f"_page_{name}", self._page_overview)()
        except Exception:  # noqa: BLE001
            log.exception("渲染页面 %s 失败", name)
            tk.Label(self.body, text="（本页渲染异常，请查看日志）",
                     font=("Microsoft YaHei", 16), bg=C["bg"], fg=C["warn"]).pack(pady=40)

    def _update_dots(self) -> None:
        dots = "   ".join(("●" if i == self.page_index else "○") for i in range(len(self.pages)))
        self.dots.configure(text=dots + "      （空格暂停 / ← → 翻页 / Esc 退出）")

    # ---------------- KPI 卡片 ----------------
    def _kpi_card(self, parent, title: str, value: str, sub: str = "", color: str = None) -> None:
        color = color or C["accent"]
        card = tk.Frame(parent, bg=C["card"], highlightbackground=C["line"], highlightthickness=1)
        card.pack(side="left", expand=True, fill="both", padx=10, pady=6)
        tk.Label(card, text=title, font=("Microsoft YaHei", 15), bg=C["card"], fg=C["sub"]).pack(pady=(18, 2))
        tk.Label(card, text=value, font=("Microsoft YaHei", 40, "bold"), bg=C["card"], fg=color).pack()
        tk.Label(card, text=sub, font=("Microsoft YaHei", 12), bg=C["card"], fg=C["sub"]).pack(pady=(2, 16))

    # ---------------- 图表助手 ----------------
    def _embed(self, fig, parent) -> None:
        if not self.FigureCanvas:
            return
        canvas = self.FigureCanvas(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(side="left", fill="both", expand=True, padx=8, pady=6)
        self._canvases.append(canvas)
        self._figs.append(fig)

    def _new_fig(self, w=5.0, h=3.6):
        fig = self.plt.figure(figsize=(w, h), dpi=100, facecolor=C["panel"])
        return fig

    def _style_ax(self, ax, title=""):
        ax.set_facecolor(C["panel"])
        ax.set_title(title, color=C["fg"], fontsize=14, pad=10)
        ax.tick_params(colors=C["sub"], labelsize=10)
        for spine in ax.spines.values():
            spine.set_color(C["line"])

    def _first_by_types(self, types, n=1):
        out = [q for q in self.q.questions if q.get("type") in types]
        return out[:n]

    # ---------------- 页：总览 ----------------
    def _page_overview(self) -> None:
        s = self.analyzer.summary()
        kpis = tk.Frame(self.body, bg=C["bg"])
        kpis.pack(fill="x")
        self._kpi_card(kpis, "累计问卷", str(s["total"]), "份", C["accent"])
        self._kpi_card(kpis, "今日新增", f"+{s['today_new']}", "份", C["good"])
        self._kpi_card(kpis, "完成率", f"{s['completion_rate']*100:.1f}%", f"{s['completed']}/{s['total']}", C["accent2"])
        self._kpi_card(kpis, "平均时长", s["avg_duration_text"], "每份", C["warn"])

        if not self.plt:
            self._text_overview(s)
            return
        charts = tk.Frame(self.body, bg=C["bg"])
        charts.pack(fill="both", expand=True, pady=8)
        # 前两个选项题作为「年龄结构 / 性别结构」饼图
        for qd in self._first_by_types({"single", "yesno"}, n=2):
            st = self.analyzer.question_stats(qd["id"])
            fig = self._new_fig()
            ax = fig.add_subplot(111)
            self._style_ax(ax, qd.get("title", "")[:16])
            dist = [d for d in st.get("distribution", []) if d["count"] > 0]
            if dist:
                ax.pie([d["count"] for d in dist], labels=[d["label"] for d in dist],
                       autopct="%1.0f%%", colors=PALETTE, textprops={"color": C["fg"], "fontsize": 10},
                       wedgeprops={"edgecolor": C["panel"]})
            else:
                ax.text(0.5, 0.5, "暂无数据", ha="center", color=C["sub"])
            fig.tight_layout()
            self._embed(fig, charts)

    def _text_overview(self, s) -> None:
        tk.Label(self.body, text=f"累计 {s['total']} 份 · 完成率 {s['completion_rate']*100:.1f}%",
                 font=("Microsoft YaHei", 22), bg=C["bg"], fg=C["fg"]).pack(pady=40)

    # ---------------- 页：统计图 ----------------
    def _page_charts(self) -> None:
        if not self.plt:
            tk.Label(self.body, text="（未安装 matplotlib，无法显示图表）",
                     font=("Microsoft YaHei", 20), bg=C["bg"], fg=C["warn"]).pack(pady=60)
            return
        grid = tk.Frame(self.body, bg=C["bg"])
        grid.pack(fill="both", expand=True)

        # 柱状图：第一个单选题分布
        singles = self._first_by_types({"single"}, n=1)
        if singles:
            st = self.analyzer.question_stats(singles[0]["id"])
            fig = self._new_fig(6, 3.8)
            ax = fig.add_subplot(111)
            self._style_ax(ax, st["title"][:18])
            dist = st.get("distribution", [])
            ax.bar([d["label"] for d in dist], [d["count"] for d in dist], color=PALETTE)
            ax.tick_params(axis="x", rotation=20)
            fig.tight_layout()
            self._embed(fig, grid)

        # 评分题分布柱状
        ratings = self._first_by_types({"rating"}, n=1)
        if ratings:
            st = self.analyzer.question_stats(ratings[0]["id"])
            fig = self._new_fig(6, 3.8)
            ax = fig.add_subplot(111)
            self._style_ax(ax, st["title"][:18] + f"（均值{st.get('mean','-')}）")
            dist = st.get("distribution", [])
            ax.bar([d["label"] for d in dist], [d["count"] for d in dist], color=C["accent"])
            fig.tight_layout()
            self._embed(fig, grid)

        # 多选题排行（横向条）
        multis = self._first_by_types({"multiple"}, n=1)
        if multis:
            st = self.analyzer.question_stats(multis[0]["id"])
            fig = self._new_fig(6, 3.8)
            ax = fig.add_subplot(111)
            self._style_ax(ax, st["title"][:18] + "（排行）")
            dist = sorted(st.get("distribution", []), key=lambda x: x["count"])
            ax.barh([d["label"] for d in dist], [d["count"] for d in dist], color=C["accent2"])
            fig.tight_layout()
            self._embed(fig, grid)

    # ---------------- 页：趋势 ----------------
    def _page_trends(self) -> None:
        by_date = self.analyzer.count_by_date()
        if not self.plt:
            tk.Label(self.body, text="按日趋势：" + "  ".join(f"{d}:{c}" for d, c in by_date.items()),
                     font=("Microsoft YaHei", 16), bg=C["bg"], fg=C["fg"], wraplength=1100).pack(pady=40)
            return
        fig = self._new_fig(11, 5)
        ax = fig.add_subplot(111)
        self._style_ax(ax, "每日答卷数量趋势")
        if by_date:
            dates = list(by_date.keys())
            counts = list(by_date.values())
            ax.plot(dates, counts, marker="o", color=C["accent"], linewidth=2.5, markersize=8)
            ax.fill_between(range(len(dates)), counts, color=C["accent"], alpha=0.15)
            ax.tick_params(axis="x", rotation=30)
            ax.grid(True, color=C["line"], alpha=0.4)
        else:
            ax.text(0.5, 0.5, "暂无数据", ha="center", color=C["sub"])
        fig.tight_layout()
        self._embed(fig, self.body)

    # ---------------- 页：AI 分析 ----------------
    def _page_ai(self) -> None:
        insights = self._get_insights()
        wrap = tk.Frame(self.body, bg=C["bg"])
        wrap.pack(fill="both", expand=True)
        tk.Label(wrap, text="🤖 AI 智能洞察", font=("Microsoft YaHei", 24, "bold"),
                 bg=C["bg"], fg=C["accent"]).pack(anchor="w", pady=(6, 14))
        for i, ins in enumerate(insights[:10], 1):
            row = tk.Frame(wrap, bg=C["card"], highlightbackground=C["line"], highlightthickness=1)
            row.pack(fill="x", pady=5)
            tk.Label(row, text=str(i), font=("Microsoft YaHei", 16, "bold"), bg=C["accent2"],
                     fg="white", width=3).pack(side="left", fill="y")
            tk.Label(row, text=ins, font=("Microsoft YaHei", 15), bg=C["card"], fg=C["fg"],
                     wraplength=1100, justify="left", anchor="w").pack(side="left", padx=14, pady=10)

    def _get_insights(self) -> List[str]:
        # 优先调用 AI 引擎；不可用则回退到分析器派生要点
        try:
            from modules import ai_engine
            engine = ai_engine.AIEngine(self.config, self.q, self.analyzer)
            return engine.generate_insights()
        except Exception as exc:  # noqa: BLE001
            log.info("AI 引擎暂不可用，使用基础洞察：%s", exc)
            return self._basic_insights()

    def _basic_insights(self) -> List[str]:
        out = []
        s = self.analyzer.summary()
        out.append(f"累计回收问卷 {s['total']} 份，完成率 {s['completion_rate']*100:.1f}%，平均用时 {s['avg_duration_text']}。")
        for st in self.analyzer.all_question_stats():
            if st.get("type") in ("single", "yesno") and st.get("top"):
                out.append(f"「{st['title'][:20]}」中，选择最多的是「{st['top']['label']}」，占 {st['top']['ratio']*100:.0f}%。")
            elif st.get("type") == "rating" and st.get("n"):
                out.append(f"「{st['title'][:20]}」平均评分 {st['mean']} 分（满分 {st.get('scale',5)}）。")
            if len(out) >= 10:
                break
        return out

    # ---------------- 页：报告页 ----------------
    def _page_report(self) -> None:
        left = tk.Frame(self.body, bg=C["bg"])
        left.pack(side="left", fill="both", expand=True)
        s = self.analyzer.summary()
        tk.Label(left, text="📋 调查总览报告", font=("Microsoft YaHei", 24, "bold"),
                 bg=C["bg"], fg=C["fg"]).pack(anchor="w", pady=(6, 14))
        lines = [
            f"问卷主题：{self.q.title()}",
            f"样本规模：{s['total']} 份（已完成 {s['completed']} 份）",
            f"完成率：{s['completion_rate']*100:.1f}%",
            f"平均填写时长：{s['avg_duration_text']}",
            f"今日新增：{s['today_new']} 份",
            "数据来源：现场答题端 · CSV/SQLite 双重存储",
        ]
        for ln in lines:
            tk.Label(left, text="•  " + ln, font=("Microsoft YaHei", 16), bg=C["bg"], fg=C["sub"],
                     anchor="w", justify="left", wraplength=600).pack(anchor="w", pady=4)

        # 右侧：评分题雷达图
        ratings = self._first_by_types({"rating"}, n=6)
        if self.plt and len(ratings) >= 3:
            stats = [self.analyzer.question_stats(r["id"]) for r in ratings]
            stats = [st for st in stats if st.get("n")]
            if len(stats) >= 3:
                import numpy as np
                labels = [st["title"][:8] for st in stats]
                values = [st["mean"] for st in stats]
                scale = stats[0].get("scale", 5)
                angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
                values_c = values + values[:1]
                angles_c = angles + angles[:1]
                fig = self._new_fig(5.4, 5.4)
                ax = fig.add_subplot(111, polar=True)
                ax.set_facecolor(C["panel"])
                ax.plot(angles_c, values_c, color=C["accent"], linewidth=2)
                ax.fill(angles_c, values_c, color=C["accent"], alpha=0.25)
                ax.set_xticks(angles)
                ax.set_xticklabels(labels, color=C["fg"], fontsize=10)
                ax.set_ylim(0, scale)
                ax.set_title("各项评分雷达图", color=C["fg"], fontsize=14, pad=18)
                ax.tick_params(colors=C["sub"])
                fig.tight_layout()
                self._embed(fig, self.body)

    # ---------------- 轮播 / 刷新 ----------------
    def _tick_clock(self) -> None:
        from datetime import datetime
        self.clock.configure(text=datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.win.after(1000, self._tick_clock)

    def _schedule_carousel(self) -> None:
        if self._carousel_job:
            self.win.after_cancel(self._carousel_job)
        self._carousel_job = self.win.after(self.carousel_interval, self._auto_advance)

    def _auto_advance(self) -> None:
        if not self.paused:
            self.next_page()
        self._schedule_carousel()

    def _schedule_refresh(self) -> None:
        if self._refresh_job:
            self.win.after_cancel(self._refresh_job)
        self._refresh_job = self.win.after(self.refresh_interval, self._auto_refresh)

    def _auto_refresh(self) -> None:
        self.render_page(self.pages[self.page_index])
        self._schedule_refresh()

    def next_page(self) -> None:
        self.page_index = (self.page_index + 1) % len(self.pages)
        self.render_page(self.pages[self.page_index])

    def prev_page(self) -> None:
        self.page_index = (self.page_index - 1) % len(self.pages)
        self.render_page(self.pages[self.page_index])

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.page_tag.configure(fg=C["warn"] if self.paused else C["sub"])

    # ---------------- 按键 / 关闭 ----------------
    def _bind_keys(self) -> None:
        self.win.bind("<Escape>", lambda e: self._on_close())
        self.win.bind("<space>", lambda e: self.toggle_pause())
        self.win.bind("<Right>", lambda e: self.next_page())
        self.win.bind("<Left>", lambda e: self.prev_page())

    def _on_close(self) -> None:
        for job in (self._carousel_job, self._refresh_job):
            if job:
                try:
                    self.win.after_cancel(job)
                except Exception:  # noqa: BLE001
                    pass
        try:
            self.win.destroy()
        except Exception:  # noqa: BLE001
            pass

    def run(self) -> None:
        self.render_page(self.pages[self.page_index])
        self._tick_clock()
        self._schedule_carousel()
        self._schedule_refresh()
        if self.owns_loop:
            self.win.mainloop()


PAGE_TITLES = {
    "overview": "数据总览", "charts": "统计图表", "trends": "趋势分析",
    "ai": "AI 洞察", "report": "调查报告",
}


# ======================================================================
# 入口
# ======================================================================
def launch(config: Dict[str, Any], master: Optional[tk.Misc] = None) -> Optional[ScienceDashboard]:
    app = ScienceDashboard(config, master=master)
    app.run()
    return app
