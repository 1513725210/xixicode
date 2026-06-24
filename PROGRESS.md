# MiniCode 开发会话记录

**日期:** 2025-07-17  
**会话主题:** Spec 讨论 → Runtime Skeleton → DeepSeek 接入 → 真实 Agent Loop → 基础设施修复

---

## 1. 已完成的阶段

### Phase 0 — Spec 设计与定稿

| 决策 | 结论 |
|------|------|
| Agent 框架 | **不用 LangGraph**，原生 asyncio + while 循环 |
| Skill 形态 | **Prompt 模板 + tool_allowlist**（YAML 文件），不是代码 |
| V1 Skill 路由 | **LLM 直接选择**（Skill 列表进 prompt），V2 再引入 Embedding Recall |
| Tool 操作语义 | **SEARCH/REPLACE 块**（语言无关，精确文本匹配） |
| Reflection 触发 | **分级触发**（<3步跳过，≥3步轻量反思，失败深度反思） |
| Memory 存储 | **SQLite + sqlite-vec**（零额外进程），V1 不做 ChromaDB |
| Sandbox | **V1 不做 Docker**，依赖 Security Layer 4 级防护 |
| CLI 呈现 | **默认流式日志**，`-v` 模式 Rich Live Panel |
| LLM 后端 | **多后端路由**（按任务复杂度选模型，失败自动降级） |
| 核心依赖 | **~6 个包**：sqlite-vec, httpx, jinja2, click, rich, structlog |

**产出:** `spec.md`（21 章完整设计规约）

---

### Phase 1 — Runtime Skeleton（Mock 全通）

**目标:** `minicode` 命令可启动，跑通完整 Agent Loop，全部 Tool/Skill/LLM/Memory 用 Mock。

**产物:**

```
src/minicode/
├── main.py              CLI 入口（Click + Banner + Event Consumer）
├── events.py            AgentEvent 7 种类型 + 图标映射
├── agent/
│   ├── loop.py          Query Loop async generator
│   └── planner.py       KeywordPlanner（关键词匹配）
├── tool/
│   ├── base.py          Tool ABC + ToolResult
│   └── mock.py          Mock 全部 Tool
├── skill/registry.py    Mock SkillRegistry
├── llm/client.py        MockLLMClient
├── memory/store.py      Mock MemoryStore
├── context/builder.py   Mock ContextBuilder
└── security/classifier.py  Mock SecurityClassifier

tests/
├── conftest.py          共享 fixture
└── test_loop.py         15 条测试
```

**验证:**
- `minicode "修复 NPE"` → 4 步 bug_fix 流程 ✅
- `minicode "重构模块"` → 3 步 refactor 流程 ✅
- `minicode "添加测试"` → 3 步 write_test 流程 ✅
- `minicode "分析架构"` → 3 步 explore 流程 ✅
- `pytest tests/ -v` → 15 passed ✅

---

### Phase 1 (修正) — DeepSeek API 接入 + LLM 驱动 Planner

**变更文件:**

| 文件 | 改动 |
|------|------|
| `llm/client.py` | 新增 `DeepSeekLLMClient`（httpx + OpenAI-compatible），保留 `MockLLMClient` |
| `agent/planner.py` | `Planner` 改名 `KeywordPlanner`，新增 `LLMPlanner`（JSON prompt → DeepSeek → 解析） |
| `agent/loop.py` | thinking 事件附带 LLM reasoning |
| `main.py` | `_build_loop()` 自动检测 `deepseek` 环境变量 → DeepSeek 或 Mock |
| `tests/conftest.py` | `Planner` → `KeywordPlanner`，测试路径不受影响 |

**自动切换逻辑:**
- `$deepseek` 已设置 → `DeepSeekLLMClient` + `LLMPlanner`
- `$deepseek` 未设置 → `MockLLMClient` + `KeywordPlanner`

---

### Phase 1 (重构) — 真正的 Query Loop + 审批阻塞 + 容错

**修复的审计问题:** #1（Loop 不是 Loop）、#4（审批不阻塞）、#8（执行零容错）

