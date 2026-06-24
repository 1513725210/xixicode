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
from minicode.mcp.tools import create_mcp_backed_tools
from minicode.llm.client import DeepSeekLLMClient, MockLLMClient
from minicode.memory.store import FileMemoryStore
from minicode.context.builder import ContextBuilder
from minicode.security.classifier import build_default_classifier, MockSecurityClassifier
from minicode.tui import LiveDisplay


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


async def stream_events(task: str, loop: QueryLoop, display: LiveDisplay):
    """消费 AgentEvent 流并通过 LiveDisplay 渲染到终端。"""
    try:
        async for event in loop.run(task):
            display.render(event)
            # 审批事件需要交互
            if event.type == "need_approval":
                detail = event.detail or {}
                approval_event = detail.get("_approval_event")
                approval_result = detail.get("_approval_result")
                if approval_event is not None and approval_result is not None:
                    choice = display.prompt("  Approve? [y/n] ").strip().lower()
                    if choice == "y":
                        approval_result["approved"] = True
                    approval_event.set()
    except asyncio.CancelledError:
        display.print("\n  中断")
        display.print("  [c] 继续等待   [r] 重新规划   [a] 放弃任务")


# ── REPL ──


async def repl_loop(loop: QueryLoop, display: LiveDisplay):
    """交互式 REPL 循环。"""
    while True:
        try:
            user_input = display.prompt("> ")
        except (KeyboardInterrupt, EOFError):
            display.print("\n  再见")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            _handle_meta_command(user_input, loop, display)
            continue

        await stream_events(user_input, loop, display)


def _handle_meta_command(cmd: str, loop: QueryLoop, display: LiveDisplay):
    """处理 / 开头的元命令。"""
    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command in ("/exit", "/quit"):
        display.print("  再见")
        sys.exit(0)
    elif command == "/help":
        display.print("""
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
        display.print(f"  可用 Skill: {', '.join(skills)}")
    elif command == "/history":
        history = loop.tool_executor.call_history
        if not history:
            display.print("  暂无 Tool 调用记录")
        else:
            display.print(f"  Tool 调用记录 ({len(history)} 次):")
            for i, call in enumerate(history, 1):
                display.print(f"  {i}. {call['tool']} -> {call['params']}")
    elif command == "/memory":
        count = loop.memory_store.count
        display.print(f"  会话记忆: {count} 条")
    elif command == "/model":
        model_disp = getattr(loop, "_model_display", "unknown")
        display.print(f"  当前模型: {model_disp}")
    elif command == "/clear":
        display.print("\033[2J\033[H")
    else:
        display.print(f"  未知命令: {command}，输入 /help 查看帮助")


# ── One-shot ──


async def oneshot(task: str, loop: QueryLoop, display: LiveDisplay):
    """单任务模式：执行 -> 输出 -> 退出。"""
    await stream_events(task, loop, display)
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

    # 单一事件循环执行（MCP 客户端需要共享事件循环）
    async def _run():
        loop, model_display = await _build_loop(
            auto_approve=auto_approve,
            dry_run=dry_run,
            no_memory=no_memory,
            model=model,
        )

        # 创建 LiveDisplay
        with LiveDisplay(model=model_display, verbose=verbose, quiet=quiet) as display:
            # 显示 Banner
            if not quiet:
                info = get_repo_info()
                info["model"] = model_display
                display.show_banner(BANNER.format(**info))

            try:
                if task:
                    await oneshot(task, loop, display)
                else:
                    try:
                        await repl_loop(loop, display)
                    except KeyboardInterrupt:
                        display.print("\n  再见")
            finally:
                await loop.close()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        click.echo("\n  再见")


async def _build_loop(
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
        # LLM 可用 → 使用 LLM SkillRouter 替代关键词匹配
        from minicode.skill.router import SkillRouter as LLMSkillRouter
        skill_registry = SkillRegistry(skill_router=LLMSkillRouter(llm))
    else:
        llm = MockLLMClient()
        planner = KeywordPlanner()
        model_display = "mock (V1 skeleton)"
        skill_registry = SkillRegistry()

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

    # ── MCP 动态能力接入 ──
    mcp_dispose = None
    mcp_servers_loaded = 0
    try:
        import json as _json
        mcp_config_path = os.path.join(
            os.path.expanduser("~"), ".minicode", "mcp.json"
        )
        if os.path.exists(mcp_config_path):
            mcp_config = _json.loads(Path(mcp_config_path).read_text(encoding="utf-8"))
            mcp_servers_cfg = mcp_config.get("mcpServers", {})
            if mcp_servers_cfg:
                mcp_result = await create_mcp_backed_tools(
                    mcp_servers=mcp_servers_cfg,
                    cwd=os.getcwd(),
                )
                for tool in mcp_result.tools:
                    tool_registry.register(tool)
                mcp_servers_loaded = len([s for s in mcp_result.servers if s.status == "connected"])
                mcp_dispose = mcp_result.dispose
                if mcp_servers_loaded > 0:
                    click.echo(
                        f"  [MCP] 已连接 {mcp_servers_loaded} 个 server, "
                        f"加载 {len(mcp_result.tools)} 个工具",
                        err=True,
                    )
    except Exception as exc:
        click.echo(f"  [MCP] 初始化失败: {exc}", err=True)

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
    loop._mcp_dispose = mcp_dispose  # MCP 清理回调
    return loop, model_display
