# MiniCode Specification

**Version:** v1.0  
**Author:** Deng Xiaoyi  
**Status:** Draft

---

## 1. Project Overview

### 1.1 Vision

MiniCode 是一个面向本地代码仓库的 AI Coding Agent。

系统参考 Claude Code 架构设计，通过 Query Loop + Tool Use 实现自主任务执行能力。

目标并非构建聊天机器人，而是构建能够：

- 理解代码库
- 制定执行计划
- 调用工具
- 修改代码
- 运行测试
- 总结经验
- 持续进化

的工程级 Coding Agent。

---

## 2. Design Principles

### Principle 1 — Agent First

所有功能围绕 Agent 构建。

- **禁止：** User → Tool
- **必须：** User → Agent → Tool

### Principle 2 — Memory Driven

Agent 必须具备长期记忆能力。任何执行结果都应有机会沉淀为记忆资产。

### Principle 3 — Skill Oriented

Agent 不直接学习 Tool。Agent 学习 Skill。Skill 再组合 Tool。

### Principle 4 — Safe Execution

所有危险操作必须经过审查。

---

## 3. MVP Scope

**V1 不实现：**

- GUI
- Browser Agent
- Voice
- Remote Execution

**仅支持：**

- Local Repository
- CLI
- Tool Calling
- Memory
- Skill
- Reflection

---

## 4. System Architecture

```
User
  ↓
Main Agent
  ↓
Planner
  ↓
Skill Router
  ↓
Skill Executor
  ↓
Tool Layer
  ↓
Memory Layer
  ↓
Reflection Layer
```

---

## 5. Core Workflow — Query Loop

Agent 持续运行以下循环：

1. Understand Task
2. Plan
3. Select Skill
4. Execute Tool
5. Observe Result
6. Update Context
7. Determine Completion
8. Reflect

### 5.1 Detailed Loop with Memory Injection

Memory 检索发生在 `think()` 之前，确保 LLM 每次推理都能看到相关历史经验：

```python
while not task_completed:
    # Step 6 from previous iteration (or initial load)
    update_context()       # ← 检索 Memory，注入 context
        # ├── User Memory       → 全量注入 (数据量小)
        # ├── Knowledge Memory  → 语义检索 Top 5
        # └── Procedural Memory → 语义检索 Top 3
    
    # Step 1-3 combined
    plan = think(context)   # ← LLM 推理 (context 已含 Memory)
    
    # Step 3-4
    skill = select_skill(plan, context)
    
    # Step 4-5
    result = execute(skill, context)
    
    # Step 6
    observe(result)
    
    # Step 7 — loop continues or breaks

# Step 8 — after loop
reflect(task, execution_history)
```

### 5.2 Memory Retrieval Optimization

| 策略 | 描述 |
|------|------|
| 首轮全量检索 + 后续增量 | 第 1 轮检索全部 Memory，后续只检索新产生的 |
| 缓存短路 | Prompt Cache 命中时跳过检索 |

### 5.3 Agent Event Bus

Agent 是 User 和 Tool 之间的唯一网关。User 不直接看到 Tool 输出，
Agent 通过事件总线选择性地暴露内部状态：

```python
class AgentEvent:
    type: Literal[
        "thinking",       # Agent 在推理
        "tool_call",      # 即将调用 Tool（可触发审批）
        "tool_result",    # Tool 返回结果
        "progress",       # 进度更新
        "need_approval",  # 暂停等待 User 批准（Security Layer 4）
        "reflection",     # 反思总结
        "done",           # 任务完成
    ]
```

User → Agent → Tool 的硬约束：
- Tool 不知道 User 的存在
- User 不知道 Tool 的存在
- Tool 错误由 Agent 处理（重试 / 换策略 / 上报），不直接抛给 User
- User 中途介入（批准、纠正）通过 Agent 事件总线，不走旁路

---

## 6. Agent Architecture

### 6.1 Main Agent

