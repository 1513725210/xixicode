"""TUI — Rich Live 持久状态面板。

参考 MiniCode tui/* 的状态化渲染设计：
- LiveDisplay: Rich Live 持久面板 + 彩色事件渲染
- 面板显示：步骤数 / Tool 数 / LLM 调用 / Token / 当前状态
- 颜色映射：thinking=cyan, tool_call=yellow, tool_result=green/red,
            done=bold green, need_approval=red, error=red

默认模式（无 --verbose）：流式事件 + 底部状态栏
--verbose 模式：完整 Rich Panel 持久状态
--quiet 模式：仅最终结果
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field

from rich.console import Console, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.layout import Layout
from rich import box

from minicode.events import AgentEvent

# ── 颜色常量 ──

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


# ── 状态追踪 ──


@dataclass
class LiveStatus:
    """Live 面板显示的运行时状态。"""

    step: int = 0
    tools: int = 0
    llm_calls: int = 0
    tokens_prompt: int = 0
    tokens_completion: int = 0
    current_action: str = ""
    last_result: str = ""
    last_result_ok: bool = True
    skill: str = ""
    events: list[str] = field(default_factory=list)  # 最近事件日志

    def update_from_event(self, event: AgentEvent) -> None:
        """从 AgentEvent 更新状态。"""
        detail = event.detail or {}

        if event.type == "done":
            self.step = detail.get("steps", self.step)
            self.tools = detail.get("tools", self.tools)
        elif event.type == "tool_call":
            self.current_action = event.message[:80]
        elif event.type == "tool_result":
            self.last_result = event.message[:120]
            self.last_result_ok = detail.get("success", True)
        elif event.type == "thinking":
            if detail.get("tokens_prompt"):
                self.tokens_prompt = detail["tokens_prompt"]
                self.tokens_completion = detail.get("tokens_completion", 0)
                self.llm_calls = detail.get("llm_calls", 0)

        # 事件日志（最近 8 条）
        icon = ICONS.get(event.type, " ")
        self.events.append(f"{icon} {event.message[:80]}")
        if len(self.events) > 8:
            self.events = self.events[-8:]


# ── 渲染函数 ──


def _build_status_panel(status: LiveStatus, model_display: str = "") -> RenderableType:
    """构建 Rich 可渲染的持久状态面板。

    Args:
        status: 当前运行时状态
        model_display: 模型显示名称

    Returns:
        Rich Panel
    """
    # 顶部状态行
    header = Text()
    header.append("MiniCode", style="bold cyan")
    if model_display:
        header.append(f"  [{model_display}]", style="dim")
    header.append(f"  步 {status.step}", style="yellow")
    header.append(f"  Tool {status.tools}", style="yellow")
    if status.llm_calls > 0:
        header.append(f"  LLM {status.llm_calls}", style="dim")
        header.append(
            f"  {status.tokens_prompt}+{status.tokens_completion} tok",
            style="dim",
        )

    # 当前操作
    if status.current_action:
        header.append(f"\n  {status.current_action}", style="bold")

    # 最近事件日志
    if status.events:
        event_text = Text()
        for e in status.events[-6:]:
            event_text.append(f"  {e}\n", style="dim")
        header.append("\n")
        header.append(event_text)

    return Panel(
        header,
        title="[bold cyan]MiniCode[/]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(0, 1),
    )


def _render_event_rich(event: AgentEvent) -> RenderableType:
    """将 AgentEvent 渲染为 Rich 可渲染对象。

    Args:
        event: AgentEvent 实例

    Returns:
        Rich Text/Panel
    """
    icon = ICONS.get(event.type, " ")
    detail = event.detail or {}

    if event.type == "need_approval":
        # 审批事件 — 特殊渲染
        lines = [
            f"  {icon} High Risk Action",
            f"  Tool:  {detail.get('tool', '?')}",
            f"  Risk:  {detail.get('risk', '?')}",
        ]
        if detail.get("description"):
            lines.append(f"  Desc:  {detail.get('description')}")
        return Text("\n".join(lines), style=COLORS["need_approval"])

    elif event.type == "done":
        text = Text()
        text.append(f"\n  {icon} {event.message}", style=COLORS["done"])
        summary = detail.get("summary", "")
        if summary:
            text.append(f"\n\n{summary[:500]}", style="cyan")
        return text

    elif event.type == "assistant":
        return Text(f"  {event.message[:300]}", style=COLORS["assistant"])

    elif event.type == "thinking":
        reasoning = detail.get("reasoning", "")
        text = Text(f"  {icon} {event.message}", style=COLORS["thinking"])
        if reasoning and len(reasoning) < 200:
            text.append(f"  | {reasoning[:150]}", style="dim")
        return text

    elif event.type == "tool_result":
        ok = detail.get("success", True)
        color = COLORS["tool_result_ok"] if ok else COLORS["tool_result_err"]
        result_icon = ICONS["tool_result_ok"] if ok else ICONS["tool_result_err"]
        output = event.message[:200]
        return Text(f"  {result_icon} {output}", style=color)

    else:
        color = COLORS.get(event.type, "white")
        return Text(f"  {icon} {event.message}", style=color)


# ── LiveDisplay ──


class LiveDisplay:
    """Rich Live 持久显示管理器。

    Usage:
        display = LiveDisplay(model="deepseek-chat", verbose=False)
        with display:
            display.render(event1)
            display.render(event2)
            ...
    """

    def __init__(
        self,
        model: str = "",
        verbose: bool = False,
        quiet: bool = False,
    ):
        self._model = model
        self._verbose = verbose
        self._quiet = quiet
        self._status = LiveStatus()
        self._console = Console()
        self._live: Live | None = None

    def __enter__(self) -> "LiveDisplay":
        if self._quiet:
            self._live = None
            return self

        # verbose 模式：全屏面板
        # 默认模式：紧凑状态栏
        panel = _build_status_panel(self._status, self._model)
        self._live = Live(
            panel,
            console=self._console,
            refresh_per_second=4,
            vertical_overflow="visible",
        )
        self._live.__enter__()
        return self

    def __exit__(self, *args) -> None:
        if self._live:
            self._live.__exit__(*args)
        self._live = None

    def render(self, event: AgentEvent) -> None:
        """渲染一个 AgentEvent。

        - quiet 模式：仅输出 done 事件
        - 默认模式：流式输出事件行 + 更新状态面板
        - verbose 模式：完整面板实时更新
        """
        self._status.update_from_event(event)

        if self._quiet:
            if event.type == "done":
                self._console.print(f"[{COLORS['done']}]{event.message}[/]")
            return

        if self._verbose:
            # 完整面板模式
            panel = _build_status_panel(self._status, self._model)
            rich_event = _render_event_rich(event)
            layout = Layout()
            layout.split_column(
                Layout(rich_event, size=3),
                Layout(panel),
            )
            if self._live:
                self._live.update(layout)
            else:
                self._console.print(rich_event)
        else:
            # 默认模式：流式输出 + 底部状态
            rich_event = _render_event_rich(event)
            if event.type in ("done", "assistant", "need_approval"):
                # 重要事件：直接输出
                self._console.print(rich_event)
            elif event.type not in ("thinking", "progress"):
                # 操作事件：输出 + 更新面板
                self._console.print(rich_event)

            # 更新 Live 面板
            if self._live:
                panel = _build_status_panel(self._status, self._model)
                self._live.update(panel)

    def print(self, text: str = "") -> None:
        """输出纯文本（用于 banner、元命令结果等）。"""
        if self._quiet:
            return
        self._console.print(text)

    def input(self, prompt: str = "> ") -> str:
        """获取用户输入。"""
        if sys.stdin.isatty():
            return input(prompt).strip()
        return ""

    def show_banner(self, banner_text: str) -> None:
        """显示 Banner。"""
        if not self._quiet:
            self._console.print(banner_text, style="bold cyan")