**核心架构变更:**

```
修复前:                                修复后:
plan = planner.plan(task)              while not done:
for step in plan.steps:                    next_action = planner.next_step(context)
    execute(step)                          if next_action.done: break
yield done                                 risk = classify(action)
                                           if risky: await approval_event.wait()  ← 阻塞
                                           try:
                                               result = execute(action)
                                           except Exception:  ← 容错
                                               record failure, let LLM retry
                                           context.history.append(result)
```

**新增数据结构:**
- `NextAction` — 每步 LLM 决策结果（done/tool/params/description/reasoning）
- `StepResult` — 已完成步骤记录
- `LoopContext` — 循环上下文（task + history + memories）

**审批机制:**
- `asyncio.Event` 阻塞等待
- CLI 层 `click.prompt` → `event.set()` → Loop 继续
- 用户拒绝 → 记录失败历史 → 下一轮 LLM 重新规划

**重复检测:**
- 连续 3 步相同 (tool, description) → 强制完成

**验证:**
- `pytest tests/ -v` → 15 passed ✅
- `minicode "解析架构"` → LLM 每步重评估，5 步合理结束 ✅

---

### Phase 1.5 — 基础设施修复

**修复的审计问题:** #7（LLM 错误被吞）、#12（HTTP 资源泄漏）

| # | 文件 | 改动 |
|---|------|------|
| #7 | `llm/client.py` | 新增 `LLMError` 异常类。`chat()`/`chat_stream()` 所有错误路径改为 `raise LLMError` |
| #7 | `agent/planner.py` | `LLMPlanner.next_step()` 和 `plan()` 捕获 `LLMError` → fallback |
| #12 | `llm/client.py` | `MockLLMClient` 添加 `close()` |
| #12 | `agent/loop.py` | 新增 `close()` → 调 `llm.close()` |
| #12 | `main.py` | `try/finally` 确保退出时 `loop.close()` |

---

### Phase 1.6 — 真实 Tool 实现（P0 + P1 完成）

**目标:** 替换 Mock Tool，实现真实文件系统操作。每个 Tool 先写测试再实现。

**新增文件:**

| 文件 | 说明 |
|------|------|
| `tool/registry.py` | `ToolRegistry`（注册/查找）+ `ToolExecutor`（分发/容错/历史） |
| `tool/file.py` | `ReadFile`（带行号+offset/limit）+ `WriteFile` + `EditFile`（SEARCH/REPLACE） |
| `tool/search.py` | `Grep`（Python re + glob）+ `SearchFile` + `ListDirectory` |
| `tool/command.py` | `RunCommand`（asyncio subprocess + 超时 + 输出截断） |
| `tests/tool/conftest.py` | `tmp_dir` + `tmp_file` fixture（独立临时目录） |
| `tests/tool/test_registry.py` | 11 条（注册/查找/分发/容错/历史） |
| `tests/tool/test_read_file.py` | 6 条（完整读取/分段/行号/元数据/错误路径） |
| `tests/tool/test_grep.py` | 7 条（匹配/无匹配/glob过滤/行号/非法正则/跨行） |
| `tests/tool/test_edit_file.py` | 8 条（替换/未找到/多次匹配/多行/保留其他内容） |
| `tests/tool/test_list_directory.py` | 8 条（列出/空目录/隐藏文件排除/SearchFile） |
| `tests/tool/test_run_command.py` | 7 条（echo/ls/命令不存在/非零退出/截断） |

**修改文件:**

| 文件 | 改动 |
|------|------|
| `main.py` | `_build_loop()` 改用 `ToolExecutor` + 7 个真实 Tool，不再使用 `MockToolExecutor` |

**已完成 Tool:**

