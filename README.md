# ElderAI Survey Platform · 适老化智能问卷与 AI 数据分析平台

## 项目简介
面向**老年人**、可**离线运行 / 联网增强 / 本地部署**的一体化智能问卷系统，覆盖「问卷设计 → 适老化答题 → 数据分析 → 大屏展示 → AI 报告」的完整闭环。

A bilingual, **offline-first / online-enhanced / locally-deployable** survey platform built for **senior citizens**, covering the full loop: *design → accessible answering → analytics → big-screen showcase → AI reporting*.

---

## 核心功能模块

| 模块 | 说明 | 英文 |
| --- | --- | --- |
| 📝 问卷设计器 | 可视化增删题、拖拽排序、逻辑跳转、自动校验、模拟预览 | Survey Builder |
| 🧓 老人答题端 | 超大字体、高对比、语音播报、自动保存与断点恢复 | Senior Client |
| 📊 数据分析中心 | 查看/筛选/搜索/删除/导出，自动统计与交叉分析 | Analytics |
| 📺 科交会大屏 | 全屏科技蓝驾驶舱，自动轮播 + 实时刷新 | Dashboard |
| 🤖 AI 分析报告 | 离线规则 + 联网 LLM，自动生成洞察与报告 | AI Report |
| 📞 随访管理 | 把受试者分配给学生、学生查询任务、一键电话/短信、完成情况统计 | Follow-up Management |

---

## 更新日志 · What's New

### v1.2.0 (2026-06-13) · 随访子系统重建 · Follow-up Subsystem Rebuilt

> 把整套随访（回访）功能重建为**统一、简约、纯前端、可离线**的子系统，全部位于 `followup/`，从主控台「回访管理」一键贯通：**导入名单 → 分配 → 学生查询 → 完成统计**。
>
> A complete rebuild of the follow-up workflow into one **clean, minimalist, pure-frontend, offline-capable** subsystem under `followup/`, driven end-to-end from the launcher: **import rosters → allocate → student lookup → completion stats**.

#### ✨ 亮点 | Highlights
1. **随访分配系统 · Allocation** — `followup/allocation.html`
   - 浏览器内上传学生 / 受试者 CSV（或 JSON），中英文表头自动容错
   - 一键「平均分配」（轮询均分），再逐人下拉**微调**
   - 顶部实时显示 **「未分配 X 人」**（>0 高亮）＋每位学生当前分配数＋已分配/总数
   - 导出 `allocation.json` / CSV
2. **学生查询页 · Student Lookup** — `followup/query.html`（由 `generate_query.py` 生成）
   - 学生**输入姓名**即看到分配给自己的受试者
   - **一键打电话**（`tel:`）、**一键发短信**（`sms:`，正文已按姓名填好）
   - 短信＝**统一模板＋`{姓名}`占位**，每次由 Python 生成时填写、自动替换
3. **完成情况统计 · Completion Stats** — `followup/completion.html`
   - 粘贴群接龙 / 聊天文本，自动找出**谁还没发**
   - **双模式**：对照「学生名单」或「受试者名单」
   - 输出总人数 / 已完成 / 未完成，并可导出未完成名单
4. **CSV → JSON 转换 · Converter** — `followup/csv_to_json.py`（学生 / 受试者通用，列名容错）
5. **GUI 面板 · One-stop Panel** — `followup/followup_panel.py`，主控台「回访管理」启动

#### 🎨 主题与风格 | Theme
- 全部页面**简约风格**、亮 / 暗双主题，默认浅色，右上角一键切换并记忆（`localStorage`）
- 零 CDN 依赖，可直接 `file://` 离线打开；共享主题 `followup/assets/theme.css`

#### 🧭 目录速览 | File Map
```
followup/
├─ allocation.html      ① 分配系统
├─ query.html           ② 学生查询页（generate_query.py 生成）
├─ completion.html      ③ 完成情况统计
├─ csv_to_json.py       CSV → JSON
├─ generate_query.py    生成查询页
├─ followup_panel.py    GUI 面板（被 main.py 调用）
├─ assets/theme.css     共享主题（亮/暗·简约）
└─ data/                students/subjects/allocation/sms_template
```

#### 🚀 快速上手 | Quick Start
```bash
python main.py          # 主控台 →「回访管理」→ 按 ①~⑥ 操作
```

#### 🧹 升级与清理 | Migration & Cleanup
- 移除旧的半成品 mock 文件（英文假数据、互不衔接，且主控台按钮曾引用**不存在的文件名**导致点击报错）：
  `follow-up-allocation.html`、`follow-up-query.html`、`generate_query_html.py`、`generate_elder_survey_html.py`、根目录 `csv_to_json.py`、`experimenters.csv/json`、`test_subjects.json`
- 新功能与旧文件无依赖关系，核心问卷平台（设计器 / 答题端 / 分析 / 大屏 / AI 报告）不受影响。

---

> 📌 以下为历史版本记录；其中提到的中文文件名已在 **v1.2.0** 统一重构/移除，请以上方 v1.2.0 为准。
> Historical entries below; the Chinese filenames they mention were consolidated/removed in **v1.2.0**.

### v1.1.1 (2026-06-10)

#### 新增功能 | New Features
1. **回访人员自动分配系统**
   - 纯前端网页 `回访分配Demo.html`（已优化，移除Demo标识）
   - 支持设置总人数和调查员数量，自动计算分配数量
   - 将"未分配：0 | 总分配：100 / 100"调整到分配人员卡片上方，直观查看
   - 支持手动调整每个调查员的分配数量，灵活适配需求