**职责：**

- 理解用户需求
- 管理上下文
- 规划任务
- 调度 Skill
- 判断任务完成

**输入：** Task  
**输出：** Execution Plan

### 6.2 Planner Agent

**职责：** 任务拆解

**Example:**

```
User: Fix order service NPE

Output:
  Step1: Read Logs
  Step2: Locate Source
  Step3: Root Cause
  Step4: Fix
  Step5: Test
```

### 6.3 Reflection Agent

**职责：** 任务结束后总结经验

**输出：**

- Procedural Memory
- Episodic Memory
- Knowledge Memory

---

## 7. Skill System

### 7.1 Objective

解决 Tool 数量增长导致的选择困难问题。

**Skill = Reusable Capability**

### 7.2 Design Decision: Skill = Prompt + Constraints

Skill 不是硬编码的 Tool 调用序列，而是一段 **Prompt 模板 + Tool 约束**。
Agent 选中 Skill 后，将 Skill 的 system_prompt 注入上下文，LLM 在 Skill 的框架内
动态决定具体调用哪个 Tool、传什么参数。

- Skill 是知识，不是代码
- Skill 提供边界（tool_allowlist），Agent 在边界内自主决策
- V1 Skill 文件格式：YAML

### 7.3 Example Skills

- Bug Fix Skill
- Refactor Skill
- Test Skill
- Code Review Skill
- Dependency Analysis Skill

### 7.4 Skill 定义格式

```yaml
# 示例：skills/builtins/bug_fix.yaml
name: bug_fix
description: 定位并修复代码中的 Bug
tags: [java, spring, exception]
examples: [NPE, OOM]
system_prompt: |
  你是一个 Bug 修复专家。按以下流程操作：
  1. 从错误信息找出关键文件和行号
  2. 阅读源码，理解上下文
  3. 定位根因
  4. 用最小修改修复
  5. 运行测试验证
tool_allowlist:
  - read_file
  - grep
  - edit_file
  - run_test
```

---

## 8. Skill Routing

### 8.1 V1 策略：LLM 直接选择

V1 预计 Skill 数量 < 20，不需要两阶段 Embedding Recall。
将所有 Skill 的 `name + description` 放入 system prompt，LLM 直接选择。

```
[System Prompt]
  ...
  Available Skills:
  - bug_fix: 定位并修复代码中的 Bug
  - refactor: 重构代码，改善结构不改变行为
  - code_review: 审查代码变更，指出问题
  - write_test: 为指定代码编写测试用例
```

### 8.2 V2 升级路径

当 Skill 数量超过 ~30 个时，引入两阶段路由：

- **Stage 1:** Embedding Recall → Top K=20
- **Stage 2:** LLM Rerank → Top K=5

**Output:** Selected Skill + Confidence Score

---

## 9. Tool System

### 9.1 Tool Interface

```python
class Tool:
    name: str
    description: str          # LLM 可读的功能描述
    parameters: dict           # JSON Schema 参数定义
    risk_level: Literal["safe", "medium", "high"]

    async def execute(self, **params) -> ToolResult:
        """执行工具。高风险操作触发 Security Layer 4 审批。"""

class ToolResult:
    success: bool
    output: str                # 人类可读输出
    error: str | None
    artifacts: list[Artifact]  # 产生的文件 diff 等
```

### 9.2 V1 Tool 清单 (含风险分级)

| Tool        | Risk    | Description              |
|-------------|---------|--------------------------|
| ReadFile    | safe    | 读取文件内容              |
| SearchFile  | safe    | 按文件名搜索              |
| Grep        | safe    | 搜索文件内容 (ripgrep)    |
| GitStatus   | safe    | Git 工作区状态            |
| GitDiff     | safe    | Git 差异                  |
| GitLog      | safe    | Git 提交历史              |
| GitShow     | safe    | Git 查看具体 commit       |
| RunTest     | medium  | 运行测试套件              |
| RunCommand  | high    | 执行任意 shell 命令       |
| WriteFile   | high    | 写入/覆盖文件             |
| EditFile    | high    | SEARCH/REPLACE 精确编辑   |

