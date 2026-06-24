# MiniCode — Unfinished Features

对比 MiniCode/Claude Code 14 个核心设计模式，当前 V1 状态。

> 最后更新: 2026-06-24
> 对照: MiniCode (TypeScript) + spec.md

---

## ✅ DONE (5/14)

| # | 模式 | 关键文件 | 状态 |
|---|------|---------|------|
| 1 | Agent Loop | `agent/loop.py` — while True + per-step LLM re-evaluation | ✅ |
| 3 | Tool Use Protocol | `tool/base.py`, `tool/registry.py` — 17 tools, unified Tool ABC | ✅ |
| 4 | Progress vs Final | `events.py` — distinct `progress`, `done`, `reflection` types | ✅ |
| 5 | Permissions & Approval | `security/` — 4-level pipeline + approval with timeout | ✅ |
| 10 | Session/Fork/Recovery | `session.py` — JSONL append-only, compact boundary, fork | ✅ |

---

## 🔧 PARTIAL — 代码已写但未集成 (5/14)

| # | 模式 | 已有什么 | 缺什么 |
|---|------|---------|--------|
| 7 | Skills as Workflows | `skill/loader.py` — YAML 加载；`skill/registry.py` — 关键词选择 | `skill/router.py` 的 LLM SkillRouter 从未被实例化；loop.py 只用关键词选择 |
| 8 | Auto Context Compaction | `context/compressor.py` — L1/L2/L3 完整实现 | **loop.py 从未调用 compressor**；无自动触发阈值检查 |
| 9 | Provider Usage | `LLMResponse` 有 `prompt_tokens`/`completion_tokens` | **无人读取**；loop.py 无 token 积累；压缩决策不基于真实 usage |
| 11 | Large Tool Results | `RunCommand.MAX_OUTPUT=3000` 等硬截断 | **无 "preview+path" 替换模式**；截断 = 数据丢失 |
| 13 | Background Tasks | `BackgroundTask` dataclass 存在 | **从未被创建**；RunCommand 总是同步等待 |

---

## 🏗 PARTIAL — 需要新代码 (3/14)

| # | 模式 | 已有什么 | 缺什么 |
|---|------|---------|--------|
| 2 | Structured Messages | 7 种 EventType | 缺 `user`、`assistant`、`summary` 类型；loop 中未包装 |
| 12 | TUI State Machine | 线性 `click.echo()` 渲染 | 无 Rich Live 持久面板；无 diff preview 审批 |
| 14 | Scope Boundary | `spec.md` 有 MVP scope + roadmap | `REASONIX.md` 与 `spec.md` 矛盾（PROGRESS.md #13） |

---

## ✅ 现已完成

| # | 模式 | 关键文件 |
|---|------|---------|
| 6 | MCP Dynamic Capability | `mcp/client.py` — stdio JSON-RPC；`mcp/tools.py` — 动态工具包装；`~/.minicode/mcp.json` 配置 |

---

## 📋 实施路线图

### Phase 1 — 集成已有代码（最快见效）
- [x] 1.0 写入 unfinish.md 跟踪文件
- [x] 1.1 `loop.py` 调用 `detect_injection()` — 接入 Security Layer 2
- [x] 1.2 `main.py` 创建 `SkillRouter(llm)` 替代 keyword 选择
- [x] 1.3 `loop.py` 调用 `compress_context()` — 自动压缩触发
- [x] 1.4 `planner.py` 积累 `prompt_tokens`/`completion_tokens`，传给 loop.py
- [x] 1.5 `loop.py` 调用 `save_event()` + CLI 增加 `/resume`

### Phase 2 — 完善 PARTIAL 功能
- [x] 2.1 events.py 增加 `user`/`assistant`/`summary` 类型
- [x] 2.2 `tool/storage.py` — 大结果 preview+path 替换
- [x] 2.3 TUI 升级 — Rich Live 持久面板
- [x] 2.4 `tool/background.py` — 后台任务注册表
- [x] 2.5 修复 REASONIX.md 与 spec.md 的矛盾

### Phase 3 — MCP 动态能力
- [x] 3.1 `mcp/client.py` — stdio JSON-RPC 通信
- [x] 3.2 `mcp/tools.py` — 动态工具包装
- [x] 3.3 `~/.minicode/mcp.json` 配置 + 集成到 _build_loop

### Phase 4 — Skills 管理
- [ ] 4.1 Skill install/remove CLI 命令
- [ ] 4.2 SkillRegistry.reload() 热加载