2. **回访查询系统（纯前端，无需服务器） · Follow-up Query System**
   - `回访查询.html`：支持上传CSV格式回访名单
   - 输入姓名即可查询该人员详细信息
   - 提供"一键发短信"和"一键打电话"快捷操作
   - 支持亮色/暗色主题切换，现代化渐变页脚，美观实用
   - 支持群发短信（默认隐藏，可手动展开）
   - Pure frontend HTML, no server required
   - Supports CSV list upload, theme switching, one-click SMS/call operations

3. **群接龙未完成查询 · Group Task Check**
   - `群接龙未完成查询.html`：自动识别群接龙中的未完成任务人员
   - 统计总人数、已完成数、未完成数
   - 区分显示完成和未完成人员，一目了然
   - 现代化渐变页脚，适配整体风格
   - Automatically identify incomplete personnel in group follow-up responses
   - Statistics on total number, completed count, and incomplete count

#### 功能优化 | Optimizations
- **页脚统一美化**：所有HTML文件都已重新设计页脚，采用渐变背景+现代化布局，支持响应式设计，适配不同屏幕
- **模拟数据更新**：`回访名单.csv`替换为完整模拟数据示例，姓名和电话随机生成，适配实际使用场景，与python文件完美衔接
- **主题与配色**：所有网页都支持亮色/暗色主题切换，淡色简约配色，大气低调，适合老人使用和团队协作
- **移动端适配**：所有新增网页都做了响应式设计，支持手机访问和操作
- **数据导入**：回访名单支持CSV格式导入，适配Excel和其他表格工具生成的名单

---

### v1.1.0 (2026-06-7)

#### 新增功能 | New Features
1. **回访管理模块 · Follow-up Management**
   - Python脚本 `生成回访名单.py`：根据问卷已完成数据自动生成回访名单
   - 名单包含：姓名、电话（需手动补充）、回访状态、是否需要短信、分配回访人员
   - 支持随机分配回访人员，适配团队协作需求
   - Follow-up list includes: Name, Phone (needs manual fill-in), Follow-up Status, Need SMS, Assigned Follow-up Person
   - Supports random assignment of follow-up personnel for team collaboration

#### 功能优化 | Optimizations
- **主题切换**：启动器和所有网页都支持亮色/暗色主题切换
- 支持批量短信发送（默认隐藏，可按需显示）

---

### v1.0.0 (2026-06-03)
- 初始版本：问卷设计器、答题端、数据分析、大屏展示、AI分析报告等核心功能
- Initial version: Core functions including survey builder, client, analytics, dashboard, AI report, etc.

---

## 使用教程 · Tutorial

### 完整随访管理流程
全部从主控台 `python main.py` →「回访管理」面板按 ①~⑥ 顺序操作即可；各文件位于 `followup/`。

#### 1. 准备名单（CSV → JSON）
- **①上传学生名单 CSV**：列 `student_name, phone`（兼容 `姓名/电话` 等中英文表头），自动转为 `followup/data/students.json`。
- **②上传受试者名单 CSV**：列 `subject_name, phone, note`（备注可选），自动转为 `followup/data/subjects.json`。
- 受试者来自**已完成问卷的老人名单**。也可单独运行：
  ```bash
  python followup/csv_to_json.py 输入.csv 输出.json --kind subjects
  ```

#### 2. 分配（③ 打开分配系统 `allocation.html`）
1. 上传学生、受试者两份名单（或点「载入示例数据」试用）
2. 点 **「平均分配」** 轮询均分
3. 在表格里用下拉框逐人**微调**指派；选「不分配」则该人计入顶部 **「未分配 X 人」** 提示
4. 点 **「导出 allocation.json」** 下载分配结果

#### 3. 生成学生查询页（④ 导入分配结果 → ⑤ 填短信并生成）
1. **④导入分配结果**：选择上一步下载的 `allocation.json`
2. **⑤填短信·生成查询页**：在弹窗里填写统一短信模板（用 `{姓名}` 占位），点「生成并打开」
3. 自动生成 `followup/query.html` 并打开 —— 学生**输入自己的姓名**即可看到分配给自己的受试者，**一键打电话 / 发短信**（短信正文已按姓名填好）
4. 需要更换短信内容时，重复 ⑤ 即可重新生成

#### 4. 完成情况统计（⑥ 打开 `completion.html`）
1. 选择对照 **学生名单** 或 **受试者名单**（粘贴每行一名，或上传 CSV/JSON）
2. 把群接龙 / 聊天文本粘进「接龙文本」框（兼容 `1. 张三 ✅ 完成` 等格式）
3. 点 **「分析未完成」**：统计总人数 / 已完成 / 未完成，并可复制或导出**未完成名单**

---

## 使用方式 · Usage

### 启动图形化主控台 · Launch GUI Launcher
```bash
python main.py
```

### 其他命令 · Other Commands
```bash
python main.py --check       # 自检模式 · Self-check mode
python main.py --builder     # 直接打开问卷设计器 · Open survey builder
python main.py --survey      # 直接进入老人答题端 · Launch senior client
python main.py --analytics  # 直接进入数据分析中心 · Launch analytics
python main.py --dashboard  # 直接进入科交会大屏 · Launch dashboard
python main.py --seed [N]    # 生成N份模拟答卷 · Generate N mock responses
```

---

## 技术栈 · Tech Stack
- 运行环境：Python 3.9+
- 界面：tkinter（标准库，零额外依赖）
- 数据处理：pandas, numpy, sqlite3
- 图表：matplotlib
- 导出：openpyxl, reportlab, python-docx
- 语音：pyttsx3, vosk
- 前端：原生HTML/CSS/JavaScript（无框架）

---

## 许可证 · License
仅供适老化调研、科交会展示与教学研究使用。
For elderly-care research, science-fair demonstration and educational use.
