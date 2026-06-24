# MiniCode Project Memory

> Project memory loaded as system prefix. Keep terse.

## Key Facts

- **Project**: MiniCode — AI Coding Agent for local repositories
- **Language**: Python 3.11+
- **Entry**: `minicode` CLI (Click) → `main.py`
- **Core**: Query Loop (`agent/loop.py`) — while-true with per-step LLM re-evaluation
- **Architecture**: Agent → Skill → Tool pipeline
- **Design spec**: [spec.md](./spec.md) — single source of truth for architecture

## Current State

- V1.0 — 17 tools, 151 tests passing
- LLM: DeepSeek API (OpenAI-compatible), with Mock offline fallback
- Memory: File-based (Markdown+YAML frontmatter) in `~/.minicode/memory/`
- Session: JSONL append-only in `~/.minicode/projects/`
- Config: Multi-source YAML merge

## Tech Stack

| Component | Choice | Reason |
|-----------|--------|--------|
| Agent Loop | asyncio + while | Loop is a loop, not a graph |
| LLM SDK | httpx + OpenAI-compatible API | DeepSeek/Claude both support this |
| CLI | Click + Rich | Terminal UI + params |
| Template | Jinja2 | Skill/Memory injection |
| Testing | pytest + pytest-asyncio | Standard async testing |
| Config | YAML | User-editable, layered (default → user → project) |

## Key Design Principles

1. Agent First — User → Agent → Tool, never User → Tool
2. Memory Driven — Results become memory assets
3. Skill Oriented — Agent learns Skills, Skills compose Tools
4. Safe Execution — High-risk ops require approval

## See Also

- [spec.md](./spec.md) — Full V1 design specification
- [unfinish.md](./unfinish.md) — Unfinished features tracker
- [PROGRESS.md](./PROGRESS.md) — Development progress log