| Tool | 优先级 | 测试数 | 特性 |
|------|--------|--------|------|
| `ReadFile` | P0 | 6 | 带行号输出、offset/limit、不存在/目录错误处理 |
| `Grep` | P0 | 7 | Python re、glob 过滤、50 匹配上限、二进制跳过 |
| `EditFile` | P0 | 8 | SEARCH/REPLACE、唯一性校验、多行替换 |
| `WriteFile` | P0 | - | 覆盖写入、自动创建父目录 |
| `ListDirectory` | P1 | 6 | 目录树、隐藏文件排除、100 项上限 |
| `RunCommand` | P1 | 7 | asyncio subprocess、30s 超时、3KB 截断 |
| `SearchFile` | P2 | 2 | 文件名 glob、__pycache__ 排除 |

**待实现（P2）:**

| Tool | 说明 |
|------|------|
| `GitStatus` / `GitDiff` / `GitLog` | Git 操作（依赖 git 命令） |
| `RunTest` | 运行测试套件 |

**测试总计:** 15（旧 loop）+ 47（新 tool）= **62 条全部通过**

---

## 2. 当前项目结构

```
minicode/
├── pyproject.toml
├── README.md
├── spec.md                  # 21 章设计规约（唯一真相源）
├── .gitignore
├── PROGRESS.md              # 本文件
│
├── src/minicode/
│   ├── __init__.py          # v0.1.0
│   ├── events.py            # AgentEvent 7 种类型 + EVENT_ICONS
│   ├── main.py              # CLI 入口: Banner + REPL + Event Consumer
│   ├── agent/
│   │   ├── loop.py          # Query Loop: while + asyncio.Event + try/except
│   │   └── planner.py       # KeywordPlanner + LLMPlanner + NextAction/LoopContext
│   ├── tool/
│   │   ├── base.py          # Tool ABC + ToolResult + RiskLevel
│   │   ├── registry.py      # ToolRegistry + ToolExecutor
│   │   ├── file.py           # ReadFile + WriteFile + EditFile
│   │   ├── search.py         # Grep + SearchFile + ListDirectory
│   │   ├── command.py        # RunCommand
│   │   └── mock.py           # MockToolExecutor（测试保留）
│   ├── skill/registry.py    # MockSkillRegistry (5 种 skill)
│   ├── llm/
│   │   └── client.py        # LLMError + DeepSeekLLMClient + MockLLMClient
│   ├── memory/store.py      # MockMemoryStore
│   ├── context/builder.py   # MockContextBuilder
│   └── security/classifier.py  # MockSecurityClassifier
│
└── tests/
    ├── conftest.py           # mock_loop + mock_tool_executor + mock_memory_store
    ├── test_loop.py          # 15 条（事件类型/顺序/元数据/边界/中断）
    └── tool/
        ├── __init__.py
        ├── conftest.py       # tmp_dir + tmp_file fixture
        ├── test_registry.py  # 11 条
        ├── test_read_file.py # 6 条
        ├── test_grep.py      # 7 条
        ├── test_edit_file.py # 8 条
        ├── test_list_directory.py  # 8 条（含 SearchFile）
        └── test_run_command.py     # 7 条
```

---

### Phase 1.6 (追加) — Synthesize：任务结束合成总结

**问题:** Agent 执行完后只显示"任务完成 · N 步 · M Tool"，用户看不到任何结论。

**修复:** 在 while 循环结束后、done 事件之前，新增 `planner.synthesize(context)` 步骤：
- `KeywordPlanner.synthesize()` — 模板化摘要（Markdown 格式）
- `LLMPlanner.synthesize()` — LLM 调用合成（带 fallback）
- done 事件的 `detail["summary"]` 携带总结文本
- CLI 层 done 事件渲染时打印 summary

**改动文件:** `agent/planner.py`（+50 行）、`agent/loop.py`（+10 行）、`main.py`（`_safe_echo` 包装 + done 渲染）

---

## 2. 当前项目结构