### 9.3 EditFile 语义

采用 **SEARCH/REPLACE 块** 方式（不依赖语言/AST）：

```
EditFile(
    path="src/service.py",
    search="  return old_value",    # 精确匹配文本
    replace="  return new_value"    # 替换文本
)
```

- `search` 必须在文件中唯一出现一次，否则拒绝
- 对语言无关，纯文本操作
- 比 WriteFile 更安全（只改目标片段）

---

## 10. Memory System

```
Memory Layer
├── User Memory       — 长期用户偏好
├── Episodic Memory   — 任务执行历史
├── Procedural Memory — 经验总结
└── Knowledge Memory  — 知识资产
```

### 10.1 Memory Types

| Type               | Description                  | Example                           |
|--------------------|------------------------------|-----------------------------------|
| User Memory        | 长期用户偏好                 | Preferred Language = Java         |
| Episodic Memory    | 任务执行历史                 | Fixed OrderService NPE            |
| Procedural Memory  | 经验总结                     | NPE → check DTO mapping first     |
| Knowledge Memory   | 知识资产                     | Project Architecture Summary      |

### 10.2 Memory Storage

- Metadata
- Content
- Embedding
- Timestamp
- Importance Score
- Access Count

**Storage Backend:** SQLite + sqlite-vec

**Design Decision:** V1 选择 SQLite + sqlite-vec 而非 ChromaDB。原因：
- 零额外进程，`pip install sqlite-vec` 即用
- 向量搜索用内积，单机几百到几千条 memory 足够
- 无需管理 ChromaDB server/client 生命周期
- ChromaDB 在 V2+ 数据量增长后再评估

---

## 11. Reflection Pipeline

### 11.1 触发条件 (分级)

每个任务都做反思不经济。根据任务结果和复杂度分级触发：

| 条件                    | Reflection 深度       | 产出                           |
|-------------------------|-----------------------|--------------------------------|
| 成功 + < 3 Tool 调用    | 跳过                  | 仅记录 Episodic Memory          |
| 成功 + ≥ 3 Tool 调用    | 轻量反思              | 1 条 Procedural Memory          |
| 失败                    | 深度反思              | Procedural + Episodic + 根因分析 |
| 用户显式 `/reflect`     | 全量反思              | 以上全部 + 建议新 Skill          |

### 11.2 Pipeline

```
Task Finished
  ↓
判断触发级别
  ↓
Reflection (LLM 调用)
  ↓
Extract Lessons
  ↓
Categorize → Procedural / Episodic / Knowledge
  ↓
Store → MemoryStore
  ↓
Update Index → ChromaDB
```

### 11.3 Reflection Prompt

- What worked?
- What failed?
- Can this be reused?
- Should a new skill be created?

---

## 12. Context Management

### Problem

Context Window Overflow

### Solution — Hierarchical Compression

| Level | Type             | Size       |
|-------|------------------|------------|
| 1     | Short Summary    | <100 tokens |
| 2     | Detailed Summary | <500 tokens |
| 3     | Raw Content      | External Storage |

---

## 13. Prompt Cache

**Cache Key:** Task + Skill + Repository + Memory Snapshot

**Hit Strategy:** Semantic Similarity, Threshold > 0.9

---

## 14. Multi-Agent Design

### Architecture

```
Main Agent
  ↓
Sub Agent
  ↓
Tool
```

### Rules

- Sub Agent cannot call another Sub Agent
- Sub Agent cannot modify global state
- Sub Agent only returns results
- Main Agent owns final decision

---

## 15. Security Layer

