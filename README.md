# Contract Verification Agent (Enterprise Document Async Hub)

面向企业级合同场景的**异步文档解析与大模型（LLM）智能核验系统**。基于 FastAPI、Celery 与 DeepSeek API 构建，解决大文件同步处理阻塞、非结构化数据提取困难及证据溯源等核心痛点。

## ✨ 核心特性 (Features)

*   **⚡ 异步高并发架构**：使用 **Celery + RabbitMQ** 实现任务解耦，API 仅负责接收并返回 Task_ID。实测接口 P99 响应时间从同步处理的 **13.9 秒骤降至 0.35 秒**。
*   **🤖 智能 Agent 工具调用**：接入 **DeepSeek API**，通过 `search_document`、`get_source` 等 Tool Calls 编排，实现文档的按需检索与多轮推理。
*   **🛡️ 严格的数据与证据核验**：利用 **Pydantic** 进行强类型校验，确保 LLM 返回的 JSON 结构化数据（如金额、甲方）绝对合规；通过逐字引文（Quote）比对，强制要求每个提取字段附带原文出处，防止模型幻觉。
*   **🔒 幂等与去重机制**：基于文件 **MD5 + SHA-256** 双重指纹及数据库唯一约束，在并发测试中精准拦截重复提交，仅生成唯一任务 ID。
*   **⚙️ 持久化与容错设计**：采用 Outbox 模式持久化任务，配合行级锁（Row Lock）和租约（Lease）机制防止任务丢失；内置最多 **3 次异常重试**与软超时保护。
*   **📊 严谨的性能边界**：明确限制 50 MiB 上传上限及 20 万字符解析上限，避免大模型上下文截断（实测超出即返回 413 拒绝），不静默丢数据。

1. 无 Docker 本地演示 (Mock 模式)
无需配置数据库和 API Key，直接运行自带的 Mock 演示脚本：

powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-demo.ps1
打开 http://127.0.0.1:8000，上传 examples/contract.txt 即可查看离线核验流程（离线模式仅识别自带示例）。

2. 接入真实大模型与完整服务栈
请确保已安装 Docker 环境。

bash
# 1. 配置环境变量 (填入你的真实 DeepSeek API Key)
cp .env.example .env

# 2. 一键启动 FastAPI + Celery + RabbitMQ + PostgreSQL + Redis
docker compose up --build -d
访问 http://127.0.0.1:8000/docs 查看自动生成的 Swagger 接口文档。

📈 性能压测与数据指标 (Benchmark)
基于本地 6 并发、320 组真实中英文测试集的控制实验（详见仓库中的 BENCHMARK.md）：

指标维度	同步阻塞处理	异步架构处理
接口 P99 耗时	13.904 秒	0.354 秒
并发去重拦截	-	8路并发请求仅产生 1 个任务ID
文件体积边界	-	> 52.4MB 精准返回 413 状态码
LLM 提取成本基线：中文合成样本平均约 4593 Token/份，英文 CUAD 样本平均约 13501 Token/份。

模型效果对照：在 12 份固定合成样本上，LLM 与正则表达式在“合同金额”字段提取准确率均为 83.33%。本系统据此明确了“正则前置 + LLM 兜底”的混合提取演进路线。

📡 核心接口 (API Endpoints)
路由	方法	描述
/api/tasks	POST	上传文档，计算指纹并异步创建任务，返回 202
/api/tasks/{id}	GET	查询任务状态、提取结果、Token 消耗及证据引文
/api/tasks/{id}/reviews	POST	提交人工复核决定（认可/退回）与更正记录
/health	GET	服务与数据库健康检查
## 🏗️ 系统架构 (Architecture)
```mermaid
flowchart LR
    API[上传接口] --> DB[(PostgreSQL任务记录)]
    DB --> Dispatcher[持久化分发器 (Outbox)]
    Dispatcher --> MQ[RabbitMQ]
    MQ --> Worker[Celery Worker]
    Worker --> Agent[DeepSeek API & 工具核验]
    Worker --> DB
    Worker --> Redis[(Celery 执行元数据)]
    Poll[前端状态轮询] --> DB