```
minicode/
├── pyproject.toml
├── README.md
├── spec.md                  # 21 章设计规约（唯一真相源）
├── .gitignore
├── PROGRESS.md              # 本文件
│
├── src/minicode/
│   ├── __init__.py          # v0.1.0
│   ├── events.py            # AgentEvent 7 种类型 + EVENT_ICONS
│   ├── main.py              # CLI 入口: Banner + REPL + Event Consumer + _safe_echo
│   ├── agent/
│   │   ├── loop.py          # Query Loop: while + asyncio.Event + try/except + synthesize
│   │   └── planner.py       # KeywordPlanner + LLMPlanner + synthesize + NextAction/LoopContext
│   ├── tool/
│   │   ├── base.py          # Tool ABC + ToolResult + RiskLevel
│   │   ├── registry.py      # ToolRegistry + ToolExecutor
│   │   ├── file.py          # ReadFile + WriteFile + EditFile
│   │   ├── search.py        # Grep + SearchFile + ListDirectory
│   │   ├── command.py       # RunCommand
│   │   └── mock.py          # MockToolExecutor（测试保留）
│   ├── skill/registry.py    # MockSkillRegistry (5 种 skill)
│   ├── llm/
│   │   └── client.py        # LLMError + DeepSeekLLMClient + MockLLMClient
│   ├── memory/store.py      # MockMemoryStore
│   ├── context/builder.py   # MockContextBuilder
│   └── security/classifier.py  # MockSecurityClassifier
│
└── tests/
    ├── conftest.py          # mock_loop + mock_tool_executor + mock_memory_store
    ├── test_loop.py         # 15 条（事件类型/顺序/元数据/边界/中断）
    └── tool/
        ├── conftest.py      # tmp_dir + tmp_file fixture
        ├── test_registry.py # 11 条
        ├── test_read_file.py     # 6 条
        ├── test_grep.py          # 7 条
        ├── test_edit_file.py     # 8 条
        ├── test_list_directory.py # 8 条（含 SearchFile）
        └── test_run_command.py   # 7 条
```

---

## 3. 审计问题状态

**来源：** 首次审计，共发现 13 个设计问题

### 已修复 (7/13)

| # | 问题 | 修复阶段 |
|---|------|---------|
| 1 | Query Loop 不是 Loop | Phase 1 重构 |
| 4 | Security 审批不阻塞 | Phase 1 重构 |
| 8 | 执行循环零容错 | Phase 1 重构 |
| 7 | LLM 异常被吞成正常响应 | Phase 1.5 |
| 12 | HTTP Client 资源泄漏 | Phase 1.5 |
| 3-lite | 任务结束无总结（Reflection 缺失） | Phase 1.6 追加 |
| 11 | KeywordPlanner 硬编码具体文件路径 | Phase 1 重构 |

### 未修复 (6/13)

| # | 问题 | 优先级 | 计划 |
|---|------|--------|------|
| 5 | ContextBuilder 未被调用 | P1 | Phase 2 |
| 4-skill | Skill 选了没用（tool_allowlist 未注入） | P1 | Phase 3 |
| 6 | Planner 和 SkillRegistry 关键词重复 | P1 | Phase 3 |
| 9 | run_all() 测试方法在生产代码里 | P2 | Phase 3 |
| 10 | 缺少 Planner/Skill/Security 单元测试 | P2 | Phase 3 |
| 13 | REASONIX.md 与 spec.md 矛盾 | P3 | Phase 5 |

---

## 4. 剩余任务计划

### Phase 2 — ContextBuilder 接入 + 真实 Memory（优先级 P1）

**目标:** 让 LLM 收到的 system prompt 由 ContextBuilder 动态构建，而非 Planner 内部硬编码。

| # | 任务 | 测试文件 | 说明 |
|---|------|---------|------|
| 2.1 | 实现 `ContextBuilder.build()` | `tests/context/test_builder.py` | Jinja2 模板：注入 task、memories、skill_prompt、history_summary、available_tools |
| 2.2 | loop.py 在每轮调用 `context_builder.build()` | - | 替换内联的 memory.search() |
| 2.3 | MemoryStore 接入 SQLite + sqlite-vec | `tests/memory/test_store.py` | 替换 MockMemoryStore，真实语义检索 |
| 2.4 | Reflection 分级触发 | `tests/agent/test_reflection.py` | <3 步跳过、≥3 步轻量反思、失败深度反思 |

**产出:** LLM 看到动态构建的上下文，Memory 真正语义检索而非返回最近 N 条。

