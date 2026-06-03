# ElderAI Survey Platform · 适老化智能问卷与 AI 数据分析平台

> 面向**老年人**、可**离线运行 / 联网增强 / 本地部署**的一体化智能问卷系统，覆盖「问卷设计 → 适老化答题 → 数据分析 → 大屏展示 → AI 报告」的完整闭环。
>
> A bilingual, **offline-first / online-enhanced / locally-deployable** survey platform built for **senior citizens**, covering the full loop: *design → accessible answering → analytics → big-screen showcase → AI reporting*.

**核心理念 · Core principle**：问卷**不写死在代码里**。整个系统由单一配置文件 `survey/questionnaire.json` 驱动，设计器、老人端、分析端、大屏端读取**同一份**问卷定义。
*The questionnaire is **never hard-coded**. The whole system is driven by one config file `survey/questionnaire.json`; the builder, client, analytics and dashboard all read the **same** definition.*

---

## 目录 · Table of Contents

- [五大模块 · Modules](#五大模块--modules)
- [系统架构 · Architecture](#系统架构--architecture)
- [技术栈 · Tech Stack](#技术栈--tech-stack)
- [技术实现路径 · Technical Implementation](#技术实现路径--technical-implementation)
- [项目结构 · Project Structure](#项目结构--project-structure)
- [快速开始 · Quick Start](#快速开始--quick-start)
- [使用方法 · Usage](#使用方法--usage)
- [配置说明 · Configuration](#配置说明--configuration)
- [离线 / 联网与降级 · Offline / Online & Degradation](#离线--联网与降级--offline--online--degradation)
- [测试与质量 · Testing & Quality](#测试与质量--testing--quality)
- [常见问题 · FAQ](#常见问题--faq)
- [作者 · Author](#作者--author)

---

## 五大模块 · Modules

| 模块 · Module | 说明 · Description | 技术 · Tech |
| --- | --- | --- |
| 📝 问卷设计器 · Survey Builder | 可视化增删题、拖拽排序、逻辑跳转、流程图、自动校验、模拟预览，导出标准 JSON · Visual editing, drag-sort, branching logic, flowchart, validation, live preview → standard JSON | 纯前端 HTML/CSS/JS · Pure frontend |
| 🧓 老人答题端 · Survey Client | 超大字体、高对比、超大按钮、语音播报、自动保存与断点恢复 · Huge fonts, high contrast, big buttons, TTS, autosave & resume | `tkinter` |
| 📊 数据分析中心 · Analytics | 查看/筛选/搜索/删除/导出，自动统计与交叉分析 · View/filter/search/delete/export, auto stats & cross-tabs | `tkinter` + `pandas` |
| 📺 科交会大屏 · Dashboard | 全屏科技蓝驾驶舱，自动轮播 + 实时刷新 · Full-screen cockpit, auto carousel + live refresh | `tkinter` + `matplotlib` |
| 🤖 AI 分析引擎 · AI Engine | 离线规则 + 联网 LLM，自动生成洞察与报告 · Offline rules + online LLM, auto insights & reports | Rule engine / OpenAI·DeepSeek·Qwen·OpenRouter |

---

## 系统架构 · Architecture

所有模块围绕一份问卷定义与一套数据层协作；箭头表示数据流向。
*Everything revolves around one questionnaire definition and one data layer; arrows show data flow.*

```
                        ┌──────────────────────────┐
   设计 Design          │  builder/ (HTML+CSS+JS)   │  浏览器 / Browser
                        │  可视化设计器 Survey Builder │
                        └─────────────┬────────────┘
                                      │  导出 export
                                      ▼
                       ┌───────────────────────────────┐
   真相源 Source of     │   survey/questionnaire.json    │ ◀── 单一配置 single config
   Truth               └───────────────┬───────────────┘
                                       │ 读取 read
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                              ▼                               ▼
┌───────────────┐            ┌──────────────────┐             ┌─────────────────┐
│ survey_gui.py │            │  analytics.py    │             │  dashboard.py   │
│ 老人答题端     │            │  分析中心 Analyzer │             │  科交会大屏      │
│ Client        │            └────────┬─────────┘             └────────┬────────┘
└───────┬───────┘                     │ stats(dict)                    │
        │ 答卷 record                  ▼                                ▼
        ▼                    ┌──────────────────┐             ┌─────────────────┐
┌─────────────────────────┐ │   ai_engine.py   │────────────▶│ report_generator│
│     data_manager.py     │ │ 离线规则 / 联网LLM │  report     │  Excel/PDF/Word │
│  CSV + SQLite 双存储     │ └──────────────────┘             └─────────────────┘
│  Dual storage           │
└─────────────────────────┘
        ▲
        │ 引擎 engine：加载/逻辑跳转/答案校验  load / branching / validation
┌─────────────────────────────────────────────┐
│ questionnaire_engine.py + validation_engine.py│
└─────────────────────────────────────────────┘
```

统一入口 `main.py` 以**惰性导入**装载各模块——任一模块缺失或异常都不会拖垮主控台。
*The single entry `main.py` lazy-loads each module, so a missing/broken module can never crash the launcher.*

---

## 技术栈 · Tech Stack

| 领域 · Area | 选型 · Choice |
| --- | --- |
| 运行环境 · Runtime | Python 3.11+（已在 3.13 验证 · verified on 3.13） |
| 界面 · GUI | `tkinter`（标准库，零额外依赖 · stdlib, zero extra deps） |
| 数据 · Data | `pandas` · `numpy` · `sqlite3`（标准库 · stdlib） |
| 图表 · Charts | `matplotlib`（嵌入 tkinter / 导出 PNG · embedded & PNG export） |
| 导出 · Export | `openpyxl`(Excel) · `reportlab`(PDF) · `python-docx`(Word) |
| 语音 · Speech | `pyttsx3`(TTS) · `vosk`+`SpeechRecognition`(离线 ASR) |
| 联网 AI · Online AI | `requests` → OpenAI 兼容接口 · OpenAI-compatible API |
| 设计器 · Builder | 原生 HTML/CSS/JavaScript（无框架、无服务器 · no framework, no server） |

> `tkinter` / `sqlite3` / `json` / `threading` / `logging` 为标准库；语音与联网依赖**缺失即自动降级**，不影响核心运行。
> *Speech & online deps gracefully degrade when missing; the core always runs.*

---

## 技术实现路径 · Technical Implementation

这一节说明「**怎么实现的**」——关键设计与算法。
*This section explains **how it is built** — the key designs and algorithms.*

### 1. 配置驱动 · Config-driven single source of truth
问卷以一份 JSON 描述：`meta`（元信息）/ `settings`（行为）/ `questions[]`。每题含 `id / type / title / options / logic / required / voice_text` 等字段，支持 7 种题型：`single, multiple, yesno, rating, text, number, date`。新增、修改问卷**无需改动任何代码**。
*One JSON describes the whole survey; adding or changing a survey needs **no code change**.*

### 2. 逻辑跳转引擎（前后端语义一致）· Branching engine with JS↔Python parity
跳转规则为 `{op, value, goto}`，运算符 `equals / not_equals / contains / greater_than / less_than / between`。求值在两端**独立实现但语义完全一致**：设计器预览 [`builder.js`](builder/builder.js) 的 `evaluateRule/computeNext` 与运行时 [`questionnaire_engine.py`](modules/questionnaire_engine.py) 的 `evaluate_rule/next_id`。两者通过单元测试交叉验证（如 `Q5=否 → Q14`）。
*Branching is evaluated independently in JS (builder preview) and Python (runtime) with identical semantics, cross-checked by tests.*

### 3. 图论校验引擎 · Graph-based validation
保存/导出前自动校验，**发现致命错误则禁止导出**。把问卷建成有向图（逻辑边 + 顺序兜底边 + `END` 终点），并运行：
- **可达性 BFS** → 检测「孤立题目」(orphan)
- **反向可达 BFS** → 检测「无终点路径」(no-endpoint)
- **DFS 回边检测** → 检测「死循环跳转」(cycle)
- 结构检查 → 重复 ID、空题干、缺/重选项、非法逻辑值

设计器 [`builder.js`](builder/builder.js) 与命令行 [`validation_engine.py`](modules/validation_engine.py) 实现同一套算法，结果一致。
*A directed graph drives BFS (orphans), reverse-BFS (dead ends) and DFS back-edge (cycles); same algorithm in JS and Python.*

### 4. 双重存储数据层 · Dual storage (CSV + SQLite)
[`data_manager.py`](modules/data_manager.py) 每份答卷**同时**写入 SQLite（`INSERT OR REPLACE`）与 CSV（按 `response_id` upsert），用 `threading.Lock` 保证答题端自动保存并发安全，CSV 采用临时文件原子替换。读取优先 SQLite，失败回退 CSV。编号用「微秒时间戳 + 进程自增序号」保证批量生成**零碰撞**。
*Every response is written to both SQLite and CSV (thread-safe, atomic); reads prefer SQLite and fall back to CSV; IDs are collision-proof.*

### 5. 适老化答题端 · Accessibility engineering
[`survey_gui.py`](modules/survey_gui.py)：字号 24/36/48/60/72（默认 48 粗体，用命名 `tkfont` 对象热切换）；三套高对比主题（白底黑字 / 黑底白字 / 蓝底黄字）；按钮高 ≥80px、宽 ≥300px、间距 ≥20px；键盘操作（数字键选项、← → 翻页、回车确认）；**防误触**（点击去抖）；**超时提醒**（空闲自动重读）；**逐题原子自动保存** `autosave.json`，异常退出后**断点恢复**。
*Hot-swappable font sizes, 3 high-contrast themes, oversized buttons, keyboard control, click-debounce, idle re-read, and per-question atomic autosave with resume.*

### 6. 语音系统（优雅降级）· Speech with graceful degradation
[`speech_engine.py`](modules/speech_engine.py) 探测 `pyttsx3`(TTS) 与 `vosk`(离线 ASR)：可用则后台线程播报（不阻塞 UI）；**缺失则静默降级为无操作但保留回调**，答题流程不受任何影响。
*Probes TTS/ASR; speaks on a background thread when available, silently no-ops (keeping callbacks) when not.*

### 7. 统计分析核心 · Pure analytics core
[`analytics.py`](modules/analytics.py) 的 `Analyzer` 是**无界面纯函数核心**：概览（人数/完成率/平均时长/今日新增）、单题分布、数值统计（均值/中位数/总体标准差）、**交叉列联表**。所有结果均为普通 `dict`，被大屏、AI、报告**复用**，全程问卷驱动、零硬编码题目。
*A GUI-free `Analyzer` returns plain dicts (summary, distributions, mean/median/std, cross-tabs) reused by dashboard, AI and reports.*

### 8. 科交会大屏 · Big-screen dashboard
[`dashboard.py`](modules/dashboard.py)：`matplotlib` 经 `FigureCanvasTkAgg` 嵌入 tkinter，内置中文字体回退列表；科技蓝主题，6 类图（饼/柱/折线/横向排行/雷达）；5 页展厅模式用 `after()` 定时器轮播（10s）、刷新（5s）、时钟（1s）；切页时关闭旧 Figure 防内存泄漏。
*Matplotlib embedded in tkinter with CJK font fallback; `after()`-based carousel (10s) / refresh (5s) / clock (1s); figures closed on switch to avoid leaks.*

### 9. AI 分析引擎（离线 + 联网）· Hybrid AI engine
[`ai_engine.py`](modules/ai_engine.py)：
- **离线规则引擎**始终可用，从统计结果生成「调查结论 / 用户画像 / 趋势预测 / 改进建议 / 风险提示」并汇总去重出 **≥10 条洞察**。
- **联网模式**把统计 JSON 拼成 prompt，调用 OpenAI 兼容 `/chat/completions`（OpenAI / DeepSeek / Qwen / OpenRouter），鲁棒解析 LLM 返回的 JSON。
- **任何**超时 / 无 Key / 解析失败都**自动降级**到离线，绝不中断。

*An always-available offline rule engine (≥10 insights) plus an online LLM path that auto-degrades on any failure.*

### 10. 报告导出 · Report export
[`report_generator.py`](modules/report_generator.py)：Excel（4 Sheet：原始数据 / 统计结果 / 交叉分析 / AI 洞察，`openpyxl`）；PDF（封面 / 目录 / 统计图 / 分析 / AI 报告 / 建议，`reportlab` 内置中文字体 `STSong-Light`）；Word（`python-docx`）。图表先由 matplotlib 渲染为 PNG 再嵌入。
*Excel (4 sheets), PDF (CJK via STSong-Light), Word; charts rendered to PNG then embedded.*

### 11. 工程实践 · Engineering practices
面向对象 + 完整类型注解 + 中文注释 + 统一日志（滚动文件）+ 全面异常兜底 + 模块解耦。九阶段渐进开发，**每阶段自检**，累计 **114 项断言测试全部通过**。
*OOP, full type hints, logging, defensive error handling, decoupled modules; 9 phased builds with 114 passing self-check assertions.*

---

## 项目结构 · Project Structure

```
elder_ai_survey/
├── main.py                      # 统一入口 · entry (--check / --seed / direct launch)
├── config/config.json           # 全局配置 · global config (themes / AI / speech / about)
├── survey/
│   ├── questionnaire.json        # 问卷定义（唯一真相源）· questionnaire (source of truth)
│   ├── answers.csv               # 答卷 CSV · responses (CSV)
│   └── autosave.json             # 运行时断点（自动生成）· runtime checkpoint
├── database/survey.db            # 答卷 SQLite（自动生成）· responses (SQLite)
├── builder/                      # 问卷设计器（纯前端）· builder (pure frontend)
│   ├── survey_builder.html
│   ├── builder.css
│   └── builder.js
├── modules/                      # 功能模块 · feature modules
│   ├── questionnaire_engine.py   # 问卷引擎 / 逻辑跳转 · engine & branching
│   ├── validation_engine.py      # 结构校验（图论）· graph validation
│   ├── data_manager.py           # CSV+SQLite 双存储 · dual storage
│   ├── survey_gui.py             # 适老化答题端 · accessible client
│   ├── speech_engine.py          # 语音 TTS/ASR · speech
│   ├── analytics.py              # 统计与分析中心 · analytics
│   ├── dashboard.py              # 科交会大屏 · dashboard
│   ├── ai_engine.py              # AI 分析（离线+联网）· AI engine
│   └── report_generator.py       # 报告导出 · report export
├── exports/  backup/  logs/      # 导出 / 备份 / 日志 · outputs
├── requirements.txt
└── README.md
```

---

## 快速开始 · Quick Start

```bash
# 1.（可选）安装依赖；缺失的可选依赖会自动降级
#    (optional) install deps; missing optional deps auto-degrade
pip install -r requirements.txt

# 2. 环境与配置自检（无需图形界面）
#    self-check environment & config (no GUI needed)
python main.py --check

# 3.（可选）生成 200 份模拟答卷用于展示；仓库已内置一批
#    (optional) seed 200 mock responses; some are pre-loaded
python main.py --seed            # 自定义份数 · custom: python main.py --seed 500

# 4. 启动图形化主控台 · launch the GUI launcher
python main.py
```

> 📦 **开箱即用 · Ready to demo**：仓库已内置 200 份模拟答卷（`database/survey.db`），直接打开分析中心或大屏即见完整效果。
> *200 mock responses are pre-loaded — open Analytics or Dashboard to see it live.*

---

## 使用方法 · Usage

### 命令行参数 · CLI reference

| 命令 · Command | 作用 · Action |
| --- | --- |
| `python main.py` | 图形主控台（一键进入 5 大模块）· GUI launcher |
| `python main.py --check` | 自检环境、配置、问卷、依赖 · self-check |
| `python main.py --seed [N]` | 生成 N 份模拟答卷（默认 200，会先清空）· seed mock data |
| `python main.py --builder` | 浏览器打开问卷设计器 · open builder in browser |
| `python main.py --survey` | 直接进入老人答题端 · launch survey client |
| `python main.py --analytics` | 直接进入数据分析中心 · launch analytics |
| `python main.py --dashboard` | 直接进入科交会大屏 · launch dashboard |
| `python -m modules.validation_engine [file]` | 命令行校验问卷文件 · validate a questionnaire file |

### 角色化工作流 · Role-based workflows

**① 管理员：设计问卷 · Admin: design a survey**
双击 `builder/survey_builder.html`（或 `--builder`）→ 增删题、设题型与选项 → 用「逻辑跳转」可视化设置分支 → 「校验」通过后「导出 JSON」→ 用导出的文件替换 `survey/questionnaire.json`。
*Double-click the builder → edit questions → set branching visually → validate → export JSON → replace `survey/questionnaire.json`.*

**② 老人：答题 · Senior: take the survey**
`--survey` 进入全屏答题端 → 右上角可调字体大小 / 切换配色 / 开关语音 → 逐题作答（支持鼠标、键盘、语音）→ 提交。中途异常退出，下次自动询问**断点续答**。
*Full-screen client with adjustable fonts/contrast/voice; mouse, keyboard or voice input; auto-resume after an unexpected exit.*

**③ 管理员：分析数据 · Admin: analyze**
`--analytics` → 查看/搜索/筛选/删除答卷 → 「单题统计」看分布与均值 → 「交叉分析」做列联表（如年龄 × 是否使用智能手机）→ 「导出 Excel」。
*View/search/filter/delete; per-question stats; cross-tabs; export to Excel.*

**④ 展示：科交会大屏 · Showcase: dashboard**
`--dashboard` → 全屏自动轮播总览 / 图表 / 趋势 / AI 洞察 / 报告页。快捷键：`空格` 暂停、`← →` 翻页、`Esc` 退出。
*Full-screen auto carousel; `Space` pause, `← →` navigate, `Esc` exit.*

**⑤ AI 报告 · AI report**
主控台「AI 分析报告」→ 「生成 AI 报告预览」看结论与洞察 → 「导出 Excel / PDF / Word」。
*Generate an AI report preview, then export to Excel / PDF / Word.*

---

## 配置说明 · Configuration

编辑 [`config/config.json`](config/config.json)（节选 · excerpt）：

```jsonc
{
  "accessibility": {                  // 适老化 · accessibility
    "default_font_size": 48,          // 默认字号 · default font (px)
    "default_theme": "white_black",   // white_black | black_white | blue_yellow
    "timeout_seconds": 60             // 超时重读 · idle re-read
  },
  "ai": {                             // AI 引擎 · AI engine
    "mode": "auto",                   // auto | online | offline
    "active_provider": "deepseek",
    "fallback_to_offline": true,      // 联网失败自动降级 · auto-degrade
    "providers": {
      "deepseek": { "enabled": false, "api_key": "", "model": "deepseek-chat" }
      // openai / qwen / openrouter 同构 · same shape
    }
  },
  "dashboard": {                      // 大屏 · dashboard
    "refresh_interval_seconds": 5,
    "carousel_interval_seconds": 10
  },
  "about": {                          // 署名 · attribution (shown in GUI)
    "author": "Jiacheng Zheng",
    "contact_url": "https://karcen.github.io/zhengjiacheng.github.io/"
  }
}
```

启用联网 AI：把对应 provider 的 `enabled` 设为 `true`、填入 `api_key`，并将 `ai.active_provider` 指向它即可。
*To enable online AI: set the provider's `enabled: true`, fill its `api_key`, and point `ai.active_provider` to it.*

---

## 离线 / 联网与降级 · Offline / Online & Degradation

| 能力 · Capability | 联网增强 · Online | 离线回退 · Offline fallback |
| --- | --- | --- |
| AI 分析 · AI analysis | LLM 生成报告 · LLM report | 规则引擎（始终可用）· rule engine (always on) |
| 语音播报 · TTS | — | `pyttsx3`；缺失则静默 · silent if missing |
| 语音识别 · ASR | Whisper（预留接口）· reserved | `vosk` 离线模型 · offline model |
| PDF 导出 · PDF | — | `reportlab` 内置中文字体 · built-in CJK |

设计原则：**默认全离线可用**，联网仅作增强；任何联网失败都自动回退，核心永不中断。
*Design principle: fully usable offline by default; networking is purely additive and any failure auto-falls-back.*

---

## 测试与质量 · Testing & Quality

九阶段每阶段自检，累计 **114 项断言全部通过**；覆盖：逻辑求值、图论校验、双存储一致性、答题流程（含逻辑跳转/断点恢复）、统计正确性、大屏渲染、AI 离线/降级、Excel/PDF/Word 实际产出，及全链路端到端集成。
*Each of the 9 phases is self-checked — 114 assertions in total, covering branching, graph validation, storage consistency, the answering flow, statistics, dashboard rendering, AI offline/degradation, real Excel/PDF/Word output, and end-to-end integration.*

```bash
python main.py --check                         # 环境/依赖自检 · environment self-check
python -m modules.validation_engine            # 校验内置问卷 · validate the bundled survey
```

---

## 常见问题 · FAQ

- **语音不发声 · No voice?** 未安装 `pyttsx3`（已自动静默降级）。安装：`pip install pyttsx3`。
  *`pyttsx3` not installed (auto-degraded). Install it to enable TTS.*
- **图表中文乱码 · Garbled CJK in charts?** 系统缺中文字体。安装任一：思源黑体 / 文泉驿 / 微软雅黑等；程序已内置字体回退列表。
  *Install a CJK font (Source Han Sans / WenQuanYi / etc.); a font-fallback list is built in.*
- **无图形界面环境 · Headless server?** 用 `--check` / `--seed` / `validation_engine` 等命令行能力；GUI 模块需要桌面环境。
  *Use the CLI features; GUI modules need a desktop session.*
- **换一套问卷 · Use a different survey?** 用设计器生成并替换 `survey/questionnaire.json`，全系统自动适配。
  *Generate via the builder and replace the JSON — the whole system adapts automatically.*

---

## 作者 · Author

**Jiacheng Zheng** · 使用 Claude Code 辅助开发 · built with the help of Claude Code

🔗 联系我 · Contact: <https://karcen.github.io/zhengjiacheng.github.io/>

## License

仅供适老化调研、科交会展示与教学研究使用。
*For elderly-care research, science-fair demonstration and educational use.*