| Level | Description                | Examples                        |
|-------|----------------------------|---------------------------------|
| 1     | Rule Check                 | Block: rm -rf, sudo, shutdown   |
| 2     | Prompt Injection Detection | Detect: ignore instruction, system prompt leak, credential extraction |
| 3     | Risk Classification        | SAFE / MEDIUM / HIGH            |
| 4     | Human Approval             | Required for: git push, mass edit, file deletion |

---

## 16. Observability

**Trace Every Step:** Task → Skill → Tool → Memory → Reflection

**Metrics:**

- Success Rate
- Tool Call Count
- Skill Recall Accuracy
- Memory Hit Rate
- Average Tokens
- Execution Time

---

## 17. Tech Stack

**Design Decision:** V1 不引入 LangGraph。Agent 拓扑是简单的 while 循环 + 单线调用，不需要 DAG 编排。
用原生 `asyncio` + LLM SDK 即可完整表达。LangGraph 在 V3/V4 拓扑真正复杂化时再评估。

| Component       | V1 选择                        | 理由                                    |
|-----------------|--------------------------------|-----------------------------------------|
| Agent Loop      | asyncio + 原生 while           | 循环就是循环，不是图                     |
| LLM SDK         | httpx + OpenAI-compatible API  | DeepSeek/Claude 都兼容此协议             |
| LLM Router      | 自写 ~50 行 wrapper 或 LiteLLM | 多后端路由，按任务复杂度选模型            |
| Prompt Template | Jinja2                         | 标准选择，Skill/Memory 注入用模板拼装    |
| Memory Vector   | SQLite + sqlite-vec            | 零额外进程，向量内积搜索，单机足够        |
| CLI             | Rich + Click / Typer           | 终端 UI + 参数解析                       |
| Config          | YAML (config.yaml)             | 用户可编辑，层次覆盖（default → user）    |
| Testing         | pytest + pytest-asyncio        | 标准异步测试框架                         |
| Sandbox         | **V1 不做 Docker**             | 依赖 Security Layer 的 Rule Check + 审批  |
| Observability   | structlog + 本地 JSON 日志      | V1 个人使用，不需要 OpenTelemetry        |
| Python          | 3.11+                          | asyncio 成熟，tomllib 内置               |

**核心依赖数量：~6 个包**（sqlite-vec, httpx, jinja2, click, rich, structlog）

---

## 18. Project Structure

