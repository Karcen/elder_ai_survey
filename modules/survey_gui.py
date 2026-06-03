# -*- coding: utf-8 -*-
"""
survey_gui.py · 适老化老人答题端

特性：
    - 全屏、超大字体（默认 48 号粗体，可在 24/36/48/60/72 间切换）
    - 三套高对比主题（白底黑字 / 黑底白字 / 蓝底黄字）一键切换
    - 超大按钮（高 ≥80px、宽 ≥300px、间距 ≥20px）
    - 两种答题模式：标准逐题模式 + 对话访谈模式（像有人提问一样）
    - 键盘操作（数字键选项、← 上一题、→/回车 下一题）
    - 语音播报与自动重读、超时提醒、防误触
    - 逐题自动保存 autosave.json，异常退出后自动恢复
    - 提交后 CSV + SQLite 双重存储

实现要点：彩色按钮统一用 tk.Label 实现（macOS 上 tk.Button 会忽略 bg 颜色，
导致高对比主题与白字按钮失效），从而保证三套主题、文字颜色都正确显示。

数据流：统一通过 questionnaire_engine 读取问卷、做逻辑跳转与答案校验。
"""
from __future__ import annotations

import json
import logging
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import messagebox
from datetime import datetime
from typing import Any, Dict, List, Optional

from modules import data_manager as dm
from modules.questionnaire_engine import Questionnaire
from modules.speech_engine import SpeechEngine

log = logging.getLogger("survey_gui")

BASE_DIR = Path(__file__).resolve().parent.parent

# 三套高对比主题
THEMES: Dict[str, Dict[str, str]] = {
    "white_black": {"name": "白底黑字", "bg": "#ffffff", "fg": "#111111", "sub": "#444444",
                    "btn": "#eef3ff", "btn_fg": "#111111", "sel": "#1d4ed8", "sel_fg": "#ffffff",
                    "bar": "#e6edfb", "accent": "#1d4ed8", "line": "#9db4e3"},
    "black_white": {"name": "黑底白字", "bg": "#000000", "fg": "#ffffff", "sub": "#cccccc",
                    "btn": "#222222", "btn_fg": "#ffffff", "sel": "#ffd400", "sel_fg": "#000000",
                    "bar": "#111111", "accent": "#ffd400", "line": "#666666"},
    "blue_yellow": {"name": "蓝底黄字", "bg": "#03204d", "fg": "#ffe600", "sub": "#ffe600",
                    "btn": "#0b3a7a", "btn_fg": "#ffe600", "sel": "#ffe600", "sel_fg": "#03204d",
                    "bar": "#06285c", "accent": "#ffe600", "line": "#2a559f"},
}


