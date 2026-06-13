#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ElderAI Survey Platform - 统一启动入口
适老化智能问卷与AI数据分析平台

用法：
    python main.py            # 启动图形化主控台（启动器）
    python main.py --check    # 自检模式：仅校验环境与配置，不打开窗口
    python main.py --builder  # 直接用浏览器打开问卷设计器
    python main.py --survey   # 直接进入老人答题端
    python main.py --analytics# 直接进入数据分析中心
    python main.py --dashboard# 直接进入科交会大屏

设计原则：
    各功能模块采用“惰性导入”，单个模块缺失或报错不影响启动器本身，
    便于分阶段开发与自检。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

# 项目根目录（main.py 所在目录），统一以此解析相对路径
BASE_DIR = Path(__file__).resolve().parent
# 把项目根目录加入模块搜索路径，保证 `import modules.xxx` 可用
sys.path.insert(0, str(BASE_DIR))


# ======================================================================
# 配置加载
# ======================================================================
def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """加载全局配置 config/config.json。

    Args:
        config_path: 配置文件路径，默认 BASE_DIR/config/config.json

    Returns:
        配置字典；文件缺失或解析失败时返回空字典并记录日志。
    """
    if config_path is None:
        config_path = BASE_DIR / "config" / "config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error("配置文件不存在：%s", config_path)
    except json.JSONDecodeError as exc:
        logging.error("配置文件 JSON 解析失败：%s", exc)
    return {}


def save_config(config: Dict[str, Any], config_path: Optional[Path] = None) -> bool:
    """把配置写回 config/config.json（用于记忆界面主题等设置）。"""
    if config_path is None:
        config_path = BASE_DIR / "config" / "config.json"
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except OSError as exc:
        logging.error("保存配置失败：%s", exc)
        return False