```
minicode/
├── pyproject.toml              # 项目元数据 + 依赖声明
├── README.md
├── spec.md                     # 本文件
│
├── src/
│   └── minicode/
│       ├── __init__.py
│       ├── main.py             # CLI 入口 (Click/Typer)
│       │
│       ├── agent/              # Agent 层 — 系统大脑
│       │   ├── __init__.py
│       │   ├── loop.py         # Query Loop: while not done
│       │   ├── planner.py      # 任务拆解 (一次 LLM 调用)
│       │   └── reflection.py   # 任务后反思 (一次 LLM 调用)
│       │
│       ├── skill/              # Skill 层 — 可复用能力
│       │   ├── __init__.py
│       │   ├── registry.py     # Skill 加载 + 索引
│       │   ├── router.py       # 基于 LLM 的 Skill 选择
│       │   └── builtins/       # 内置 Skill 定义 (YAML)
│       │       ├── bug_fix.yaml
│       │       ├── refactor.yaml
│       │       ├── code_review.yaml
│       │       └── write_test.yaml
│       │
│       ├── tool/               # Tool 层 — 原子操作
│       │   ├── __init__.py
│       │   ├── base.py         # Tool 抽象基类 + ToolResult
│       │   ├── registry.py     # Tool 注册表
│       │   ├── file.py         # ReadFile, WriteFile, EditFile
│       │   ├── search.py       # SearchFile, Grep
│       │   ├── command.py      # RunCommand
│       │   ├── git.py          # GitStatus, GitDiff, GitLog, GitShow
│       │   └── test.py         # RunTest
│       │
│       ├── memory/             # Memory 层 — 长期记忆
│       │   ├── __init__.py
│       │   ├── models.py       # MemoryEntry 数据结构
│       │   ├── store.py        # MemoryStore (SQLite + sqlite-vec)
│       │   └── retriever.py    # 语义检索 + 元数据过滤
│       │
│       ├── context/            # Context 管理 — Prompt 拼装
│       │   ├── __init__.py
│       │   ├── builder.py      # System prompt 组装
│       │   └── compressor.py   # 层次压缩 (L1/L2/L3)
│       │
│       ├── security/           # Security 层 — 4 级防护
│       │   ├── __init__.py
│       │   ├── rules.py        # Level 1: 命令黑名单
│       │   ├── injection.py    # Level 2: 注入检测
│       │   ├── classifier.py   # Level 3: 风险分级
│       │   └── approval.py     # Level 4: 用户审批
│       │
│       ├── llm/                # LLM 抽象层
│       │   ├── __init__.py
│       │   ├── client.py       # OpenAI-compatible HTTP client
│       │   └── cache.py        # Prompt Cache (语义命中)
│       │
│       └── events.py           # AgentEvent 类型定义
│
├── tests/                      # 测试目录 — 镜像 src/ 结构
│   ├── __init__.py
│   ├── conftest.py             # 共享 fixture: mock LLM, tmp repo
│   ├── agent/
│   │   ├── test_loop.py
│   │   ├── test_planner.py
│   │   └── test_reflection.py
│   ├── skill/
│   │   ├── test_registry.py
│   │   └── test_router.py
│   ├── tool/
│   │   ├── test_file.py
│   │   ├── test_search.py
│   │   ├── test_command.py
│   │   ├── test_git.py
│   │   └── test_test.py
│   ├── memory/
│   │   ├── test_store.py
│   │   └── test_retriever.py
│   ├── context/
│   │   └── test_builder.py
│   ├── security/
│   │   ├── test_rules.py
│   │   └── test_classifier.py
│   └── llm/
│       └── test_client.py
│
├── skills/                     # 用户自定义 Skill (可选)
│   └── .gitkeep
│
└── .minicode/                  # 运行时数据 (gitignored)
    ├── memory/                 # SQLite + vec 持久化数据
    ├── cache/                  # Prompt cache 命中记录
    ├── traces/                 # 执行 trace 日志
    └── config.yaml             # 用户配置覆盖
```

### 18.1 分层依赖规则

```
agent  → skill, context, memory, llm, events
skill  → tool, llm
tool   → (独立, 仅依赖 base.py)
memory → (独立, SQLite + sqlite-vec)
context → memory
security → tool  (拦截 Tool 调用)

禁止反向依赖：tool 不能 import agent
禁止跨层：tool 不能 import skill
```

### 18.2 Skill 文件格式 (YAML)

```yaml
# skills/builtins/bug_fix.yaml
name: bug_fix
description: 定位并修复代码中的 Bug
tags: [debug, exception, error]
examples:
  - "Fix NPE in OrderService"
  - "修复这个报错"
system_prompt: |
  你是一个 Bug 修复专家。按以下流程操作：
  1. 从错误信息/堆栈找出关键文件和行号
  2. 阅读相关源码，理解上下文
  3. 定位根因（不要猜测，用 grep/read_file 验证）
  4. 用 SEARCH/REPLACE 应用最小修复
  5. 运行相关测试验证
  注意：不要大范围重构，只修 Bug。

tool_allowlist:
  - read_file
  - grep
  - edit_file
  - run_test
  - git_diff
```

## 19. CLI Interaction Design

### 19.1 启动与输入

```bash
$ minicode
```

```
╭──────────────────────────────────────────────────────────╮
│                                                          │
│   🧠 MiniCode v0.1.0                                     │
│                                                          │
│   仓库  /home/me/biz-project          模型  deepseek-v3  │
│   分支  main                           文件  1,247 个     │
│                                                          │
│   输入任务开始，或 /help 查看帮助                        │
│                                                          │
╰──────────────────────────────────────────────────────────╯

>
```

