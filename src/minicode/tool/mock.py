"""Mock ToolExecutor — 所有 Tool 返回固定成功结果。

V1 第一阶段：所有 Tool 用 Mock，先让 Agent Loop 跑通。
后续逐步替换为真实实现（ReadFile, WriteFile, EditFile...）。

参考 MiniCode 的 mock-model.ts 分层设计：
- content-aware: 根据 params 返回不同的 Mock 输出
- 覆盖所有已注册工具名称
"""

from minicode.tool.base import ToolResult


class MockToolExecutor:
    """Mock 工具执行器。

    所有 Tool 调用返回预定义的成功结果，
    模拟真实执行但不产生任何副作用。
    """

    def __init__(self):
        self.call_history: list[dict] = []

    async def execute(self, tool_name: str, params: dict) -> ToolResult:
        """模拟执行一个 Tool。

        Args:
            tool_name: 工具名称
            params: 工具参数

        Returns:
            ToolResult: 总是 ok=True 的模拟结果
        """
        self.call_history.append({"tool": tool_name, "params": params})

        pattern = params.get("pattern", "")
        path = params.get("path", "")
        glob = params.get("glob", "")
        query = params.get("query", "")

        if tool_name == "grep":
            if "import" in pattern or "from " in pattern:
                output = (
                    "80+ 处 import 语句分布于:\n"
                    "  main.py → events.py, agent/ (loop.py, planner.py)\n"
                    "  tool/ → base.py, mock.py\n"
                    "  llm/ → client.py\n"
                    "  memory/ → store.py\n"
                    "  context/ → builder.py\n"
                    "  security/ → classifier.py"
                )
            elif pattern:
                output = f"在 {path or '.'} 中搜索 '{pattern[:40]}' → 找到 2 处匹配"
            else:
                output = "找到 5 处匹配"

        elif tool_name == "read_file":
            if path == "src/":
                output = (
                    "src/ 目录包含 14 个文件:\n"
                    " ├─ main.py          CLI 入口 (Click)\n"
                    " ├─ events.py        AgentEvent 7 种类型\n"
                    " ├─ agent/\n"
                    " │   ├─ loop.py      Query Loop (async generator)\n"
                    " │   └─ planner.py   任务拆解 (关键词路由)\n"
                    " ├─ tool/\n"
                    " │   ├─ base.py      Tool ABC + ToolResult\n"
                    " │   └─ mock.py      MockExecutor (9 个 Tool)\n"
                    " ├─ skill/registry.py   Skill 注册表 (5 种)\n"
                    " ├─ llm/client.py    LLM 客户端\n"
                    " ├─ memory/store.py  记忆存储 (Mock)\n"
                    " ├─ context/builder.py 上下文构建\n"
                    " └─ security/classifier.py 安全分级"
                )
            else:
                output = f"读取 {path or '.'} · 可读 (含 {100} 行内容)"

        elif tool_name == "list_directory":
            output = (
                "项目根目录:\n"
                "  src/   源码 (14 个文件, 7 个子包)\n"
                "  tests/ 测试 (conftest.py, test_loop.py)\n"
                "  pyproject.toml  工程配置\n"
                "  README.md       使用说明\n"
                "  spec.md         设计规约 (21 章)\n"
                "  .gitignore"
            )

        elif tool_name == "web_search":
            output = (
                f"QUERY: {query}\n\n"
                "[1] Mock Result 1\n"
                "    URL: https://example.com/1\n"
                "    Mock search result snippet for demonstration.\n\n"
                "[2] Mock Result 2\n"
                "    URL: https://example.com/2\n"
                "    Another mock search result.\n"
            )

        elif tool_name == "web_fetch":
            url = params.get("url", "")
            output = (
                f"URL: {url}\n"
                f"STATUS: 200\n"
                f"CONTENT_TYPE: text/html\n"
                f"TITLE: Mock Page Title\n\n"
                f"Mock page content for {url}. This is simulated content."
            )

        elif tool_name == "ask_user":
            question = params.get("question", "")
            return ToolResult(ok=True, output=question, awaitUser=True)

        else:
            fallback = {
                "edit_file": "已修改文件 (3 行替换)",
                "patch_file": "已修补文件 (2 处替换)",
                "modify_file": "已修改文件 (45 行 → 52 行)",
                "write_file": "已写入文件 (45 行)",
                "run_test": "12/12 测试通过",
                "git_status": "modified: src/order_service.py",
                "git_diff": "1 个文件变更, +4 -3",
                "git_log": "最近 5 条提交",
                "git_show": "commit abc123: Fix NPE in OrderService",
                "search_file": "找到 8 个匹配文件",
            }
            output = fallback.get(tool_name, f"[Mock] {tool_name} 执行完成")

        return ToolResult(ok=True, output=output)

    @property
    def call_count(self) -> int:
        return len(self.call_history)