# ======================================================================
# 日志系统
# ======================================================================
def setup_logging(config: Dict[str, Any]) -> logging.Logger:
    """初始化日志系统：同时输出到控制台与 logs/app.log（滚动）。"""
    log_dir = BASE_DIR / config.get("paths", {}).get("logs", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    level = logging.DEBUG if config.get("app", {}).get("debug") else logging.INFO

    logger = logging.getLogger()
    logger.setLevel(level)
    # 避免重复添加 handler（多次调用时）
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    return logger


# ======================================================================
# 启动器主控台（tkinter）
# ======================================================================
# 启动器主题：亮色（默认）+ 暗色，可在界面右上角一键切换
LAUNCHER_THEMES = {
    "light": {
        "bg": "#eef2f8",          # 窗口背景（浅石板）
        "bg2": "#ffffff",         # 头部
        "card": "#ffffff",        # 卡片背景
        "card_hover": "#eef4ff",  # 卡片悬停
        "border": "#dde5f0",      # 卡片描边
        "title": "#0f172a",       # 主文字
        "muted": "#5b6b85",       # 次文字
        "faint": "#94a3b8",       # 弱文字
        "accent": "#2563eb",      # 主强调色
        "link": "#2563eb",
        "link_hi": "#1d4ed8",
    },
    "dark": {
        "bg": "#0b1220",          # 窗口背景（深石板蓝）
        "bg2": "#0e1730",         # 头部
        "card": "#16213a",        # 卡片背景
        "card_hover": "#1f2d4d",  # 卡片悬停
        "border": "#26344f",      # 卡片描边
        "title": "#f1f5f9",       # 主文字
        "muted": "#9aa7bd",       # 次文字
        "faint": "#5d6e8c",       # 弱文字
        "accent": "#38bdf8",      # 主强调色
        "link": "#38bdf8",
        "link_hi": "#7dd3fc",
    },
}


class LauncherApp:
    """图形化主控台：一个窗口集中启动 5 大模块。

    各模块按钮点击时才惰性导入对应模块，缺失则弹出友好提示，
    不会导致启动器崩溃。
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        import tkinter as tk  # 局部导入，--check 模式无需 GUI 依赖

        self.config = config
        self.log = logging.getLogger("launcher")
        self.tk = tk
        # 界面主题：亮色 / 暗色（默认亮色），可在右上角切换并记忆
        self.ui_theme = config.get("ui", {}).get("theme", "light")
        if self.ui_theme not in LAUNCHER_THEMES:
            self.ui_theme = "light"
        self.lc = LAUNCHER_THEMES[self.ui_theme]

        self.root = tk.Tk()
        self.root.title(config.get("app", {}).get("name_zh", "适老化智能问卷平台"))
        self.root.configure(bg=self.lc["bg"])
        self.root.minsize(720, 640)
        self._center(900, 810)
        self._build_ui()

    def _center(self, w: int, h: int) -> None:
        """把窗口居中显示。"""
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 3)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    @staticmethod
    def _blend(c1: str, c2: str, t: float) -> str:
        """按比例 t 混合两个 #RRGGBB 颜色（t=0 取 c1，t=1 取 c2）。"""
        a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
        m = [round(a[i] * (1 - t) + b[i] * t) for i in range(3)]
        return "#%02x%02x%02x" % tuple(m)

    def _build_ui(self) -> None:
        tk = self.tk
        lc = self.lc
        app_name = self.config.get("app", {}).get("name_zh", "适老化智能问卷平台")
        version = self.config.get("app", {}).get("version", "1.0.0")

        # ---- 头部 ----
        header = tk.Frame(self.root, bg=lc["bg2"])
        header.pack(fill="x")
        tk.Label(header, text="🧓", font=("Arial", 40), bg=lc["bg2"], fg=lc["title"]).pack(pady=(30, 2))
        tk.Label(header, text=app_name, font=("Microsoft YaHei", 24, "bold"),
                 bg=lc["bg2"], fg=lc["title"]).pack()
        tk.Label(header, text=f"ElderAI Survey Platform   ·   v{version}",
                 font=("Arial", 12), bg=lc["bg2"], fg=lc["faint"]).pack(pady=(5, 0))
        tk.Frame(header, bg=lc["accent"], height=3, width=68).pack(pady=(14, 22))

        # ---- 主题切换（右上角）----
        self._theme_btn = tk.Label(
            self.root, text=("🌙 暗色" if self.ui_theme == "light" else "☀️ 亮色"),
            font=("Microsoft YaHei", 11, "bold"), bg=lc["card"], fg=lc["title"],
            padx=14, pady=6, cursor="hand2", highlightthickness=1,
            highlightbackground=lc["border"], highlightcolor=lc["border"])
        self._theme_btn.place(relx=1.0, y=16, x=-18, anchor="ne")
        self._theme_btn.bind("<Button-1>", lambda e: self._toggle_theme())
        self._theme_btn.bind("<Enter>", lambda e: self._theme_btn.configure(bg=lc["card_hover"]))
        self._theme_btn.bind("<Leave>", lambda e: self._theme_btn.configure(bg=lc["card"]))

        # ---- 页脚（先锚定底部）----
        tk.Label(self.root, text="支持离线运行 · 联网增强 · 本地部署",
                 font=("Arial", 10), bg=lc["bg"], fg=lc["faint"]).pack(side="bottom", pady=(0, 12))
        self._build_credit(self.root)

        # ---- 模块卡片（最后铺满中部）----
        modules = [
            ("📝", "问卷设计器", "管理员可视化设计问卷，生成 questionnaire.json", "#3b82f6", self.open_builder),
            ("🧓", "老人答题端", "适老化大字体、高对比、语音播报答题界面", "#10b981", self.open_survey),
            ("📊", "数据分析中心", "查看 · 筛选 · 统计 · 交叉分析 · 导出", "#f59e0b", self.open_analytics),
            ("📺", "科交会大屏", "全屏数据驾驶舱，自动轮播与实时刷新", "#06b6d4", self.open_dashboard),
            ("🤖", "AI 分析报告", "生成调查结论、洞察并导出 Excel/PDF/Word", "#a78bfa", self.open_ai_report),
            ("📞", "回访管理", "分配受试者 · 学生查询 · 完成情况统计", "#8b5cf6", self.open_followup),
        ]
        container = tk.Frame(self.root, bg=lc["bg"])
        container.pack(fill="both", expand=True, padx=46)
        for icon, title, desc, accent, handler in modules:
            self._module_card(container, icon, title, desc, accent, handler)

    def _toggle_theme(self) -> None:
        """在亮色 / 暗色之间切换，并记忆到配置。"""
        self.ui_theme = "dark" if self.ui_theme == "light" else "light"
        self.lc = LAUNCHER_THEMES[self.ui_theme]
        self.config.setdefault("ui", {})["theme"] = self.ui_theme
        save_config(self.config)
        self._rebuild()

    def _rebuild(self) -> None:
        """按当前主题重绘整个主控台。"""
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=self.lc["bg"])
        self._build_ui()

    def _module_card(self, parent, icon: str, title: str, desc: str,
                     accent: str, handler) -> None:
        """模块卡片：左侧色条 + 图标 chip + 标题/描述 + 箭头，悬停整卡高亮。"""
        tk = self.tk
        chip = self._blend(accent, self.lc["card"], 0.72)          # 图标底色（常态）
        chip_h = self._blend(accent, self.lc["card_hover"], 0.60)  # 图标底色（悬停）

        card = tk.Frame(parent, bg=self.lc["card"], highlightthickness=1,
                        highlightbackground=self.lc["border"], highlightcolor=self.lc["border"],
                        cursor="hand2")
        card.pack(fill="x", pady=7)

        strip = tk.Frame(card, bg=accent, width=5)
        strip.pack(side="left", fill="y")

        chip_box = tk.Frame(card, bg=chip)
        chip_box.pack(side="left", padx=(16, 12), pady=12)
        icon_lbl = tk.Label(chip_box, text=icon, font=("Arial", 26), bg=chip, padx=10, pady=4)
        icon_lbl.pack()

        chevron = tk.Label(card, text="›", font=("Arial", 30, "bold"), bg=self.lc["card"], fg=accent)
        chevron.pack(side="right", padx=20)

        txt = tk.Frame(card, bg=self.lc["card"])
        txt.pack(side="left", fill="both", expand=True, pady=12)
        title_lbl = tk.Label(txt, text=title, font=("Microsoft YaHei", 17, "bold"),
                             bg=self.lc["card"], fg=self.lc["title"], anchor="w")
        title_lbl.pack(anchor="w")
        desc_lbl = tk.Label(txt, text=desc, font=("Microsoft YaHei", 11),
                            bg=self.lc["card"], fg=self.lc["muted"], anchor="w")
        desc_lbl.pack(anchor="w", pady=(3, 0))

        card_widgets = [card, chevron, txt, title_lbl, desc_lbl]
        chip_widgets = [chip_box, icon_lbl]

        def on() -> None:
            for w in card_widgets:
                w.configure(bg=self.lc["card_hover"])
            for w in chip_widgets:
                w.configure(bg=chip_h)
            card.configure(highlightbackground=accent, highlightcolor=accent)
            chevron.configure(fg=self.lc["title"])

        def off() -> None:
            for w in card_widgets:
                w.configure(bg=self.lc["card"])
            for w in chip_widgets:
                w.configure(bg=chip)
            card.configure(highlightbackground=self.lc["border"], highlightcolor=self.lc["border"])
            chevron.configure(fg=accent)

        all_widgets = [card, strip, chip_box, icon_lbl, chevron, txt, title_lbl, desc_lbl]
        self._hover_bind(card, all_widgets, on, off)
        for w in all_widgets:
            w.bind("<Button-1>", lambda e: handler())

    def _hover_bind(self, card, widgets, on, off) -> None:
        """整卡悬停：子控件间移动不闪烁（离开后延时确认指针真的移出卡片）。"""
        state = {"in": False}

        def enter(_=None) -> None:
            if not state["in"]:
                state["in"] = True
                on()

        def leave(_=None) -> None:
            def check() -> None:
                x, y = card.winfo_pointerxy()
                cx, cy = card.winfo_rootx(), card.winfo_rooty()
                if not (cx <= x < cx + card.winfo_width()
                        and cy <= y < cy + card.winfo_height()):
                    state["in"] = False
                    off()
            card.after(25, check)

        for w in widgets:
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)

    def _build_credit(self, parent) -> None:
        """页脚署名 + 可点击的联系链接。"""
        tk = self.tk
        about = self.config.get("about", {})
        # 课题组/单位名称：优先 about.organization，其次复用 export.company_name，最后兜底
        org = (about.get("organization")
               or self.config.get("export", {}).get("company_name")
               or "课题组")
        author = about.get("author", "Jiacheng Zheng")
        credit = about.get("credit", "使用 Claude Code 辅助开发")
        label = about.get("contact_label", "联系我")
        url = about.get("contact_url", "")

        footer = tk.Frame(parent, bg=self.lc["bg"])
        footer.pack(side="bottom", pady=(8, 2))
        tk.Label(footer, text=f"© {org}  ·  {author} {credit}  ·  ",
                 font=("Microsoft YaHei", 10), fg=self.lc["muted"], bg=self.lc["bg"]).pack(side="left")
        link = tk.Label(footer, text=label, font=("Microsoft YaHei", 10, "underline"),
                        fg=self.lc["link"], bg=self.lc["bg"], cursor="hand2")
        link.pack(side="left")
        if url:
            link.bind("<Button-1>", lambda e: webbrowser.open(url))
            link.bind("<Enter>", lambda e: link.configure(fg=self.lc["link_hi"]))
            link.bind("<Leave>", lambda e: link.configure(fg=self.lc["link"]))

    # ---- 模块入口（惰性导入，缺失则提示开发中）----
    def _safe_launch(self, importer, label: str) -> None:
        """统一的惰性启动包装：捕获导入/运行异常并提示。"""
        from tkinter import messagebox
        try:
            importer()
        except ImportError as exc:
            self.log.warning("模块尚未就绪 [%s]：%s", label, exc)
            messagebox.showinfo("提示", f"【{label}】模块尚在开发阶段。\n\n详情：{exc}")
        except Exception as exc:  # noqa: BLE001  顶层兜底，避免启动器崩溃
            self.log.exception("启动 [%s] 失败", label)
            messagebox.showerror("错误", f"启动【{label}】失败：\n{exc}")

    def open_builder(self) -> None:
        self._safe_launch(lambda: open_builder_in_browser(self.config), "问卷设计器")

    def open_survey(self) -> None:
        def _run() -> None:
            from modules import survey_gui
            survey_gui.launch(self.config, master=self.root)
        self._safe_launch(_run, "老人答题端")

    def open_analytics(self) -> None:
        def _run() -> None:
            from modules import analytics
            analytics.launch(self.config, master=self.root)
        self._safe_launch(_run, "数据分析中心")

    def open_dashboard(self) -> None:
        def _run() -> None:
            from modules import dashboard
            dashboard.launch(self.config, master=self.root)
        self._safe_launch(_run, "科交会大屏")

    def open_ai_report(self) -> None:
        def _run() -> None:
            from modules import report_generator
            report_generator.launch(self.config, master=self.root)
        self._safe_launch(_run, "AI分析报告")

    def open_followup(self) -> None:
        def _run() -> None:
            # 随访管理面板：上传名单 → 分配 → 生成查询页 → 完成统计
            from followup import followup_panel
            followup_panel.launch(self.config, master=self.root)
        self._safe_launch(_run, "回访管理")

    def run(self) -> None:
        self.root.mainloop()


