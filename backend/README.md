# Backend service (FastAPI)

把离线管道产出的数据集（41 个案例、3 种归因方案、10 条人工标签、1 份安装级验证）
做成一个**有 schema、有接口、有异步任务、可容器化部署**的后端服务。

> 这个目录只 **读取** `requirements_all/`、`error_all/`、`reports_*_all/`、
> `golden_labels.json`、`recovered/`，除显式触发任务外不会修改它们。
> 原来的离线脚本保持原样，两条入口并存。

## 架构

```
             ┌──────────────────────────────┐
  HTTP  ───► │  FastAPI (backend/main.py)    │
             │   routers/: cases labels      │
             │            stats  jobs        │
             └───────┬──────────────┬────────┘
                     │              │
             SQLAlchemy 2.0    ThreadPoolExecutor
                     │              │
             ┌───────▼──────┐  ┌────▼──────────────┐
             │ SQLite 6 表   │  │ job worker         │
             │ cases/runs/…  │  │ rule → 规则分析器   │
             └───────▲──────┘  │ pip  → batch_runner│
                     │         └────────────────────┘
                     │
             ingest.py（唯一知道 JSON 文件形状的模块）
                     │
        requirements_all / error_all / reports_*_all
        golden_labels.json / recovered/
```

## 数据模型（6 张表）

| 表 | 主键 | 说明 |
|---|---|---|
| `cases` | `id` (`000`) | 一个 requirements 文件及其来源信息（repo / commit / sha256） |
| `pip_runs` | `id` | 产生错误日志的那次 pip 执行（模式、返回码、耗时） |
| `attribution_reports` | `id` + `(case_id, approach)` 唯一 | 三条轨道各一行：`rule` / `llm` / `agent` |
| `labels` | `case_id` | 人工标注（含 `acceptable` 可接受答案列表） |
| `verifications` | `case_id` | 修复的真实安装验证结果 |
| `jobs` | `id` | API 触发的重跑任务，供轮询 |

`attribution_reports` 与 `labels` 是一对多的对比关系：三个方案对同一个
`case_id` 各有一行，统计接口按 `(case_id, approach)` 做 join。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 服务索引 |
| GET | `/healthz` | 存活检查 + 行数 |
| GET | `/api/cases` | 列表，支持 `failure_type` / `priority` / `reviewed` / 分页 |
| GET | `/api/cases/{id}` | 详情：requirements、日志尾部、三条归因、标签、验证 |
| GET | `/api/cases/{id}/log` | 原始 pip 日志（文本，可截断） |
| GET | `/api/cases/{id}/patch` | 已验证的修复 diff |
| POST | `/api/cases/{id}/jobs` | 排队重跑，`kind` = `rule` 或 `pip`，返回 202 |
| GET | `/api/jobs` | 任务列表 |
| GET | `/api/jobs/{id}` | 任务状态与结果 |
| GET | `/api/labels` | 全部标签 |
| GET | `/api/labels/{id}` | 单个标签 |
| PUT | `/api/labels/{id}` | 新增/更新标签 |
| GET | `/api/stats` | 三方准确率、平均置信度、token、工具调用、修复数 |

交互式文档：`/docs`（Swagger UI）与 `/redoc`。

## 本地运行

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt

python -m backend.seed                 # 把产物灌进 SQLite（可重复执行）
uvicorn backend.main:app --reload --port 8000
```

打开 <http://127.0.0.1:8000/docs>。

首次启动时如果库是空的，会自动执行一次 ingest（`PIPATTR_AUTOSEED=0` 可关闭）。

## Docker

```powershell
docker compose up --build
# http://127.0.0.1:8000/docs
```

## 测试

```powershell
pip install -r backend/requirements-dev.txt
pytest backend/tests -q
```

测试使用临时 SQLite 文件（`conftest.py` 在导入前设置 `PIPATTR_DB`），
不会污染 `backend/data/pipattr.db`。

## 配置

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `PIPATTR_DATA_DIR` | 仓库根目录 | 数据集根目录 |
| `PIPATTR_DB` | `<data>/backend/data/pipattr.db` | SQLite 路径 |
| `PIPATTR_AUTOSEED` | `1` | 空库时自动灌数据 |

## 设计取舍

- **SQLite**：单进程演示足够；换成 Postgres 只需改 `backend/db.py` 一处。
- **线程池而非 Celery**：不引入 broker，任务状态仍然持久化在 `jobs` 表里，可换成
  RQ/Celery 而不改接口。
- **ingest 幂等**：以 `(case_id)` / `(case_id, approach)` 为键 upsert，重跑安全。
- **`generated_at` 存字符串**：上游时间戳原样保留，避免时区转换引入歧义。
- **已知边界**：没有鉴权（内网/演示用）；一个案例同一时刻只应该跑一个 `pip` 任务；
  日志里中文路径可能仍是乱码（上游 pip 输出编码问题，与本服务无关）。

## 简历写法（可直接用）

> **Python 依赖安装失败归因系统（后端）** ｜ 个人项目 ｜ FastAPI + SQLAlchemy + SQLite + Docker
> - 将离线数据管道升级为 REST 服务：设计 **6 张表**（案例 / pip 运行 / 三方归因报告 / 标签 / 修复验证 / 任务）的数据模型，
>   `(case_id, approach)` 唯一约束保证三种归因方案对同一案例各存一行。
> - 实现 **13 个接口**，覆盖列表筛选（按失败类型 / 优先级 / 复核状态，JSON 列与关系表混合查询）、
>   详情聚合、原始日志与 diff 下载、标签写入、统计聚合；OpenAPI 文档自动生成于 `/docs`。
> - 用 `ThreadPoolExecutor` + `jobs` 表实现异步重跑：`POST /api/cases/{id}/jobs` 立即返回 **202**，
>   客户端轮询任务状态，避免长任务阻塞请求线程。
> - 数据接入层幂等：以主键 upsert，41 个案例 / 61 份报告 / 10 条标签可重复导入不产生重复行。
> - 容器化：`Dockerfile` + `docker-compose`，SQLite 数据卷持久化，`/healthz` 暴露行数用于存活探测。