零启动成本：不加载 LLM、不连 Memory、不预热——只显示环境信息立即就绪。

### 19.2 执行模式

| 模式 | 命令 | 行为 |
|------|------|------|
| One-shot | `minicode "修复 NPE"` | 执行 → 输出结果 → 退出 |
| REPL | `minicode` | 进入交互式 REPL，任务完成后回到提示符 |
| File input | `minicode --task task.md` | 从文件读取任务描述执行 |

### 19.3 Progress Streaming

本质是 AgentEvent → 流式渲染。每个事件实时展示为一行状态：

```
> 修复订单服务 NPE

  💭 分析中...
  📋 bug_fix · 2 步计划

  ● Reading logs...
  ● Searching OrderService...
  ● Root cause found: line 47 null check missing
  ● Editing file...
  ● Running tests...

  ✅ 完成 · 2 步 · 5 次 Tool · 2.1s
```

AgentEvent 类型与 UI 渲染映射：

| Event | 图标 | 流式渲染 |
|-------|------|---------|
| `thinking` | 💭 | `💭 分析中...` |
| `tool_call` | ● | `● Reading OrderService.java...` |
| `tool_result` | ✓/✗ | 追加 `─ 187 行 ✓` 或 `✗ 文件不存在` |
| `progress` | ● | `● Root cause found: ...` |
| `need_approval` | ⚠ | 暂停，显示审批 UI（见 19.4） |
| `reflection` | 🧠 | `🧠 反思中...` |
| `done` | ✅ | `✅ 完成 · N 步 · M Tool · Xs` |

### 19.4 Approval UI

高风险 Tool 执行前暂停，用户必须确认。Agent 不会自动修改代码。

```
  ⚠ High Risk Action

  Tool:  EditFile
  File:  src/order_service.py
  Diff:
    -  String name = order.getCustomer().getName();
    +  Customer c = order.getCustomer();
    +  if (c == null) throw new OrderException("...");
    +  String name = c.getName();

  Approve? [y/n/e/s/a] ›
```

审批选项：

| 键 | 行为 |
|----|------|
| `y` | 批准，Tool 执行 |
| `n` | 拒绝，Agent 重新规划 |
| `e` | 打开编辑器修改 diff，保存后执行修改版 |
| `s` | 跳过此 Tool，继续下一步 |
| `a` | 放弃整个任务 |

快捷操作：
- `y all` — 本次任务后续全部自动批准
- 空输入 = `y`（可配置）

### 19.5 Ctrl+C 中断

```
  中断
  [c] 继续等待   [r] 重新规划   [a] 放弃任务
  ›
```

| 键 | 行为 |
|----|------|
| `c` | 继续执行，Agent 不重置 |
| `r` | 中断当前步，Agent 重新规划（已完成步骤保留） |
| `a` | 放弃任务，回到提示符 |

### 19.6 Session View — /history 和 /memory

```
> /history

  本次会话:
  ✅ 修复订单服务 NPE            (2 步, 5 Tool, 2.1s)
  ✅ 添加订单验证测试             (1 步, 3 Tool, 1.4s)
  ✗ 分析支付模块循环依赖          (失败: 缺少依赖信息)

> /memory

  会话记忆:
  [Procedural] NPE → 先检查 DTO mapping 的 null 传入
  [Knowledge]  OrderService 依赖: PaymentService, InventoryService

> /memory search NPE

  [Procedural] NPE → 先检查 DTO mapping 的 null 传入  (本次)
  [Episodic]   修复 UserService NPE                   (2 天前)
```

### 19.7 元命令全集

```
/help            帮助
/reflect         触发深度反思
/memory          列出会话记忆
/memory search   搜索记忆
/skills          列出可用 Skill
/history         查看任务历史
/undo            撤销最近编辑
/diff            查看当前未提交变更
/model           查看/切换模型
/config          查看配置
/config set      修改配置项
/clear           清屏
/exit, /quit     退出
```

