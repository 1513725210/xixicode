# 🧠 MiniCode

> 面向本地代码仓库的 AI Coding Agent · V1 Skeleton

MiniCode 是一个轻量级命令行 AI 编程助手。它理解你的代码库、制定执行计划、调用工具修改代码，并在任务完成后自动总结经验。

**目标不是聊天机器人，而是能自主完成工程任务的 Coding Agent。**

---

## 快速开始

```bash
# 1. 安装
pip install -e .

# 2. 运行（One-shot 单任务模式）
minicode "修复订单服务 NPE"

# 3. 或者进入 REPL 交互模式
minicode
```

---

## 使用方式

### One-shot 模式

直接传入任务，执行完退出：

```bash
minicode "重构用户模块"
minicode "给支付模块添加测试"
minicode "修复 OrderService 的 NullPointerException"
```

### REPL 模式

进入交互式对话，连续执行多个任务：

```bash
$ minicode

╭──────────────────────────────────────────────────────────╮
│   🧠 MiniCode v0.1.0                                     │
│   仓库  /home/me/biz-project          模型  deepseek-v3  │
│   分支  main                           文件  1,247 个     │
╰──────────────────────────────────────────────────────────╯

> 修复订单服务 NPE

  💭 分析中...
  ● 计划: 4 步
  ● Skill: bug_fix
  ...
  ✅ 任务完成 · 4 步 · 4 Tool

> 给这个模块加测试

  ...

> /exit
```

### 从文件读取任务

```bash
minicode --task task.md
```

### 命令行选项

| 选项 | 说明 |
|------|------|
| `-q, --quiet` | 安静模式，仅显示最终结果 |
| `-v, --verbose` | Rich Live Panel 模式，显示持久状态面板 |
| `--debug` | 输出原始 LLM 请求/响应 |
| `-y, --yes` | 自动批准所有高风险操作 |
| `--dry-run` | 只读模式，不执行任何写操作 |
| `--model MODEL` | 指定 LLM 模型 |
| `--no-memory` | 禁用记忆检索 |
| `--task FILE` | 从文件读取任务描述 |
| `--version` | 显示版本号 |

---

## REPL 元命令

在交互模式中，`/` 前缀触发元命令：

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助 |
| `/skills` | 列出可用 Skill |
| `/history` | 查看本次会话 Tool 调用历史 |
| `/memory` | 查看会话记忆 |
| `/model` | 查看当前模型 |
| `/clear` | 清屏 |
| `/exit`, `/quit` | 退出 |

---

## 执行流程

MiniCode 的核心是 **Query Loop**：

```
User 输入任务
  ↓
💭 think()        → Planner 拆解为执行步骤
  ↓
🎯 select_skill() → Skill Router 选择合适的技能
  ↓
● execute()       → 调用 Tool（grep → read → edit → test）
  ↓
✅ done           → 任务完成，记录 Memory
```

每一步通过 **AgentEvent** 流式输出到终端，用户始终知道 Agent 在做什么。

### 任务路由

Planner 根据关键词自动选择策略：

| 任务关键词 | Skill | 步骤流程 |
|-----------|-------|---------|
| `修复` / `fix` | bug_fix | grep → read → edit → test |
| `重构` / `refactor` | refactor | read → edit → test |
| `测试` / `test` | write_test | read → write → test |
| 其他 | bug_fix | grep → read |

---

## 架构

```
User
  ↓
CLI (main.py)       ← Click + Rich，Event Consumer
  ↓
Agent (loop.py)     ← Query Loop async generator
  ├── Planner       ← 任务拆解
  ├── Skill Registry ← 技能选择
  ├── Tool Executor  ← 原子操作
  ├── Memory Store   ← 长期记忆
  ├── Context Builder ← Prompt 拼装
  └── Security       ← 4 级安全防护
```

**设计原则：**
- **Agent First** — User 只能通过 Agent 调用 Tool，禁止 User → Tool 直连
- **Memory Driven** — 每次执行结果沉淀为记忆资产
- **Skill Oriented** — Agent 学习 Skill，Skill 组合 Tool
- **Safe Execution** — 高风险操作必须审批

---

## 当前状态

**V1 Skeleton · 全部 Mock 实现**

```
✅ AgentEvent 事件总线     → 7 种事件类型 + 流式渲染
✅ Query Loop 完整循环      → async generator
✅ Planner 任务拆解         → 关键词匹配（4 种计划）
✅ Skill 路由               → 关键词匹配（4 种 Skill）
✅ CLI 启动 + REPL          → Banner + one-shot + 交互
✅ 元命令                   → /help /skills /history /memory
✅ 安全审批 UI              → 5 选项（当前全 safe，自动通过）
✅ 测试覆盖                 → 15 条 · 全部通过
⏳ 真实 Tool                → 待接入（ReadFile, Grep, EditFile...）
⏳ 真实 LLM Client          → 待接入（DeepSeek/Claude API）
⏳ SQLite + vec Memory      → 待接入（替换 Mock MemoryStore）
⏳ Skill 文件加载           → 待接入（YAML → SkillRegistry）
```

---

## 开发指南

### 安装开发依赖

```bash
pip install -e ".[dev]"
```

### 运行测试

```bash
pytest tests/ -v
```

### 项目结构

```
minicode/
├── pyproject.toml
├── README.md
├── spec.md                  # 完整设计规约
│
├── src/minicode/
│   ├── main.py              # CLI 入口
│   ├── events.py            # AgentEvent 类型定义
│   ├── agent/               # Agent 层
│   │   ├── loop.py          # Query Loop 核心
│   │   └── planner.py       # 任务拆解
│   ├── tool/                # Tool 层
│   │   ├── base.py          # Tool 抽象基类
│   │   └── mock.py          # Mock 实现
│   ├── skill/registry.py    # Skill 注册表
│   ├── llm/client.py        # LLM 客户端
│   ├── memory/store.py      # 记忆存储
│   ├── context/builder.py   # 上下文构建
│   └── security/classifier.py # 安全分级
│
└── tests/
    ├── conftest.py          # 共享 fixture
    └── test_loop.py         # Agent Loop 测试（15 条）
```

### 分层依赖规则

```
agent  → skill, context, memory, llm, events
skill  → tool, llm
tool   → (独立)
memory → (独立)
context → memory
security → tool
```

禁止反向依赖和跨层调用。

---

## 路线图

| 版本 | 内容 |
|------|------|
| V1 | Single Agent, Skill, Memory, Tool, Reflection |
| V2 | Context Compression, Prompt Cache, Observability |
| V3 | Multi Agent, Worktree, Parallel Execution |
| V4 | Self Evolving Skill Generation |

详见 [spec.md](./spec.md)。

---

## License

MIT
