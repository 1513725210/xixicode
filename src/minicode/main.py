"""MiniCode CLI 入口。

用法:
    minicode                  # REPL 交互模式
    minicode "修复 NPE"        # One-shot 单任务模式
    minicode --task task.md   # 从文件读取任务

架构:
    User → CLI (main.py) → Agent (loop.py) → Event Stream → CLI 渲染
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import click

from minicode import __version__
from minicode.events import AgentEvent
from minicode.agent.loop import QueryLoop
from minicode.agent.planner import KeywordPlanner, LLMPlanner
from minicode.tool.mock import MockToolExecutor
from minicode.tool.registry import ToolRegistry, ToolExecutor
from minicode.tool.file import ReadFile, WriteFile, EditFile
from minicode.tool.search import Grep, SearchFile, ListDirectory
from minicode.tool.command import RunCommand
from minicode.tool.git import GitStatus, GitDiff, GitLog, GitShow
from minicode.tool.test import RunTest
from minicode.tool.patch import PatchFile, ModifyFile
from minicode.tool.web import WebFetch, WebSearch
from minicode.tool.ask import AskUser
from minicode.skill.registry import SkillRegistry
from minicode.llm.client import DeepSeekLLMClient, MockLLMClient
from minicode.memory.store import FileMemoryStore
from minicode.context.builder import ContextBuilder
from minicode.security.classifier import build_default_classifier, MockSecurityClassifier


# ── Banner ──

BANNER = f"""
╭──────────────────────────────────────────────────────────╮
│                                                          │
│     .---.                                                │
│    / - - \\    MiniCode v{__version__}                   │
│    |  ^  |    仓库  {{repo}}                             │ 
│    | \\_/ |    模型  {{model}}                           │
│     \\___/     分支  {{branch}}   文件  {{files}} 个      │
│                                                          │
│   输入任务开始，或 /help 查看帮助                          │
│                                                          │
╰──────────────────────────────────────────────────────────╯"""

# ── Loading Animation ──

_LOADING_LOGO = [
    "",
    "        _.-\"\"\"-._          ",
    "      .'         '.        ",
    "     /   -     -   \\       ",
    "    |       ^       |       ",
    "    |     \\___/     |       ",
    "     \\             /        ",
    "      '.         .'        ",
    "        `-...--'`          ",
]

_LOADING_SPINNERS = ["-", "\\", "|", "/"]


def _enable_ansi_on_windows():
    """Windows 10+ 启用 ANSI 转义序列支持。"""
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 0x0007)


def show_loading(duration: float = 1.5):
    """显示动态加载动画。

    原理：
    1. 隐藏光标 (ANSI \\033[?25l)
    2. 每帧用 \\033[H 回到屏幕左上角覆盖绘制
    3. 用 \\033[K 清除行尾残留字符
    4. time.sleep() 控制帧率
    5. 结束后清屏、恢复光标 (\\033[?25h)
    """
    _enable_ansi_on_windows()

    HIDE_CURSOR = "\033[?25l"
    SHOW_CURSOR = "\033[?25h"
    CLEAR = "\033[2J\033[H"
    MOVE_HOME = "\033[H"
    CLR_EOL = "\033[K"

    sys.stdout.write(HIDE_CURSOR)
    sys.stdout.flush()

    dots_cycle = [".  ", ".. ", "..."]
    start = time.time()
    idx = 0

    while time.time() - start < duration:
        sys.stdout.write(MOVE_HOME)
        for line in _LOADING_LOGO:
            sys.stdout.write(f"  {line}{CLR_EOL}\n")
        spinner = _LOADING_SPINNERS[idx % len(_LOADING_SPINNERS)]
        dots = dots_cycle[idx % len(dots_cycle)]
        sys.stdout.write(f"\n     MiniCode v{__version__}{CLR_EOL}\n")
        sys.stdout.write(f"\n   {spinner} 加载中{dots}{CLR_EOL}\n")
        sys.stdout.flush()
        idx += 1
        time.sleep(0.2)

    # 清屏并恢复光标
    sys.stdout.write(CLEAR)
    sys.stdout.write(SHOW_CURSOR)
    sys.stdout.flush()


def get_repo_info() -> dict:
    """获取当前仓库信息。"""
    cwd = Path.cwd()
    api_key = os.environ.get("deepseek", "")
    return {
        "repo": str(cwd),
        "model": "deepseek-chat" if api_key else "mock",
        "branch": "main",
        "files": sum(1 for _ in cwd.rglob("*") if _.is_file()),
    }


# ── Event Consumer ──


async def stream_events(task: str, loop: QueryLoop):
    """消费 AgentEvent 流并渲染到终端。

    Args:
        task: 用户任务
        loop: 已初始化的 QueryLoop
    """
    try:
        async for event in loop.run(task):
            _render_event(event)
    except asyncio.CancelledError:
        click.echo("\n  中断")
        click.echo("  [c] 继续等待   [r] 重新规划   [a] 放弃任务")


def _safe_echo(text: str = "", **kwargs):
    """click.echo 的编码安全包装。"""
    try:
        click.echo(text, **kwargs)
    except UnicodeEncodeError:
        # Windows GBK 终端不支持 emoji，降级 ASCII
        safe = text.encode("ascii", errors="replace").decode("ascii")
        click.echo(safe, **kwargs)


def _render_event(event: AgentEvent):
    """将单个 AgentEvent 渲染为一行终端输出。"""
    icon = event.icon
    msg = event.message

    if event.type == "thinking":
        detail = event.detail or {}
        reasoning = detail.get("reasoning", "")
        if reasoning and detail.get("phase") == "plan_complete":
            _safe_echo(f"  {icon} {msg}")
            _safe_echo(f"  [reason] {reasoning}")
        else:
            _safe_echo(f"  {icon} {msg}")
    elif event.type == "tool_result":
        _safe_echo(f"{msg}")
    elif event.type == "need_approval":
        detail = event.detail or {}
        approval_event = detail.get("_approval_event")
        approval_result = detail.get("_approval_result")

        _safe_echo(f"\n  {icon} High Risk Action")
        _safe_echo(f"  Tool:  {detail.get('tool', '?')}")
        _safe_echo(f"  Risk:  {detail.get('risk', '?')}")
        if detail.get("description"):
            _safe_echo(f"  Desc:  {detail.get('description')}")

        if approval_event is not None and approval_result is not None:
            choice = click.prompt("  Approve? [y/n]", type=str, default="n").strip().lower()
            if choice == "y":
                approval_result["approved"] = True
            approval_event.set()
        else:
            _safe_echo("  Approve? [y/n] > y (auto)")
    elif event.type == "done":
        _safe_echo(f"\n  {icon} {msg}")
        detail = event.detail or {}
        summary = detail.get("summary", "")
        if summary:
            _safe_echo(f"\n{summary}")
    elif event.type == "reflection":
        _safe_echo(f"  {icon} {msg}")
    else:
        _safe_echo(f"  {icon} {msg}")


# ── REPL ──


async def repl_loop(loop: QueryLoop):
    """交互式 REPL 循环。

    读取用户输入 → 执行 QueryLoop → 渲染事件 → 回到提示符。
    """
    while True:
        try:
            user_input = click.prompt("", prompt_suffix="> ").strip()
        except (KeyboardInterrupt, EOFError):
            click.echo("\n  再见")
            break

        if not user_input:
            continue

        # 元命令
        if user_input.startswith("/"):
            _handle_meta_command(user_input, loop)
            continue

        # 正常任务
        click.echo()  # 空行分隔
        await stream_events(user_input, loop)
        click.echo()  # 空行后回到提示符


def _handle_meta_command(cmd: str, loop: QueryLoop):
    """处理 / 开头的元命令。"""
    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command in ("/exit", "/quit"):
        click.echo("  再见")
        sys.exit(0)
    elif command == "/help":
        click.echo("""
  元命令:
  /help            帮助
  /skills          列出可用 Skill
  /history         查看 Tool 调用历史
  /memory          列出会话记忆
  /model           查看当前模型
  /clear           清屏
  /exit, /quit     退出
        """)
    elif command == "/skills":
        skills = loop.skill_registry.list_skills()
        click.echo(f"  可用 Skill: {', '.join(skills)}")
    elif command == "/history":
        history = loop.tool_executor.call_history
        if not history:
            click.echo("  暂无 Tool 调用记录")
        else:
            click.echo(f"  Tool 调用记录 ({len(history)} 次):")
            for i, call in enumerate(history, 1):
                click.echo(f"  {i}. {call['tool']} → {call['params']}")
    elif command == "/memory":
        count = loop.memory_store.count
        click.echo(f"  会话记忆: {count} 条")
    elif command == "/model":
        model = getattr(loop, "_model_display", "unknown")
        click.echo(f"  当前模型: {model}")
    elif command == "/clear":
        click.clear()
    else:
        click.echo(f"  未知命令: {command}，输入 /help 查看帮助")


# ── One-shot ──


async def oneshot(task: str, loop: QueryLoop):
    """单任务模式：执行 → 输出 → 退出。"""
    await stream_events(task, loop)
    await loop.close()


# ── Click Entry Point ──


@click.command()
@click.argument("task", required=False)
@click.option("--task-file", type=click.Path(exists=True), help="从文件读取任务")
@click.option("--quiet", "-q", is_flag=True, help="安静模式")
@click.option("--verbose", "-v", is_flag=True, help="详细模式")
@click.option("--yes", "-y", "auto_approve", is_flag=True, help="自动批准")
@click.option("--dry-run", is_flag=True, help="只读模式")
@click.option("--model", help="指定模型")
@click.option("--no-memory", is_flag=True, help="禁用记忆")
@click.version_option(version=__version__)
def main(
    task: str | None,
    task_file: str | None,
    quiet: bool,
    verbose: bool,
    auto_approve: bool,
    dry_run: bool,
    model: str | None,
    no_memory: bool,
):
    """MiniCode — 面向本地代码仓库的 AI Coding Agent."""
    # 从文件读取任务
    if task_file:
        task = Path(task_file).read_text(encoding="utf-8").strip()

    # 构建 QueryLoop（传递 CLI 标志）
    loop, model_display = _build_loop(
        auto_approve=auto_approve,
        dry_run=dry_run,
        no_memory=no_memory,
        model=model,
    )

    # 显示 Banner（安静模式跳过）
    if not quiet:
        show_loading(duration=1.5)
        info = get_repo_info()
        info["model"] = model_display
        try:
            click.echo(BANNER.format(**info))
        except UnicodeEncodeError:
            click.echo(BANNER.format(**info)
                       .encode("ascii", errors="replace").decode("ascii"))

    # 单一事件循环执行
    try:
        if task:
            asyncio.run(oneshot(task, loop))
        else:
            try:
                asyncio.run(repl_loop(loop))
            except KeyboardInterrupt:
                click.echo("\n  再见")
    finally:
        try:
            asyncio.run(loop.close())
        except Exception:
            pass


def _build_loop(
    auto_approve: bool = False,
    dry_run: bool = False,
    no_memory: bool = False,
    model: str | None = None,
) -> tuple[QueryLoop, str]:
    """构建 QueryLoop，自动选择真实或 Mock 后端。

    环境变量 `deepseek` 存在 → LLMPlanner（不做启动验证，LLM 失败由 planner 降级处理）
    不存在 → MockLLMClient + KeywordPlanner

    Returns:
        (QueryLoop, model_display_name)
    """
    api_key = os.environ.get("deepseek", "")

    if api_key:
        llm = DeepSeekLLMClient(api_key=api_key)
        planner = LLMPlanner(llm)
        model_display = model or "deepseek-chat"
    else:
        llm = MockLLMClient()
        planner = KeywordPlanner()
        model_display = "mock (V1 skeleton)"

    # ── 构建真实 Tool 执行器 ──
    tool_registry = ToolRegistry()
    tool_registry.register_many([
        ReadFile(),
        WriteFile(),
        EditFile(),
        Grep(),
        SearchFile(),
        ListDirectory(),
        RunCommand(),
        GitStatus(),
        GitDiff(),
        GitLog(),
        GitShow(),
        RunTest(),
        PatchFile(),
        ModifyFile(),
        WebFetch(),
        WebSearch(),
        AskUser(),
    ])
    tool_executor = ToolExecutor(tool_registry)

    # ── 构建 Security Classifier（dry_run 时用 mock） ──
    if dry_run:
        security = MockSecurityClassifier()
    else:
        security = build_default_classifier()

    loop = QueryLoop(
        planner=planner,
        skill_registry=SkillRegistry(),
        tool_executor=tool_executor,
        memory_store=FileMemoryStore(),
        context_builder=ContextBuilder(),
        security_classifier=security,
        auto_approve=auto_approve,
        no_memory=no_memory,
    )
    loop._llm_client = llm
    loop._model_display = model_display
    return loop, model_display
