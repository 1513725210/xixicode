"""TUI — Rich 终端渲染。

参考 MiniCode tui/* 的状态化渲染设计：
- Rich 彩色事件输出（thinking=cyan, tool_call=yellow, done=bold green）
- --verbose 模式：Live Panel 持久状态（步数/Tool/Token）
- --quiet 模式：仅最终结果

设计约束：
- 不使用裸 ANSI 转义序列（与 Rich 冲突）
- 不使用 click.prompt 阻塞事件循环（用 Rich console.input）
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich import box

from minicode.events import AgentEvent

# ── 颜色 ──

COLORS = {
    "user":           "bold white",
    "thinking":       "cyan",
    "tool_call":      "yellow",
    "tool_result_ok":  "green",
    "tool_result_err": "red",
    "progress":       "dim cyan",
    "assistant":      "bold cyan",
    "summary":        "blue",
    "need_approval":  "bold red",
    "reflection":     "magenta",
    "done":           "bold green",
}

ICONS = {
    "user":           ">",
    "thinking":       "~",
    "tool_call":      ">",
    "tool_result_ok":  "+",
    "tool_result_err": "x",
    "progress":       ".",
    "assistant":      "A",
    "summary":        "S",
    "need_approval":  "!",
    "reflection":     "*",
    "done":           "+",
}


# ── 状态 ──


@dataclass
class LiveStatus:
    """面板显示的运行时状态。"""
    step: int = 0
    tools: int = 0
    llm_calls: int = 0
    tokens_prompt: int = 0
    tokens_completion: int = 0
    current_action: str = ""
    last_result: str = ""
    last_result_ok: bool = True

    def update(self, event: AgentEvent) -> None:
        d = event.detail or {}
        if event.type == "done":
            self.step = d.get("steps", self.step)
            self.tools = d.get("tools", self.tools)
        elif event.type == "tool_call":
            self.current_action = event.message[:80]
        elif event.type == "tool_result":
            self.last_result = event.message[:120]
            self.last_result_ok = d.get("success", True)
        elif event.type == "thinking":
            if d.get("tokens_prompt"):
                self.tokens_prompt = d["tokens_prompt"]
                self.tokens_completion = d.get("tokens_completion", 0)
                self.llm_calls = d.get("llm_calls", 0)


def _render_panel(status: LiveStatus, model: str = "") -> Panel:
    """构建状态面板。"""
    title = Text("MiniCode", style="bold cyan")
    if model:
        title.append(f"  [{model}]", style="dim")
    title.append(f"  步 {status.step}  Tool {status.tools}", style="yellow")
    if status.llm_calls:
        title.append(
            f"  LLM {status.llm_calls}  {status.tokens_prompt}+{status.tokens_completion} tok",
            style="dim",
        )
    body = Text()
    if status.current_action:
        body.append(status.current_action, style="bold")
    if status.last_result:
        icon = ICONS["tool_result_ok"] if status.last_result_ok else ICONS["tool_result_err"]
        color = COLORS["tool_result_ok"] if status.last_result_ok else COLORS["tool_result_err"]
        body.append(f"\n  {icon} {status.last_result[:120]}", style=color)
    return Panel(body, title=title, border_style="cyan", box=box.ROUNDED, padding=(0, 1))


def _render_event(event: AgentEvent) -> Text:
    """彩色事件渲染。"""
    icon = ICONS.get(event.type, " ")
    d = event.detail or {}

    if event.type == "done":
        t = Text(f"\n  {icon} {event.message}\n", style=COLORS["done"])
        if d.get("summary"):
            t.append(d["summary"][:500], style="cyan")
        return t
    elif event.type == "assistant":
        return Text(f"  {event.message[:300]}", style=COLORS["assistant"])
    elif event.type == "thinking":
        t = Text(f"  {icon} {event.message}", style=COLORS["thinking"])
        r = d.get("reasoning", "")
        if r and len(r) < 200:
            t.append(f"  | {r[:150]}", style="dim")
        return t
    elif event.type == "tool_result":
        ok = d.get("success", True)
        c = COLORS["tool_result_ok"] if ok else COLORS["tool_result_err"]
        ri = ICONS["tool_result_ok"] if ok else ICONS["tool_result_err"]
        return Text(f"  {ri} {event.message[:200]}", style=c)
    elif event.type == "need_approval":
        return Text(
            f"\n  {icon} High Risk: {d.get('tool','?')} [{d.get('risk','?')}]\n"
            f"  {d.get('description','')}",
            style=COLORS["need_approval"],
        )
    else:
        c = COLORS.get(event.type, "white")
        return Text(f"  {icon} {event.message}", style=c)


# ── LiveDisplay ──


class LiveDisplay:
    """Rich 终端显示管理器。

    三种模式:
    - quiet: 仅输出 done
    - verbose: Live Panel 持久面板
    - 默认: 彩色流式输出
    """

    def __init__(self, model: str = "", verbose: bool = False, quiet: bool = False):
        self._model = model
        self._verbose = verbose
        self._quiet = quiet
        self._status = LiveStatus()
        self._console = Console(highlight=False)
        self._live: Live | None = None

    def __enter__(self) -> "LiveDisplay":
        if self._verbose and not self._quiet:
            self._live = Live(
                _render_panel(self._status, self._model),
                console=self._console,
                refresh_per_second=2,
                transient=False,
            )
            self._live.__enter__()
        return self

    def __exit__(self, *args) -> None:
        if self._live:
            self._live.__exit__(*args)
            self._live = None

    def render(self, event: AgentEvent) -> None:
        """渲染事件。"""
        self._status.update(event)

        if self._quiet:
            if event.type == "done":
                self._console.print(_render_event(event))
            return

        rich_event = _render_event(event)

        if self._verbose:
            self._live.update(_render_panel(self._status, self._model))
            # 对重要事件额外输出
            if event.type in ("done", "need_approval", "assistant"):
                self._console.print(rich_event)
        elif event.type not in ("thinking", "progress"):
            self._console.print(rich_event)

    def print(self, text: str = "") -> None:
        """输出纯文本。"""
        if not self._quiet:
            self._console.print(text)

    def prompt(self, prompt_text: str = "> ") -> str:
        """获取用户输入（非阻塞）。"""
        if self._verbose and self._live:
            self._live.stop()
        try:
            self._console.print(prompt_text, end="")
            return sys.stdin.readline().strip()
        finally:
            if self._verbose and self._live:
                self._live.start()

    def show_banner(self, banner: str) -> None:
        """显示 Banner。"""
        if not self._quiet:
            self._console.print(banner)