# ======================================================================
# 问卷设计器：用默认浏览器打开纯前端 HTML
# ======================================================================
def open_builder_in_browser(config: Dict[str, Any]) -> None:
    """用系统默认浏览器打开 builder/survey_builder.html。"""
    html = BASE_DIR / "builder" / "survey_builder.html"
    if not html.exists():
        raise ImportError(f"设计器文件不存在：{html}")
    webbrowser.open(html.as_uri())
    logging.getLogger("launcher").info("已在浏览器打开问卷设计器：%s", html)


# ======================================================================
# 自检模式
# ======================================================================
def run_self_check(config: Dict[str, Any]) -> int:
    """环境与配置自检，返回 0 表示通过，非 0 表示存在问题。"""
    log = logging.getLogger("self-check")
    problems = 0

    log.info("===== 开始自检 =====")

    # 1) Python 版本
    if sys.version_info < (3, 9):
        log.error("Python 版本过低：%s（需 3.9+）", sys.version.split()[0])
        problems += 1
    else:
        log.info("Python 版本：%s ✓", sys.version.split()[0])

    # 2) 配置
    if not config:
        log.error("配置加载失败")
        problems += 1
    else:
        log.info("配置加载：%s ✓", config.get("app", {}).get("name", "?"))

    # 3) 关键目录
    for key in ("exports", "backup", "logs"):
        d = BASE_DIR / config.get("paths", {}).get(key, key)
        d.mkdir(parents=True, exist_ok=True)
        log.info("目录就绪：%s ✓", d.relative_to(BASE_DIR))

    # 4) 问卷文件
    q_path = BASE_DIR / config.get("paths", {}).get(
        "questionnaire", "survey/questionnaire.json"
    )
    if not q_path.exists():
        log.error("问卷文件缺失：%s", q_path)
        problems += 1
    else:
        try:
            with open(q_path, "r", encoding="utf-8") as f:
                q = json.load(f)
            n = len(q.get("questions", []))
            log.info("问卷加载：《%s》共 %d 题 ✓", q.get("meta", {}).get("title", "?"), n)
        except json.JSONDecodeError as exc:
            log.error("问卷 JSON 解析失败：%s", exc)
            problems += 1

    # 5) tkinter 可用性（仅尝试导入，不创建窗口）
    try:
        import tkinter  # noqa: F401
        log.info("tkinter 可用 ✓")
    except Exception as exc:  # noqa: BLE001
        log.warning("tkinter 不可用（图形界面将无法启动）：%s", exc)

    # 6) 可选依赖巡检（缺失不算错误，仅提示降级）
    optional = {
        "pandas": "数据分析", "numpy": "数值计算", "matplotlib": "图表",
        "openpyxl": "Excel导出", "reportlab": "PDF导出", "docx": "Word导出",
        "pyttsx3": "离线语音", "requests": "联网AI",
    }
    for mod, usage in optional.items():
        try:
            __import__(mod)
            log.info("可选依赖 %-10s 可用 ✓（%s）", mod, usage)
        except ImportError:
            log.warning("可选依赖 %-10s 缺失（%s 将降级或不可用）", mod, usage)

    log.info("===== 自检结束：%s =====", "全部通过" if problems == 0 else f"{problems} 项需处理")
    return problems


