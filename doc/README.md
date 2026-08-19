# 开发文档索引

本文档集由 `product-requirements.md` 拆解而来，用于在正式编码前明确架构、接口、数据、风控和验收边界。所有文档已完善到"可查可复制"的程度，配合 `development-roadmap.md` 作为实施主线对照实施。

## 怎么用这些文档

1. **实施时**：打开 [development-roadmap.md](development-roadmap.md)，按阶段 0 → 8 顺序，每步勾选完成。每步会告诉你"做什么 / 命令 / 代码骨架 / 验证方法"，并指向需要查细节的设计文档。
2. **查字段/DDL**：去 [database-design.md](database-design.md)（含完整 DDL、索引、约束、SQLAlchemy 模型骨架）。
3. **查接口出入参**：去 [api-spec.md](api-spec.md)（每个接口有请求参数表 + JSON 示例 + 错误码）。
4. **查代码骨架**：去对应设计文档（sdk / backend / risk-control / strategy / frontend / ai-analysis），都有可复制的 Python/TS 骨架。
5. **遇到决策**：先查 [open-questions.md](open-questions.md)，每条都有"建议默认值"，不阻塞开发。
6. **每阶段结束**：跑 [testing-acceptance.md](testing-acceptance.md) 对应的测试用例和验收 checklist。

## 推荐阅读顺序

1. [product-requirements.md](product-requirements.md)：产品需求源文档（PRD）。
2. [architecture-design.md](architecture-design.md)：总体架构、模块边界和关键业务流。
3. [database-design.md](database-design.md)：PostgreSQL 表结构、约束、索引、保留策略、**完整 DDL**。
4. [api-spec.md](api-spec.md)：前后端接口契约、统一响应、错误码、实时事件、**逐接口出入参**。
5. [sdk-adapter-design.md](sdk-adapter-design.md)：同花顺股票/期货 SDK 适配层、**Pydantic 模型与 Mock 骨架**。
6. [tqsdk-futures-integration.md](tqsdk-futures-integration.md)：天勤 TqSdk 期货通道（绕开原生 CTP SDK 门槛）、**Runtime 模型、配置、只读冒烟与验收顺序**。
7. [risk-control-design.md](risk-control-design.md)：强制风控、熔断、一键停止、恢复规则、**规则类骨架**。
7. [strategy-design.md](strategy-design.md)：策略生命周期、信号模型、运行隔离、**Strategy 基类与示例策略**。
7b. [strategy-builder-design.md](strategy-builder-design.md)：规则 DSL、策略构建器、**AI 自然语言生成**。
8. [backend-design.md](backend-design.md)：后端工程结构、事务、任务调度、审计、**目录清单与各层骨架**。
9. [frontend-design.md](frontend-design.md)：前端页面结构、状态流、危险操作交互、**路由与组件骨架**。
10. [ai-analysis-design.md](ai-analysis-design.md)：AI 复盘数据口径、报告结构、安全限制、**指标计算与报告骨架**。
11. [handover.md](handover.md)：**阶段 0–8 交接说明**（做了什么 / 没做什么 / 下一步）。
11. [deployment-guide.md](deployment-guide.md)：Windows 本地开发和部署、**.env 示例与启动脚本**。
12. [testing-acceptance.md](testing-acceptance.md)：测试策略、验收清单、关键用例、**测试代码骨架**。
13. [development-roadmap.md](development-roadmap.md)：**MVP 开发阶段实施主线（可勾选）**。
14. [open-questions.md](open-questions.md)：进入开发前需要确认的问题（含建议默认值）。

## 文档完善度速查

| 文档 | 完善内容 |
| --- | --- |
| development-roadmap.md | 8 阶段 + 收尾，每步带"做什么/命令/代码骨架/验证"，可勾选 |
| database-design.md | 8 个迁移的完整 DDL、触发器、SQLAlchemy 基类与模型示例、归档脚本 |
| api-spec.md | 统一响应骨架 + 35 个接口逐个出入参表与 JSON 示例 + WebSocket 事件字段 |
| sdk-adapter-design.md | Pydantic 标准模型、适配器基类与错误体系、Mock 适配器骨架、工厂、契约测试 |
| tqsdk-futures-integration.md | 天勤 TqSdk 通道架构、配置、映射、实盘双开关、只读冒烟与验收顺序 |
| backend-design.md | 完整目录文件清单（标注阶段）、config/session/Alembic/main/pytest 骨架、依赖清单 |
| risk-control-design.md | 状态迁移矩阵、11 条风控规则类骨架、风控服务骨架、熔断监控任务、配置样例 |
| strategy-design.md | Strategy 基类、StrategyContext、信号 schema、注册表、双均线示例策略、引擎骨架 |
| strategy-builder-design.md | 规则 DSL、指标/操作符、构建流程、AI 策略生成 API 与安全边界 |
| frontend-design.md | 目录结构、路由、API 客户端、WebSocket、全局 Provider、关键组件骨架、状态工具 |
| ai-analysis-design.md | 指标计算服务骨架、报告生成服务骨架（规则化 + AI）、系统提示词、报告模板 |
| deployment-guide.md | 完整 .env 示例、CONFIG_KEY 生成、一键启停脚本、备份脚本、命令速查、PG 安装与防火墙 |
| testing-acceptance.md | 风控/订单单测骨架、幂等集成测试、E2E 测试骨架、覆盖率目标、手工验收脚本 |
| open-questions.md | 每条补"建议默认值"和"何时必须确认"，降低决策阻塞 |
| README.md | 本文件：实施指引与文档速查 |

## 开发启动建议

第一阶段先实现可运行骨架：FastAPI 后端、React 前端、PostgreSQL 迁移、健康检查、系统状态、审计日志和 Mock SDK。真实 SDK 对接、策略和自动交易必须在风控与审计骨架完成后再接入。

**从哪里开始**：直接打开 [development-roadmap.md](development-roadmap.md) 的"阶段 0：开发准备"，按 0.1 → 0.5 一步步做。

## 关键原则

1. 策略、手动交易和自动撤单都不能绕过风控。
2. 任何交易相关事件都必须落库，审计日志只追加不修改。
3. SDK 差异只能出现在适配层，业务模块依赖统一领域模型。
4. AI 读取历史数据生成复盘报告；AI 可辅助生成策略 **定义 JSON**（须用户确认并校验），均不允许直接或间接触发下单。
5. MVP 以 Windows 本机单用户运行为边界，不引入多人权限和云端托管交易。
6. 真实 SDK 未就绪前必须用 Mock SDK 跑通全部端到端用例，再接入真实 SDK。
