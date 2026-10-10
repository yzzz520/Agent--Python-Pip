# Agent 工具调用失败归因与自动恢复系统 - 结项总结

## 1. 项目目标

构建一条可复现的离线评测管道，用于研究 Python 依赖安装失败的归因与自动恢复：

- 从 GitHub 采集真实 `requirements` 来源。
- 在受控环境里执行安装、捕获原始报错。
- 对比规则基线、单步 LLM、工具调用 Agent 三种归因方案。
- 让 Agent 真正执行修复（改写 requirements）并重新安装验证。

## 2. 数据规模与可复现性

| 项目 | 数量 |
|------|------|
| 来源索引 `requirements_sources.json` | 91 条 |
| 已下载案例（`requirements_000` ~ `040`） | 41 个（40 个 GitHub 来源 + 1 个手写基线） |
| `manifest.json` 已登记来源 | 40 条，全部带 commit SHA、sha256 |
| 伴随文件（`-r` / `-c`） | 6 个案例共 11 个文件 |
| 执行日志 `error_all` | 41 份 |
| 规则报告 `reports_all` | 41 份 + summary |

所有下载都锁定 commit SHA，并按 SHA 保存 `raw_url` 和 `sha256`，默认分支变化后仍可复现。伴随文件按案例存放在 `requirements_all/support/case_XXX/`，主文件中的 `-r` / `-c` 引用已改写为本地路径；`-e .` 这类仓库自引用会注释掉并记录在 manifest。

## 3. 三条归因轨道

| 轨道 | 脚本 | 输出目录 | 说明 |
|------|------|----------|------|
| 规则基线 | `failure_analyzer.py` | `reports_all/` | 确定性正则规则，覆盖 9 类失败 |
| 单步 LLM | `llm_analyzer.py` | `reports_llm_all/` | 报错日志 + requirements 一次性交给模型，输出同构 JSON |
| 工具调用 Agent | `agent_analyzer.py` | `reports_agent_all/` + `agent_traces/` | 自主调用读日志、规则分析、PyPI 查询、改写依赖、重跑 pip |

Agent 工具箱在 `agent_tools.py`：

```text
read_case / analyze_failure / write_requirements
/ run_install / pypi_metadata
```

Agent 可以自主决定调用顺序，并在提出修复后重新执行 `run_install` 验证修复是否通过。

## 4. 三方评测结果

评测集为 000 ~ 008 共 9 条，标签见 `golden_labels.json`（AI 辅助标注，仍需人工复核）。结果见 `evaluation/comparison.md`。

| 方案 | 严格准确率 | 平均置信度 | tokens | 验证修复数 | 工具调用 |
|------|------------|------------|--------|------------|----------|
| 规则 | 8/9 (0.8889) | 0.9311 | 0 | 0 | 0 |
| 单步 LLM | 9/9 (1.0) | 0.9489 | 53,631 | 0 | 0 |
| Agent | 9/9 (1.0) | 0.9678 | 140,668 | 2 | 16 |

唯一分歧是案例 005：规则判 `python_version_mismatch`，LLM 和 Agent 判 `no_matching_distribution`，并进一步定位到 `nvidia-nccl-cu13==2.30.7` 在当前平台无可用分发。该案例在标签中标记为“有两种可接受答案”。

Agent 在案例 008 上自主完成了一次修复验证：sphinx==9.0.4 不可用，先尝试 8.1.3 触发 docutils 冲突，最终改为 `sphinx==8.1.3 + docutils==0.21.2`，pip dry-run 返回 0。

## 5. 自动恢复验证：案例 000

Agent 提出的修复：

```diff
-numpy==2.1.0
+numpy==1.26.4
```

真实安装验证（`verify_fix.py`）：

- 隔离 venv：`.runner_venvs/verify_case_000`
- 真实 `pip install`：returncode 0，耗时 389.16 秒
- `pip check`：returncode 0，`No broken requirements found.`
- import 冒烟测试：`numpy`、`langchain_chroma`、`langchain_pinecone` 全部通过
- 最终 `recovered = true`

产物：

- `recovered/case_000.patch`
- `recovered/requirements_000.fixed.txt`
- `recovered/case_000.install.log`
- `recovered/case_000.verification.json`

这构成了完整的自动恢复闭环：

```text
诊断失败 → 生成修复 → 改写依赖 → 重新解析 → 真实安装 → pip check → 冒烟测试 → recovered=true
```

## 6. 已知局限

- 评测标签是 AI 辅助标注，引用准确率前需要人工复核。
- 评测集只有 9 条，且 28/41 条原始案例本来就是 `no_failure`，区分度有限。
- 仍有 3 条案例（016、021、033）在 180 秒内无法完成解析，需要更长超时或拆分依赖。
- Agent 成本较高：单条约 1.5 万 tokens，是单步 LLM 的 2 到 3 倍。
- 目前只有案例 000 完成了真实安装级验证，其余案例停留在解析级验证。

## 7. 复现命令

```powershell
# 1. 生成/更新来源索引
python collect_requirements.py --seed-only
python collect_requirements.py --discover --render-md

# 2. 下载 requirements（按 commit SHA）
python download_requirements.py --priority P0,P1

# 3. 执行并捕获报错
python batch_runner.py --jobs 5 --timeout 120

# 4. 规则归因
python failure_analyzer.py

# 5. 单步 LLM 归因
python llm_analyzer.py

# 6. Agent 归因
python agent_analyzer.py --preload --max-steps 6

# 7. 真实安装验证
python verify_fix.py --case 000

# 8. 三方评测
python evaluate.py
```

## 8. 结论

项目已经从“依赖数据管道”升级为具备工具调用与修复验证能力的 Agent 系统：

- 数据可溯源、可复现。
- 有规则基线和 LLM 对照组。
- Agent 能自主决定工具调用顺序。
- 至少一条案例完成了真实安装级自动恢复。

后续最有价值的投入是人工复核标签并扩大失败样本，把评测集从 9 条扩展到 20 到 30 条，再补充真实安装级验证覆盖率。