# ======================================================================
# 入口
# ======================================================================
def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="适老化智能问卷与AI数据分析平台")
    parser.add_argument("--check", action="store_true", help="自检模式，不打开窗口")
    parser.add_argument("--seed", nargs="?", const=200, type=int, metavar="N",
                        help="生成 N 份模拟答卷用于展示（默认 200，会清空已有数据）")
    parser.add_argument("--builder", action="store_true", help="直接打开问卷设计器")
    parser.add_argument("--survey", action="store_true", help="直接进入老人答题端")
    parser.add_argument("--analytics", action="store_true", help="直接进入数据分析中心")
    parser.add_argument("--dashboard", action="store_true", help="直接进入科交会大屏")
    args = parser.parse_args(argv)

    config = load_config()
    setup_logging(config)
    log = logging.getLogger("main")

    if args.check:
        return run_self_check(config)

    if args.seed is not None:
        from modules import report_generator
        count = report_generator.generate_sample_data(config, n=args.seed, reset=True)
        log.info("已生成 %d 份模拟答卷（用于展示）。", count)
        return 0

    # 直达模式
    try:
        if args.builder:
            open_builder_in_browser(config)
            return 0
        if args.survey:
            from modules import survey_gui
            survey_gui.launch(config)
            return 0
        if args.analytics:
            from modules import analytics
            analytics.launch(config)
            return 0
        if args.dashboard:
            from modules import dashboard
            dashboard.launch(config)
            return 0
    except ImportError as exc:
        log.error("该模块尚未就绪：%s", exc)
        return 1

    # 默认：图形化启动器
    try:
        app = LauncherApp(config)
    except Exception as exc:  # noqa: BLE001
        log.error("无法创建图形界面（可能无显示环境）：%s", exc)
        log.info("可使用 `python main.py --check` 进行无界面自检。")
        return 1
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
