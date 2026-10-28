# Python 依赖安装失败归因与自动修复系统

从 GitHub 采集真实 `requirements` 文件 → 在受控环境执行 pip 并捕获原始报错 →
用**规则基线 / 单步 LLM / 工具调用 Agent** 三条轨道做失败归因 →
对 Agent 提出的修复做**真实安装级验证** → 通过 FastAPI 对外提供数据与任务接口。

> 这不是一个"网页"，而是一条可复现的评测管道 + 一个服务层。
> 接口细节见 [`backend/README.md`](backend/README.md)，结项说明见 [`CONCLUSION.md`](CONCLUSION.md)。

## 它解决什么问题

`pip install -r requirements.txt` 失败时，报错信息往往同时包含版本冲突、Python 版本不匹配、
平台无 wheel、网络超时等多种信号，人工判断成本高。本项目把这个问题变成可量化任务：
**给定 requirements + pip 原始日志，判断失败类型和根因，并给出可验证的修复。**

## 架构

```
GitHub ──► collect_requirements.py ──► requirements_sources.json (91 条来源)
                                              │
                                              ▼
                     download_requirements.py（锁 commit SHA + sha256，改写 -r/-c，注释 -e）
                                              │
                                              ▼
                     requirements_all/ (41) ──► batch_runner.py（pip --dry-run）
                                              │
                                              ▼
                                    error_all/ (41 份原始日志)
                                              │
              ┌───────────────────────────────┼───────────────────────────────┐
              ▼                               ▼                               ▼
      failure_analyzer.py            llm_analyzer.py                 agent_analyzer.py
      （正则规则基线）              （单步 LLM，JSON 输出）        （5 工具自主循环 + trace）
              │                               │                               │
      reports_all/ (41)            reports_llm_all/ (10)           reports_agent_all/ (10)
              └───────────────────────────────┼───────────────────────────────┘
                                              ▼
                        golden_labels.json (10 条人工标签) ──► evaluate.py
                                              │
                                              ▼
                                verify_fix.py（真实安装 + pip check + import）
                                              │
                                              ▼
                            backend/：FastAPI + SQLAlchemy + SQLite（6 表 / 13 接口）
```

## 数据规模

| 项目 | 数量 |
|---|---|
| 来源索引 | 91 条（GitHub 仓库 + 文件路径） |
| 已下载案例 | 41 个（40 个 GitHub 来源 + 1 个手写基线） |
| 伴生文件（`-r` / `-c`） | 6 个案例共 11 个文件 |
| pip 执行日志 | 41 份（全部 `--dry-run`） |
| 规则归因报告 | 41 份 |
| 单步 LLM 报告 | 10 份（000–009） |
| Agent 报告 | 10 份（000–009） |
| 人工标签 | 10 条（000–009） |
| 真实安装级验证 | 1 条（case 000） |

所有下载都锁定 commit SHA 并按 SHA 记录 `raw_url` 与 `sha256`，默认分支变化后仍可复现。

## 三方对比（评测集 10 条）

| 方案 | 严格准确率 | 宽松准确率 | 平均置信度 | tokens | 工具调用 | 声称已修复 |
|---|---|---|---|---|---|---|
| 规则基线 | 8/10 | 9/10 | 0.868 | 0 | 0 | 0 |
| 单步 LLM | 10/10 | 10/10 | 0.944 | 59,189 | 0 | 0 |
| 工具调用 Agent | 10/10 | 10/10 | 0.961 | 169,347 | 19 | 3 |

**结论**：在这 10 条样本上，两条 LLM 轨道的准确率没有差异；Agent 的代价是约 2.9 倍 tokens，
收益是能产出可被验证的修复（3 条，其中 1 条通过真实安装验证）。
样本量不足以推断泛化能力，这里只证明了链路可行。

## 后端服务

`backend/` 把上述产物变成 REST 服务：6 张表（案例 / pip 运行 / 三方归因报告 / 标签 /
修复验证 / 任务）、13 个接口、异步重跑任务、OpenAPI 文档。

```powershell
pip install -r backend/requirements.txt
python -m backend.seed                 # 期望 {"cases": 41, "runs": 41, "reports": 61, ...}
uvicorn backend.main:app --port 8000   # http://127.0.0.1:8000/docs
pytest backend/tests -q                # 9 passed
```

## 目录结构

```
collect_requirements.py     来源发现与索引
download_requirements.py    按 SHA 下载 + 伴生文件处理
batch_runner.py             批量执行 pip，产出 error_all/
failure_analyzer.py         规则基线
llm_analyzer.py             单步 LLM 归因
agent_analyzer.py           工具调用 Agent
agent_tools.py              Agent 工具箱（read/analyze/write/run_install/pypi_metadata）
evaluate.py                 三方对比（严格 + 宽松）
verify_fix.py               真实安装级验证
review_case.py / label_case.py  人工复核与打标
repair_manifest.py          manifest 补录

requirements_all/  error_all/  reports_all/  reports_llm_all/  reports_agent_all/
agent_traces/  recovered/  evaluation/  prompts/  backend/
```

## 已知局限

- **标签**：10 条，AI 辅助生成后人工复核；`golden_labels.json` 中 `needs_human_review` 仍为 `true`。
- **样本区分度**：10 条里 6 条是 `no_failure`，真正的失败只有 4 条，准确率数字的说服力有限。
- **修复验证口径不一致**：只有 case 000 做了真实安装验证（pip check + import 通过）。
  case 008 的 `fix_verified` 来自 dry-run 解析通过；case 009 两次执行都在 120s 内超时，
  该标记来自模型自述，**不应视为已验证修复**。
- **超时案例未纳入标签**：016 / 021 / 033 三条超时（`timeout` 类型不在标签类型枚举里）。
- **dry-run 并非无副作用**：pip 在解析阶段仍会下载元数据、构建 sdist，因此数据集里混有
  `build_failure` 与 `timeout`。
- **容器化**：`Dockerfile` 与 `docker-compose.yml` 已就绪，但未在有 Docker 的机器上实际构建验证。

## License

仓库暂未声明 License（建议补 MIT）。