---

### Phase 3 — Skill 注入 + 去重 + 清理（优先级 P1）

**目标:** Skill 选出来后真正影响执行（约束 tool_allowlist + 注入 system_prompt），消除 Planner/Skill 关键词重复。

| # | 任务 | 测试文件 | 说明 |
|---|------|---------|------|
| 3.1 | Skill 的 `system_prompt` 注入 LLM context | `tests/skill/test_registry.py` | 选中 skill 后，其 prompt 进入 ContextBuilder |
| 3.2 | Skill 的 `tool_allowlist` 约束执行 | `tests/skill/test_registry.py` | Planner 只能选择 allowlist 内的 tool |
| 3.3 | 统一关键词匹配逻辑 | - | Planner 和 SkillRegistry 共用一套分类器 |
| 3.4 | 移动 `run_all()` 到 test 工具 | - | 从 loop.py 删掉，tests/conftest.py 加 helper |
| 3.5 | 补齐 Planner/Skill/Security 单元测试 | `tests/agent/`、`tests/skill/`、`tests/security/` | 覆盖边界：LLMError fallback、空 skill list、风险分级 |

**产出:** Skill 不再是装饰性标签，Agent 行为受 Skill 约束。

---

### Phase 4 — P2 Tool 补齐（优先级 P2）

**目标:** 补充 Git 操作和测试运行工具。

| # | 任务 | 测试文件 | 说明 |
|---|------|---------|------|
| 4.1 | `GitStatus` + `GitDiff` + `GitLog` | `tests/tool/test_git.py` | 包装 git CLI 命令 |
| 4.2 | `RunTest` | `tests/tool/test_run_test.py` | 运行 pytest/unittest 并解析结果 |

---

### Phase 5 — 文档清理 + 收尾（优先级 P3）

| # | 任务 | 说明 |
|---|------|------|
| 5.1 | 删除或归档 REASONIX.md | 与 spec.md 矛盾，保留 spec.md 为唯一真相源 |
| 5.2 | SecurityClassifier 真实实现 | 启用命令黑名单 + 注入检测 |
| 5.3 | 更新 spec.md 反映实际实现差异 | 同步当前架构状态 |

---

### 优先级汇总

| 优先级 | Phase | 预计工作量 | 核心价值 |
|--------|-------|-----------|---------|
| P1 | Phase 2 | ContextBuilder + 真实 Memory | LLM 上下文动态构建，记忆语义检索 |
| P1 | Phase 3 | Skill 注入 + 去重 + 单元测试 | Skill 真正生效，代码质量 |
| P2 | Phase 4 | Git + RunTest Tool | 工具完备性 |
| P3 | Phase 5 | 文档 + Security | 文档一致，安全增强 |

---

## 5. 关键设计决策记录

| 决策 | 时间 | 理由 |
|------|------|------|
| 不用 LangGraph | Phase 0 | Agent 拓扑是 while 循环，不是 DAG |
| Skill = Prompt，不是 Code | Phase 0 | 灵活、可版本管理、LLM 原生 |
| SQLite + sqlite-vec 而非 ChromaDB | Phase 0 | 零额外进程，单机够用 |
| V1 不做 Docker Sandbox | Phase 0 | Security Layer 4 级审批已足够 |
| 先修基础设施再拆 Mock | Phase 1.5 | LLM 异常传播在真实 Tool 之前修 |
| 先拆 Mock Tool 再做 Reflection | Phase 1.6 计划 | Reflection 需要真实数据 |
| 环境变量名 `deepseek` | Phase 1 | 用户本机配置 |
| 审批用 asyncio.Event 阻塞 | Phase 1 重构 | 而非 yield 后无视 |
| while 循环每步 LLM 重评估 | Phase 1 重构 | 而非一次性规划全部步骤 |
| 真实 Tool 默认启用，Mock 仅测试 | Phase 1.6 | Tool 不依赖 LLM API，离线可用 |
| Grep 用 Python re 不依赖 ripgrep | Phase 1.6 | 零外部依赖，安装更简单 |
