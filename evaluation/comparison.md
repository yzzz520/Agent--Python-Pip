# 规则 / LLM / Agent 三方对比

- 生成时间：`2026-10-28T14:22:27.573892+00:00`
- 标签来源：`human-reviewed`，需要人工复核：`True`

## 逐案例结果

| 案例 | Golden | Rule | LLM | Agent | Agent 验证修复 |
|------|--------|------|-----|-------|----------------|
| 000 | dependency_conflict | dependency_conflict (OK) | dependency_conflict (OK) | dependency_conflict (OK) | True |
| 001 | no_failure | no_failure (OK) | no_failure (OK) | no_failure (OK) | False |
| 002 | no_failure | no_failure (OK) | no_failure (OK) | no_failure (OK) | False |
| 003 | no_failure | no_failure (OK) | no_failure (OK) | no_failure (OK) | False |
| 004 | no_failure | no_failure (OK) | no_failure (OK) | no_failure (OK) | False |
| 005 | no_matching_distribution | python_version_mismatch (OK) | no_matching_distribution (OK) | no_matching_distribution (OK) | False |
| 006 | no_failure | no_failure (OK) | no_failure (OK) | no_failure (OK) | False |
| 007 | no_failure | no_failure (OK) | no_failure (OK) | no_failure (OK) | False |
| 008 | python_version_mismatch | python_version_mismatch (OK) | python_version_mismatch (OK) | python_version_mismatch (OK) | True |
| 009 | invalid_local_reference | unknown (X) | invalid_local_reference (OK) | invalid_local_reference (OK) | True |

## 汇总

| 方案 | 已评测 | 正确 | 严格准确率 | 平均置信度 | tokens | 验证修复数 | 工具调用 |
|------|--------|------|------------|------------|--------|------------|----------|
| rule | 10 | 8/10 | 0.8 | 0.868 | 0 | 0 | 0 |
| llm | 10 | 10/10 | 1.0 | 0.944 | 59189 | 0 | 0 |
| agent | 10 | 10/10 | 1.0 | 0.961 | 169347 | 3 | 19 |
