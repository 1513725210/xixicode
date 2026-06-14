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
from pathlib import Path

import click

from minicode import __version__
from minicode.events import AgentEvent
from minicode.agent.loop import QueryLoop
from minicode.agent.planner import KeywordPlanner, LLMPlanner
from minicode.tool.mock import MockToolExecutor
from minicode.skill.registry import MockSkillRegistry
from minicode.llm.client import DeepSeekLLMClient, MockLLMClient
from minicode.memory.store import MockMemoryStore
from minicode.context.builder import MockContextBuilder
from minicode.security.classifier import MockSecurityClassifier


# ── Banner ──

BANNER = f"""
╭──────────────────────────────────────────────────────────╮
│                                                          │
│   🧠 MiniCode v{__version__}                                     │
│                                                          │
│   仓库  {{repo}}          模型  {{model}}  │
│   分支  {{branch}}                           文件  {{files}} 个     │
│                                                          │
│   输入任务开始，或 /help 查看帮助                        │
│                                                          │
╰──────────────────────────────────────────────────────────╯"""


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


def _render_event(event: AgentEvent):
    """将单个 AgentEvent 渲染为一行终端输出。"""
    icon = event.icon
    msg = event.message

    if event.type == "thinking":
        detail = event.detail or {}
        reasoning = detail.get("reasoning", "")
        if reasoning and detail.get("phase") == "plan_complete":
            click.echo(f"  {icon} {msg}")
            click.echo(f"  🧠 {reasoning}")
        else:
            click.echo(f"  {icon} {msg}")
    elif event.type == "tool_result":
        # tool_result 不另起一行，追加在 tool_call 之后
        click.echo(f"{msg}")
    elif event.type == "need_approval":
        detail = event.detail or {}
        approval_event = detail.get("_approval_event")
        approval_result = detail.get("_approval_result")

        click.echo(f"\n  {icon} High Risk Action")
        click.echo(f"  Tool:  {detail.get('tool', '?')}")
        click.echo(f"  Risk:  {detail.get('risk', '?')}")
        if detail.get("description"):
            click.echo(f"  Desc:  {detail.get('description')}")

        if approval_event is not None and approval_result is not None:
            # 真正的审批：等待用户输入
            choice = click.prompt("  Approve? [y/n]", type=str, default="n").strip().lower()
            if choice == "y":
                approval_result["approved"] = True
            approval_event.set()
        else:
            # 无 Event（测试/Mock 路径）→ 自动通过
            click.echo("  Approve? [y/n] › y (auto)")
    elif event.type == "done":
        click.echo(f"\n  {icon} {msg}")
    else:
        # thinking, tool_call, progress, reflection
        click.echo(f"  {icon} {msg}")


# ── REPL ──


async def repl_loop(loop: QueryLoop):
    """交互式 REPL 循环。

    读取用户输入 → 执行 QueryLoop → 渲染事件 → 回到提示符。
    """
    while True:
        try:
            user_input = click.prompt("", prompt_suffix="> ").strip()
        except (KeyboardInterrupt, EOFError):
            click.echo("\n  再见 👋")
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
        click.echo("  再见 👋")
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

    # 构建 QueryLoop
    loop = _build_loop()

    # 显示 Banner（安静模式跳过）
    if not quiet:
        info = get_repo_info()
        if model:
            info["model"] = model
        click.echo(BANNER.format(**info))

    # 确定执行模式
    if task:
        # One-shot 模式
        asyncio.run(oneshot(task, loop))
    else:
        # REPL 模式
        try:
            asyncio.run(repl_loop(loop))
        except KeyboardInterrupt:
            click.echo("\n  再见 👋")


def _build_loop() -> QueryLoop:
    """构建 QueryLoop，自动选择真实或 Mock 后端。

    环境变量 `deepseek` 存在 → DeepSeekLLMClient + LLMPlanner
    不存在 → MockLLMClient + KeywordPlanner
    """
    api_key = os.environ.get("deepseek", "")

    if api_key:
        llm = DeepSeekLLMClient(api_key=api_key)
        planner = LLMPlanner(llm)
        model_display = "deepseek-chat"
    else:
        llm = MockLLMClient()
        planner = KeywordPlanner()
        model_display = "mock (V1 skeleton)"

    loop = QueryLoop(
        planner=planner,
        skill_registry=MockSkillRegistry(),
        tool_executor=MockToolExecutor(),
        memory_store=MockMemoryStore(),
        context_builder=MockContextBuilder(),
        security_classifier=MockSecurityClassifier(),
    )
    # 将 llm 引用挂在 loop 上供 /model 命令使用
    loop._llm_client = llm
    loop._model_display = model_display
    return loop