### 19.8 命令行参数

```
-q, --quiet      安静模式（仅最终结果）
-v, --verbose    Rich Live Panel 模式
--debug          原始 LLM 请求/响应
-y, --yes        自动批准所有操作
--dry-run        只读模式，不执行写操作
--model MODEL    指定模型
--no-memory      禁用记忆检索
--task FILE      从文件读取任务
```

### 19.9 Verbosity 分层

| 级别 | 触发 | 显示内容 |
|------|------|---------|
| quiet | `-q` | 仅最终 `✅` 或 `✗` 结果 |
| normal | 默认 | 流式 AgentEvent + 审批暂停 |
| verbose | `-v` | Rich Live Panel 持久状态 + 全部 Tool 输出 |
| debug | `--debug` | 原始 LLM 请求/响应 + 完整 context dump |

---

## 20. LLM Client — 多后端路由

### 20.1 设计目标

- 统一接口，屏蔽不同 LLM 后端的 API 差异
- 按任务复杂度自动路由到不同模型
- 主力不可用时自动降级
- 可扩展新的模型后端

### 20.2 接口

```python
class LLMClient:
    """OpenAI-compatible 协议的 LLM 客户端"""

    async def chat(
        self,
        messages: list[Message],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """发送 chat completion 请求"""

    async def chat_stream(
        self,
        messages: list[Message],
        model: str | None = None,
    ) -> AsyncIterator[str]:
        """流式 chat，返回 token 迭代器"""

class LLMResponse:
    content: str
    model: str
    usage: TokenUsage              # prompt_tokens, completion_tokens
    finish_reason: str
```

### 20.3 后端着册

```yaml
# 后端配置
backends:
  deepseek:
    base_url: https://api.deepseek.com/v1
    api_key: ${DEEPSEEK_API_KEY}
    models: [deepseek-v3, deepseek-r1]

  claude:
    base_url: https://api.anthropic.com/v1
    api_key: ${ANTHROPIC_API_KEY}
    models: [claude-sonnet-4, claude-opus-4]

  openai:
    base_url: https://api.openai.com/v1
    api_key: ${OPENAI_API_KEY}
    models: [gpt-4o, gpt-4o-mini]
```

### 20.4 路由策略

```python
class LLMRouter:
    """按任务复杂度选择模型"""

    def route(self, task: Task, context: TaskContext) -> str:
        """返回 model id"""
        if task.estimated_complexity == "simple":
            return "deepseek-v3"       # 或 gpt-4o-mini
        if task.estimated_complexity == "complex":
            return "claude-sonnet-4"   # 或 deepseek-r1
        return self.config.default_model

    async def call_with_fallback(
        self, messages: list[Message]
    ) -> LLMResponse:
        """主力失败自动降级"""
        primary = self.route(task)
        try:
            return await self.client.chat(messages, model=primary)
        except (RateLimitError, ServiceUnavailable):
            fallback = self.config.fallback_model
            return await self.client.chat(messages, model=fallback)
```

### 20.5 复杂度评估

Agent 在 `think()` 阶段让 LLM 自评任务复杂度：

| 复杂度 | 特征 | 模型选择 |
|--------|------|---------|
| simple | 单文件、已知模式、无推理 | deepseek-v3 / gpt-4o-mini |
| medium | 多文件、需定位、有推理 | deepseek-v3 |
| complex | 跨模块、深度推理、架构决策 | claude-sonnet-4 / deepseek-r1 |

---

## 21. Roadmap

| Version | Features                                              |
|---------|-------------------------------------------------------|
| V1      | Single Agent, Skill, Memory, Tool, Reflection         |
| V2      | Context Compression, Prompt Cache, Observability      |
| V3      | Multi Agent, Worktree, Parallel Execution             |
| V4      | Self Evolving Skill Generation, Automatic Skill Discovery |
