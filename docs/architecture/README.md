# 当前架构与模块职责

系统采用 FastAPI + SQLAlchemy 模块化单体后端和 React + TypeScript 前端。浏览器提取工具和离线质量评估工具是辅助入口。评分与报告用于学生自测和教学实验，属于辅助性结果。

## 目录职责

| 目录 | 职责 |
| --- | --- |
| `backend/app/routes/` | HTTP 入口、请求校验和服务调用 |
| `backend/app/services/` | JD 解析、模型确认、测评状态、证据包、评分和报告业务 |
| `backend/app/agent/` | 测评 Memory、Planner、InterviewAgent 与工具接口 |
| `backend/app/models.py`、`schemas.py` | 数据库对象和共享请求/响应结构 |
| `backend/alembic/` | 数据库迁移 |
| `backend/tests/` | API、契约、状态、不变量和闭环测试 |
| `frontend/src/app/` | 应用入口、共享页面编排与样式 |
| `frontend/src/components/` | 对话、阶段轨道、工作台、测评和报告组件 |
| `frontend/src/lib/`、`types/` | API 客户端、展示逻辑和 TypeScript 契约 |
| `frontend/tests/` | UI 契约和 Playwright 浏览器测试；部分单元测试与源码同目录 |
| `prompts/` | 版本化 Prompt、输出 Schema 和清单 |
| `harness/` | 离线质量样例、评测 Runner 和样例生成器 |
| `integrations/jd-extraction/` | 用户主动触发的浏览器提取、站点适配与本地 Collector |
| `docs/`、`design/` | 需求、规格、架构、报告和已确认交互设计 |

上述路径均相对于仓库根目录。根目录的 `start_project.ps1` 和 `start_project.bat` 是统一启动入口。

## 三阶段数据流

```text
用户提供 JD
  → 阶段一：解析、汇总、人工修订、确认
  → ConfirmedModelSnapshot（不可变岗位模型）
  → 阶段二：提问、回答分析、状态机、证据观察
  → AssessmentEvidencePackage（FULL / PARTIAL）
  → 阶段三：确定性评分、受约束解释
  → ProfileReportVersion（版本化报告）
```

阶段一的主要业务入口是 `analysis.py`、`aggregation.py` 和 `stage1_tools.py`。阶段二由 `assessment_service.py` 调用 `InterviewAgent`，Planner 决定问题策略，`assessment_state.py` 控制合法状态流转，`evidence_package.py` 输出证据包。阶段三由 `report_service.py` 编排，`scoring.py` 计算分数，`profile.py` 与报告咨询服务生成和解释叙述。

AI 通过 `llm.py`、`structured_llm.py` 和阶段适配服务参与语义处理；Prompt 由 `prompt_registry.py` 管理，调用信息由 `llm_observability.py` 记录。正式评分、权重、版本冻结和状态流转由程序控制。简历通过 `resume_context.py` 提供个性化背景，不能作为正式评分证据。

前端共用 `App.tsx`、`StageRail`、`HistoryNav` 与对话区域，各阶段使用对应工作台；服务端快照是业务状态事实源。

## 本地生成文件

- `app.db`、`.pytest-run/`：本地数据库与隔离测试数据库，禁止提交；清理时保留用户数据。
- `data/*.log`：启动脚本产生的服务日志。
- `frontend/.cache/`、`frontend/dist/`：编译缓存与构建产物。
- `test-results/`、`frontend/playwright-report/`：浏览器测试产物。
- `.superpowers/`、`report_render/`：过程性工作目录，不保留在版本控制中。

## 后续职责整理

当前 `App.tsx` 同时编排三个阶段，后端服务仍主要平铺；`main.py` 同时执行建表与 SQLite 补字段，Alembic 的现有首个迁移仅添加日志字段。这些属于后续代码重构范围，本次目录清理未改变它们。数据库迁移整理须先覆盖全新数据库和已有数据库的升级路径，不能直接移除兼容逻辑。

验证命令和启动方式见 [项目 README](../../README.md)，规格与开发入口见 [文档导航](../README.md)。