# ======================================================================
# 自动保存（独立可测）
# ======================================================================
class AutoSaveStore:
    """把答题进度写入 autosave.json，支持异常退出后恢复。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, state: Dict[str, Any]) -> None:
        """原子写入，避免写一半损坏。"""
        try:
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            tmp.replace(self.path)
        except OSError as exc:
            log.error("自动保存失败：%s", exc)

    def load(self) -> Optional[Dict[str, Any]]:
        if not self.path.exists():
            return None
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            log.error("读取自动保存失败：%s", exc)
            return None

    def clear(self) -> None:
        try:
            if self.path.exists():
                self.path.unlink()
        except OSError as exc:
            log.error("清除自动保存失败：%s", exc)

    def exists(self) -> bool:
        return self.path.exists()


# ======================================================================
# 答题端主界面
# ======================================================================
class SurveyClient:
    """适老化答题端主窗口。"""

    def __init__(self, config: Dict[str, Any], master: Optional[tk.Misc] = None,
                 base_dir: Path = BASE_DIR) -> None:
        self.config = config
        self.base_dir = base_dir
        acc = config.get("accessibility", {})

        # 引擎与数据
        self.q = Questionnaire.load(config=config, base_dir=base_dir)
        self.data = dm.DataManager(config=config, base_dir=base_dir,
                                   question_ids=[x.get("id") for x in self.q.questions])
        self.speech = SpeechEngine(config)
        autosave_path = base_dir / config.get("paths", {}).get("autosave", "survey/autosave.json")
        self.autosave = AutoSaveStore(autosave_path)

        # 无障碍参数
        self.font_sizes: List[int] = acc.get("font_sizes", [24, 36, 48, 60, 72])
        default_size = acc.get("default_font_size", 48)
        self.size_idx = self.font_sizes.index(default_size) if default_size in self.font_sizes else 2
        self.theme_key = acc.get("default_theme", "white_black")
        self.timeout_seconds = int(acc.get("timeout_seconds", 60))
        self.anti_ms = int(acc.get("anti_misclick_ms", 400))
        self.auto_reread = acc.get("auto_reread", True)
        self.voice_on = self.speech.tts_available
        self.mode = acc.get("answer_mode", "standard")  # standard | conversation
        self.interviewer_name = acc.get("interviewer_name", "小助手")

        # 运行状态
        self.answers: Dict[str, Any] = {}
        self.history: List[str] = []
        self.current_qid: Optional[str] = None
        self.response_id: str = dm.DataManager.new_response_id()
        self.started_at: Optional[str] = None
        self._last_click = 0.0
        self._timeout_job: Optional[str] = None
        self._screen = "welcome"
        self._input_vars: Dict[str, Any] = {}
        self._title_label: Optional[tk.Label] = None

        # 窗口
        if master is not None:
            self.win: tk.Misc = tk.Toplevel(master)
            self.owns_loop = False
        else:
            self.win = tk.Tk()
            self.owns_loop = True
        self.win.title("适老化问卷 · 答题端")
        try:
            self.win.attributes("-fullscreen", True)
        except tk.TclError:
            self.win.geometry("1100x800")

        # 字体对象（改变字号时重配）
        self.f_title = tkfont.Font(family="Microsoft YaHei", weight="bold")
        self.f_body = tkfont.Font(family="Microsoft YaHei")
        self.f_btn = tkfont.Font(family="Microsoft YaHei", weight="bold")
        self.f_small = tkfont.Font(family="Microsoft YaHei")
        self._apply_fonts()

        self.bar = self.content = self.nav = None
        self._build_frame()
        self._bind_keys()
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- 字体 / 主题 ----------------
    @property
    def base_size(self) -> int:
        return self.font_sizes[self.size_idx]

    def _apply_fonts(self) -> None:
        s = self.base_size
        self.f_title.configure(size=s)
        self.f_btn.configure(size=max(18, int(s * 0.85)))
        self.f_body.configure(size=max(16, int(s * 0.6)))
        self.f_small.configure(size=max(12, int(s * 0.42)))

    @property
    def theme(self) -> Dict[str, str]:
        return THEMES[self.theme_key]

    def _build_frame(self) -> None:
        t = self.theme
        self.win.configure(bg=t["bg"])
        # 顶部无障碍工具条
        self.bar = tk.Frame(self.win, bg=t["bar"])
        self.bar.pack(side="top", fill="x")
        self._build_bar()
        # 内容区
        self.content = tk.Frame(self.win, bg=t["bg"])
        self.content.pack(side="top", fill="both", expand=True, padx=40, pady=10)
        # 底部导航
        self.nav = tk.Frame(self.win, bg=t["bar"])
        self.nav.pack(side="bottom", fill="x")

    def _build_bar(self) -> None:
        for w in self.bar.winfo_children():
            w.destroy()
        t = self.theme
        tk.Label(self.bar, text="🧓 适老化问卷", font=("Microsoft YaHei", 18, "bold"),
                 bg=t["bar"], fg=t["fg"]).pack(side="left", padx=18, pady=10)
        self._bar_button("退出", self._on_close).pack(side="right", padx=10, pady=10)
        self._bar_button("🎨 配色", self._cycle_theme).pack(side="right", padx=6, pady=10)
        self._bar_button("A－", self._font_smaller).pack(side="right", padx=2, pady=10)
        self._bar_button("A＋", self._font_larger).pack(side="right", padx=2, pady=10)
        mode_txt = "💬 对话模式" if self.mode == "standard" else "📋 标准模式"
        self._bar_button(mode_txt, self._toggle_mode).pack(side="right", padx=6, pady=10)
        self.voice_btn = self._bar_button("🔊 语音:" + ("开" if self.voice_on else "关"), self._toggle_voice)
        self.voice_btn.pack(side="right", padx=6, pady=10)

    def _refresh(self) -> None:
        """字号/主题变化后整屏重绘（先销毁旧框架，避免重复堆叠）。"""
        self._apply_fonts()
        for region in (self.bar, self.content, self.nav):
            if region is not None:
                region.destroy()
        self._build_frame()
        self._render_current()

    def _render_current(self) -> None:
        if self._screen == "welcome":
            self.show_welcome()
        elif self._screen == "question":
            self.show_question(self.current_qid, push_history=False)
        elif self._screen == "finished":
            self.show_finished()

    def _cycle_theme(self) -> None:
        keys = list(THEMES.keys())
        self.theme_key = keys[(keys.index(self.theme_key) + 1) % len(keys)]
        self._refresh()

    def _font_larger(self) -> None:
        if self.size_idx < len(self.font_sizes) - 1:
            self.size_idx += 1
            self._refresh()

    def _font_smaller(self) -> None:
        if self.size_idx > 0:
            self.size_idx -= 1
            self._refresh()

    def _toggle_voice(self) -> None:
        if not self.speech.tts_available:
            messagebox.showinfo("语音", "当前环境未安装语音引擎（pyttsx3），暂不能朗读。")
            return
        self.voice_on = not self.voice_on
        self.voice_btn.configure(text="🔊 语音:" + ("开" if self.voice_on else "关"))

    def _toggle_mode(self) -> None:
        self.mode = "conversation" if self.mode == "standard" else "standard"
        self._build_bar()  # 刷新按钮文字
        self._render_current()

    # ---------------- 通用控件（Label 实现的按钮，跨平台遵守颜色） ----------------
    def _clear_content(self) -> None:
        for w in self.content.winfo_children():
            w.destroy()
        for w in self.nav.winfo_children():
            w.destroy()

    def _flat_button(self, parent, text: str, command, *, bg: str, fg: str,
                     font=None, anchor: str = "w", padx: int = 26, pady: int = 22,
                     ring: bool = True, enabled: bool = True) -> tk.Label:
        """用 Label 模拟的按钮：完全遵守 bg/fg，避免 macOS 原生按钮忽略背景色。"""
        t = self.theme
        lbl = tk.Label(parent, text=text, font=font or self.f_btn, bg=bg,
                       fg=(fg if enabled else t["sub"]), justify="left",
                       cursor=("hand2" if enabled else "arrow"), anchor=anchor,
                       padx=padx, pady=pady, wraplength=1000,
                       highlightthickness=(3 if ring else 0),
                       highlightbackground=t["line"], highlightcolor=t["line"])
        if enabled:
            handler = self._debounce(command)
            lbl.bind("<Button-1>", lambda e: handler())
            if ring:
                lbl.bind("<Enter>", lambda e: lbl.configure(highlightbackground=t["accent"]))
                lbl.bind("<Leave>", lambda e: lbl.configure(highlightbackground=t["line"]))
        return lbl

    def _bar_button(self, text: str, command) -> tk.Label:
        t = self.theme
        return self._flat_button(self.bar, text, command, bg=t["btn"], fg=t["btn_fg"],
                                 font=("Microsoft YaHei", 16, "bold"), anchor="center",
                                 padx=14, pady=7)

    def _big_button(self, parent, text: str, command, selected: bool = False) -> tk.Label:
        """超大选项按钮：高 ≥80px、宽 ≥300px。"""
        t = self.theme
        return self._flat_button(
            parent, text, command,
            bg=(t["sel"] if selected else t["btn"]),
            fg=(t["sel_fg"] if selected else t["btn_fg"]),
            font=self.f_btn, anchor="w", padx=26, pady=22)

    def _debounce(self, fn):
        """防误触：忽略极短间隔内的重复点击，并重置超时计时。"""
        def wrapper(*a, **k):
            now = time.time() * 1000
            if now - self._last_click < self.anti_ms:
                return
            self._last_click = now
            self._reset_timeout()
            return fn(*a, **k)
        return wrapper

    # ---------------- 超时提醒 ----------------
    def _reset_timeout(self) -> None:
        if self._timeout_job:
            try:
                self.win.after_cancel(self._timeout_job)
            except Exception:  # noqa: BLE001
                pass
        if self._screen == "question":
            self._timeout_job = self.win.after(self.timeout_seconds * 1000, self._on_timeout)

    def _on_timeout(self) -> None:
        log.info("超时提醒触发")
        self._speak_current_question(prefix="您还在吗？我再读一遍题目。")
        lbl = getattr(self, "_title_label", None)
        if lbl is not None:
            try:
                lbl.configure(fg=self.theme["accent"])
                self.win.after(600, lambda: lbl.configure(fg=self.theme["fg"]))
            except Exception:  # noqa: BLE001
                pass
        self._reset_timeout()

    # ---------------- 语音 ----------------
    def _speak(self, text: str) -> None:
        if self.voice_on and self.speech.tts_available:
            self.speech.speak(text)

    def _speak_current_question(self, prefix: str = "") -> None:
        q = self.q.get(self.current_qid) if self.current_qid else None
        if not q:
            return
        text = q.get("voice_text") or q.get("title", "")
        if not q.get("voice_text") and q.get("type") in ("single", "multiple", "yesno"):
            opts = "。选项有：" + "，".join(o.get("label", "") for o in q.get("options", []))
            text += opts
        self._speak((prefix + text) if prefix else text)

    # ======================================================================
    # 屏幕：欢迎
    # ======================================================================
    def show_welcome(self) -> None:
        self._screen = "welcome"
        self._clear_content()
        t = self.theme
        tk.Label(self.content, text="🧓📋", font=("Arial", int(self.base_size * 1.4)),
                 bg=t["bg"], fg=t["fg"]).pack(pady=(30, 6))
        tk.Label(self.content, text=self.q.title(), font=self.f_title, bg=t["bg"], fg=t["fg"],
                 wraplength=1100, justify="center").pack(pady=8)
        desc = self.q.meta.get("description", "")
        if desc:
            tk.Label(self.content, text=desc, font=self.f_body, bg=t["bg"], fg=t["sub"],
                     wraplength=1000, justify="center").pack(pady=8)
        mins = self.q.meta.get("estimated_minutes")
        if mins:
            tk.Label(self.content, text=f"预计用时约 {mins} 分钟，共 {len(self.q)} 题",
                     font=self.f_small, bg=t["bg"], fg=t["sub"]).pack(pady=4)

        # 两种答题方式，直接暴露「对话模式」
        tk.Label(self.content, text="请选择答题方式：", font=self.f_body, bg=t["bg"],
                 fg=t["sub"]).pack(pady=(22, 6))
        b1 = self._big_button(self.content, "💬  对话模式 · 像聊天一样回答",
                              lambda: self._start("conversation"))
        b1.configure(bg=t["accent"], fg=t["sel_fg"], anchor="center")
        b1.pack(pady=8, ipadx=20)
        b2 = self._big_button(self.content, "📋  标准模式 · 逐题作答",
                              lambda: self._start("standard"))
        b2.configure(anchor="center")
        b2.pack(pady=8, ipadx=20)

        tk.Label(self.nav, text="提示：右上角可调整字体、切换配色或开关语音；答题中也能随时切换模式",
                 font=self.f_small, bg=t["bar"], fg=t["sub"]).pack(pady=18)

    def _start(self, mode: Optional[str] = None) -> None:
        if mode:
            self.mode = mode
            self._build_bar()
        self.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.answers = {}
        self.history = []
        first = self.q.first_id()
        if not first:
            messagebox.showerror("错误", "问卷没有题目，无法开始。")
            return
        self.show_question(first)

    # ======================================================================
    # 屏幕：题目（按模式分派）
    # ======================================================================
    def show_question(self, qid: Optional[str], push_history: bool = True) -> None:
        q = self.q.get(qid) if qid else None
        if not q:
            return self.submit()
        if push_history and self.current_qid and self.current_qid != qid:
            self.history.append(self.current_qid)
        self.current_qid = qid
        self._screen = "question"
        self._clear_content()

        if self.mode == "conversation":
            self._render_conversation(q)
        else:
            self._render_card(q)

        # 自动重读 + 启动超时计时 + 自动保存
        if self.auto_reread:
            self.win.after(300, self._speak_current_question)
        self._reset_timeout()
        self._autosave()

    # ---------------- 标准卡片模式 ----------------
    def _render_card(self, q: Dict[str, Any]) -> None:
        t = self.theme
        idx = self.q.index_of(q["id"])
        total = len(self.q)
        prog = tk.Frame(self.content, bg=t["bg"])
        prog.pack(fill="x", pady=(6, 14))
        tk.Label(prog, text=f"第 {idx + 1} / {total} 题", font=self.f_small,
                 bg=t["bg"], fg=t["sub"]).pack(side="left")
        if self.q.settings.get("show_progress", True):
            canvas = tk.Canvas(prog, height=14, bg=t["line"], highlightthickness=0)
            canvas.pack(side="left", fill="x", expand=True, padx=16)
            self.win.update_idletasks()
            w = max(canvas.winfo_width(), 400)
            ratio = (idx + 1) / total
            canvas.create_rectangle(0, 0, int(w * ratio), 14, fill=t["accent"], width=0)

        title_text = q.get("title", "") + ("  *" if q.get("required") else "")
        self._title_label = tk.Label(self.content, text=title_text, font=self.f_title,
                                     bg=t["bg"], fg=t["fg"], wraplength=1150, justify="left", anchor="w")
        self._title_label.pack(fill="x", pady=(4, 6))
        if q.get("description"):
            tk.Label(self.content, text=q["description"], font=self.f_body, bg=t["bg"], fg=t["sub"],
                     wraplength=1100, justify="left", anchor="w").pack(fill="x", pady=(0, 10))

        holder = tk.Frame(self.content, bg=t["bg"])
        holder.pack(fill="both", expand=True)
        self._render_input(holder, q)

        if q.get("help"):
            tk.Label(self.content, text="💡 " + q["help"], font=self.f_small, bg=t["bg"],
                     fg=t["accent"], wraplength=1100, justify="left", anchor="w").pack(fill="x", pady=8)
        self._build_nav(q)

    # ---------------- 对话访谈模式 ----------------
    def _render_conversation(self, q: Dict[str, Any]) -> None:
        t = self.theme
        self._title_label = None
        idx = self.q.index_of(q["id"])
        total = len(self.q)
        tk.Label(self.content, text=f"💬 访谈进行中 · 第 {idx + 1} / {total} 题",
                 font=self.f_small, bg=t["bg"], fg=t["sub"], anchor="w").pack(fill="x", pady=(0, 6))

        # 可滚动聊天区
        chat_wrap = tk.Frame(self.content, bg=t["bg"])
        chat_wrap.pack(fill="both", expand=True)
        canvas = tk.Canvas(chat_wrap, bg=t["bg"], highlightthickness=0)
        sb = tk.Scrollbar(chat_wrap, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=t["bg"])
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # 历史问答气泡
        for vqid in self.history + [q["id"]]:
            vq = self.q.get(vqid)
            if not vq:
                continue
            self._bubble(inner, vq.get("title", ""), "left")
            if vqid != q["id"] and self.answers.get(vqid) not in (None, ""):
                self._bubble(inner, self.q.answer_display(vqid, self.answers[vqid]) or "（未填）", "right")

        # 当前题输入区（在聊天区下方）
        input_box = tk.Frame(self.content, bg=t["bg"])
        input_box.pack(fill="x", pady=(10, 0))
        if q.get("description"):
            tk.Label(input_box, text=q["description"], font=self.f_small, bg=t["bg"], fg=t["sub"],
                     wraplength=1100, justify="left", anchor="w").pack(fill="x")
        self._render_input(input_box, q)
        if q.get("help"):
            tk.Label(input_box, text="💡 " + q["help"], font=self.f_small, bg=t["bg"],
                     fg=t["accent"], wraplength=1100, justify="left", anchor="w").pack(fill="x", pady=4)

        self._build_nav(q)
        self.win.after(60, lambda: canvas.yview_moveto(1.0))

    def _bubble(self, parent, text: str, side: str) -> None:
        """聊天气泡：left=访谈员，right=老人自己。"""
        t = self.theme
        row = tk.Frame(parent, bg=t["bg"])
        row.pack(fill="x", pady=6, padx=6)
        if side == "left":
            who, bg, fg, anchor = f"🗣 {self.interviewer_name}", t["btn"], t["btn_fg"], "w"
        else:
            who, bg, fg, anchor = "🙋 我", t["sel"], t["sel_fg"], "e"
        holder = tk.Frame(row, bg=t["bg"])
        holder.pack(anchor=anchor)
        tk.Label(holder, text=who, font=self.f_small, bg=t["bg"], fg=t["sub"],
                 anchor=anchor).pack(anchor=anchor, fill="x")
        tk.Label(holder, text=text, font=self.f_body, bg=bg, fg=fg, wraplength=820,
                 justify="left", anchor="w", padx=18, pady=12).pack(anchor=anchor)

    # ---------------- 答题输入控件 ----------------
    def _render_input(self, parent, q: Dict[str, Any]) -> None:
        qtype = q.get("type")
        cur = self.answers.get(q["id"])
        self._option_buttons = {}
        t = self.theme

        if qtype in ("single", "yesno"):
            for i, o in enumerate(q.get("options", [])):
                b = self._big_button(parent, f"{i + 1}. {o.get('label', '')}",
                                     lambda v=o["value"]: self._select_single(q["id"], v),
                                     selected=(cur == o["value"]))
                b.pack(fill="x", pady=10)
                self._option_buttons[o["value"]] = b

        elif qtype == "multiple":
            chosen = set(cur if isinstance(cur, list) else [])
            tk.Label(parent, text="（可多选）", font=self.f_small, bg=t["bg"], fg=t["sub"]).pack(anchor="w")
            for o in q.get("options", []):
                on = o["value"] in chosen
                b = self._big_button(parent, f"{'☑' if on else '☐'} {o.get('label', '')}",
                                     lambda v=o["value"]: self._toggle_multi(q["id"], v), selected=on)
                b.pack(fill="x", pady=10)
                self._option_buttons[o["value"]] = b

        elif qtype == "rating":
            scale = int(q.get("scale", 5))
            val = int(cur) if cur not in (None, "") else int(q.get("default", 0) or 0)
            box = tk.Frame(parent, bg=t["bg"])
            box.pack(pady=18)
            self._stars = []
            for i in range(1, scale + 1):
                star = tk.Label(box, text="★", font=("Arial", int(self.base_size * 1.0)),
                                bg=t["bg"], cursor="hand2",
                                fg=(t["accent"] if i <= val else t["line"]))
                star.bind("<Button-1>", lambda e, v=i: self._debounce(lambda: self._set_rating(q["id"], v))())
                star.pack(side="left", padx=10)
                self._stars.append(star)
            labels = tk.Frame(parent, bg=t["bg"])
            labels.pack(fill="x", padx=20)
            tk.Label(labels, text=q.get("min_label", ""), font=self.f_small, bg=t["bg"], fg=t["sub"]).pack(side="left")
            tk.Label(labels, text=q.get("max_label", ""), font=self.f_small, bg=t["bg"], fg=t["sub"]).pack(side="right")
            self._rating_hint = tk.Label(parent, text=f"当前：{val} 分", font=self.f_body, bg=t["bg"], fg=t["fg"])
            self._rating_hint.pack(pady=10)

        elif qtype == "number":
            var = tk.StringVar(value=str(cur if cur not in (None, "") else q.get("default", "")))
            self._input_vars[q["id"]] = var
            row = tk.Frame(parent, bg=t["bg"])
            row.pack(pady=22)
            self._flat_button(row, "－", lambda: self._step_number(q, -1), bg=t["btn"], fg=t["btn_fg"],
                              font=self.f_title, anchor="center", padx=20, pady=6).pack(side="left", padx=8)
            ent = tk.Entry(row, textvariable=var, font=self.f_title, width=6, justify="center",
                           bg=t["btn"], fg=t["fg"], relief="flat", bd=4, insertbackground=t["fg"])
            ent.pack(side="left", padx=12, ipady=10)
            self._flat_button(row, "＋", lambda: self._step_number(q, +1), bg=t["btn"], fg=t["btn_fg"],
                              font=self.f_title, anchor="center", padx=20, pady=6).pack(side="left", padx=8)
            if q.get("unit"):
                tk.Label(row, text=q["unit"], font=self.f_body, bg=t["bg"], fg=t["fg"]).pack(side="left", padx=10)

        elif qtype == "date":
            var = tk.StringVar(value=str(cur or ""))
            self._input_vars[q["id"]] = var
            tk.Entry(parent, textvariable=var, font=self.f_title, justify="center",
                     bg=t["btn"], fg=t["fg"], relief="flat", bd=4, insertbackground=t["fg"]).pack(pady=22, ipady=12)
            tk.Label(parent, text="请按 年-月-日 输入，例如 2026-06-03", font=self.f_small,
                     bg=t["bg"], fg=t["sub"]).pack()

        else:  # text
            txt = tk.Text(parent, font=self.f_body, height=4, wrap="word",
                          bg=t["btn"], fg=t["fg"], relief="flat", bd=6, insertbackground=t["fg"])
            txt.pack(fill="x", pady=16)
            if cur:
                txt.insert("1.0", str(cur))
            self._input_vars[q["id"]] = txt

    # ---------------- 选项交互 ----------------
    def _select_single(self, qid: str, value: Any) -> None:
        self.answers[qid] = value
        for v, b in self._option_buttons.items():
            sel = (v == value)
            b.configure(bg=self.theme["sel"] if sel else self.theme["btn"],
                        fg=self.theme["sel_fg"] if sel else self.theme["btn_fg"])
        self._autosave()
        self._speak(self.q.option_label(qid, value))

    def _toggle_multi(self, qid: str, value: Any) -> None:
        chosen = set(self.answers.get(qid, []) if isinstance(self.answers.get(qid), list) else [])
        chosen.discard(value) if value in chosen else chosen.add(value)
        self.answers[qid] = list(chosen)
        self.show_question(qid, push_history=False)  # 重绘以更新 ☑/☐

    def _set_rating(self, qid: str, value: int) -> None:
        self.answers[qid] = value
        for i, star in enumerate(self._stars, 1):
            star.configure(fg=self.theme["accent"] if i <= value else self.theme["line"])
        if hasattr(self, "_rating_hint"):
            self._rating_hint.configure(text=f"当前：{value} 分")
        self._autosave()
        self._speak(f"{value} 分")

    def _step_number(self, q: Dict[str, Any], delta: int) -> None:
        var = self._input_vars.get(q["id"])
        try:
            v = int(float(var.get() or 0))
        except ValueError:
            v = 0
        v += delta
        lo, hi = q.get("min"), q.get("max")
        if lo is not None:
            v = max(int(lo), v)
        if hi is not None:
            v = min(int(hi), v)
        var.set(str(v))

    # ---------------- 导航 ----------------
    def _build_nav(self, q: Dict[str, Any]) -> None:
        t = self.theme
        is_last = self.q.next_id(q["id"], self.answers.get(q["id"])) == "END"
        prev = self._flat_button(self.nav, "←  上一题", self.go_prev, bg=t["btn"], fg=t["btn_fg"],
                                 anchor="center", padx=24, pady=16, enabled=bool(self.history))
        prev.pack(side="left", padx=30, pady=16)
        self._flat_button(self.nav, "🔊 再读一遍", lambda: self._speak_current_question(),
                          bg=t["btn"], fg=t["btn_fg"], anchor="center", padx=18, pady=16).pack(side="left", padx=10, pady=16)
        nxt = self._flat_button(self.nav, "提交问卷  ✓" if is_last else "下一题  →", self.go_next,
                                bg=t["accent"], fg=t["sel_fg"], anchor="center", padx=34, pady=16)
        nxt.pack(side="right", padx=30, pady=16)

    def _collect_input(self, qid: str) -> None:
        """把输入型控件（数字/日期/文本）的值收集到 answers。"""
        q = self.q.get(qid)
        if not q:
            return
        if q.get("type") in ("number", "date"):
            var = self._input_vars.get(qid)
            if var is not None:
                val = var.get().strip()
                if q["type"] == "number" and val != "":
                    try:
                        val = int(float(val))
                    except ValueError:
                        pass
                self.answers[qid] = val
        elif q.get("type") == "text":
            txt = self._input_vars.get(qid)
            if txt is not None:
                self.answers[qid] = txt.get("1.0", "end").strip()

    def go_next(self) -> None:
        qid = self.current_qid
        self._collect_input(qid)
        ans = self.answers.get(qid)
        ok, msg = self.q.validate_answer(qid, ans)
        if not ok:
            messagebox.showwarning("提示", msg)
            self._speak(msg)
            return
        nxt = self.q.next_id(qid, ans)
        self._autosave()
        if nxt == "END" or nxt is None:
            self.submit()
        else:
            self.show_question(nxt)

    def go_prev(self) -> None:
        if not self.history:
            return
        self._collect_input(self.current_qid)
        prev = self.history.pop()
        self.current_qid = prev
        self.show_question(prev, push_history=False)

    # ---------------- 自动保存 ----------------
    def _autosave(self) -> None:
        self.autosave.save({
            "response_id": self.response_id,
            "questionnaire_id": self.q.meta.get("id", ""),
            "started_at": self.started_at,
            "current_qid": self.current_qid,
            "answers": self.answers,
            "history": self.history,
            "mode": self.mode,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

    def maybe_resume(self) -> bool:
        """启动时若存在未完成进度，询问是否继续。返回是否已恢复。"""
        state = self.autosave.load()
        if not state or not state.get("answers"):
            return False
        if not messagebox.askyesno("继续上次", "检测到上次未答完的问卷，是否从上次的位置继续？"):
            self.autosave.clear()
            return False
        self.response_id = state.get("response_id", self.response_id)
        self.started_at = state.get("started_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.answers = state.get("answers", {})
        self.history = state.get("history", [])
        self.mode = state.get("mode", self.mode)
        self._build_bar()
        qid = state.get("current_qid") or self.q.first_id()
        self.show_question(qid, push_history=False)
        return True

    # ======================================================================
    # 提交 / 完成
    # ======================================================================
    def submit(self) -> None:
        finished = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        duration = 0.0
        if self.started_at:
            duration = (datetime.strptime(finished, "%Y-%m-%d %H:%M:%S")
                        - datetime.strptime(self.started_at, "%Y-%m-%d %H:%M:%S")).total_seconds()
        record = {
            "response_id": self.response_id,
            "questionnaire_id": self.q.meta.get("id", ""),
            "started_at": self.started_at or finished,
            "finished_at": finished,
            "duration_seconds": round(duration, 1),
            "completed": True,
            "answers": self.answers,
        }
        ok = self.data.save_response(record)
        self.autosave.clear()
        if not ok:
            messagebox.showerror("保存失败", "答卷保存失败，请联系工作人员。")
        self.show_finished()

    def show_finished(self) -> None:
        self._screen = "finished"
        if self._timeout_job:
            try:
                self.win.after_cancel(self._timeout_job)
            except Exception:  # noqa: BLE001
                pass
        self._clear_content()
        t = self.theme
        tk.Label(self.content, text="🎉", font=("Arial", int(self.base_size * 2)),
                 bg=t["bg"], fg=t["fg"]).pack(pady=(60, 10))
        tk.Label(self.content, text="感谢您的参与！", font=self.f_title, bg=t["bg"], fg=t["fg"]).pack(pady=10)
        tk.Label(self.content, text="您的回答已经保存，祝您生活愉快、身体健康。",
                 font=self.f_body, bg=t["bg"], fg=t["sub"], wraplength=1000, justify="center").pack(pady=10)
        self._speak("感谢您的参与，您的回答已经保存。")

        again = self._big_button(self.content, "📝 再填一份", self._restart)
        again.configure(bg=t["accent"], fg=t["sel_fg"], anchor="center")
        again.pack(pady=30, ipadx=30)
        quit_btn = self._big_button(self.content, "退出", self._on_close)
        quit_btn.configure(anchor="center")
        quit_btn.pack(pady=4, ipadx=30)

    def _restart(self) -> None:
        self.response_id = dm.DataManager.new_response_id()
        self.answers, self.history, self.current_qid = {}, [], None
        self.show_welcome()

    # ---------------- 键盘 ----------------
    def _bind_keys(self) -> None:
        self.win.bind("<Escape>", lambda e: self._on_close())
        self.win.bind("<Right>", lambda e: self._key_next())
        self.win.bind("<Return>", lambda e: self._key_next())
        self.win.bind("<Left>", lambda e: self.go_prev() if self._screen == "question" else None)
        for n in range(1, 10):
            self.win.bind(str(n), lambda e, k=n: self._key_number(k))

    def _key_next(self) -> None:
        if self._screen == "welcome":
            self._start()
        elif self._screen == "question":
            self.go_next()

    def _key_number(self, n: int) -> None:
        if self._screen != "question":
            return
        q = self.q.get(self.current_qid)
        if not q:
            return
        opts = q.get("options", [])
        if q.get("type") in ("single", "yesno") and n <= len(opts):
            self._select_single(q["id"], opts[n - 1]["value"])
        elif q.get("type") == "multiple" and n <= len(opts):
            self._toggle_multi(q["id"], opts[n - 1]["value"])
        elif q.get("type") == "rating" and n <= int(q.get("scale", 5)):
            self._set_rating(q["id"], n)

    # ---------------- 关闭 ----------------
    def _on_close(self) -> None:
        if self._screen == "question":
            if not messagebox.askyesno("退出", "确定要退出吗？已答内容会自动保存，下次可继续。"):
                return
        try:
            self.win.destroy()
        except Exception:  # noqa: BLE001
            pass

    # ---------------- 运行 ----------------
    def run(self) -> None:
        if not self.maybe_resume():
            self.show_welcome()
        if self.owns_loop:
            self.win.mainloop()


# ======================================================================
# 入口
# ======================================================================
def launch(config: Dict[str, Any], master: Optional[tk.Misc] = None) -> Optional[SurveyClient]:
    """启动答题端。master 非空时作为子窗口（不自占主循环）。"""
    try:
        app = SurveyClient(config, master=master)
    except tk.TclError as exc:
        log.error("无法创建图形界面（可能无显示环境）：%s", exc)
        raise
    app.run()
    return app
