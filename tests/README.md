# 随访子系统 · 测试数据与流水线自测

用一份模拟数据把整条随访链路跑通，方便验证功能是否正常。

## 一键跑通（命令行 / headless）

```bash
python tests/run_pipeline.py
```

会依次执行并打印每步结果：

1. **CSV → JSON**：`tests/data/students.csv`、`subjects.csv` → `tests/out/*.json`
   （`subjects.csv` 故意用中文表头 `受试者id,姓名,电话,备注`，验证列名容错）
2. **平均分配**：8 名学生 × 40 名受试者 → 每人 5 个 → `tests/out/allocation.json`
3. **生成查询页**：`tests/out/query.html`（内联数据 + 短信按姓名替换）
4. **完成情况统计**：对照学生名单与 `sample_thread.txt`，应得未完成 = 杨光、孙磊

任一步异常都会以非 0 退出码失败。产物只写入 `tests/out/`，不影响 `followup/` 正式文件。

## 在浏览器里手动验证（图形界面）

```bash
# 1) 分配系统：打开后上传下面两份 CSV，点「平均分配」，再随意微调看顶部「未分配 X 人」
open followup/allocation.html
#    上传：tests/data/students.csv  +  tests/data/subjects.csv
#    点「导出 allocation.json」

# 2) 学生查询页：直接看自测生成的成品（输入学生姓名，如「张伟」）
open tests/out/query.html

# 3) 完成情况统计：粘贴接龙文本，点「分析未完成」
open followup/completion.html
#    名单粘贴 tests/data/students.csv（或每行一个姓名）
#    接龙文本粘贴 tests/data/sample_thread.txt  → 未完成应为 杨光、孙磊
```

也可以从主控台走完整 GUI 流程：`python main.py` →「回访管理」→ 按 ①~⑥，
上传时选 `tests/data/` 里的 CSV 即可。

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `data/students.csv` | 8 名学生（标准英文表头 + email） |
| `data/subjects.csv` | 40 名受试者（**中文表头**，含备注，测列名容错） |
| `data/sms_template.txt` | 统一短信模板（含 `{姓名}` 占位） |
| `data/sample_thread.txt` | 群接龙示例文本（6 人已报备） |
| `run_pipeline.py` | 端到端自测脚本 |
| `out/` | 运行产物（可随时删除重跑） |
