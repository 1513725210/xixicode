"""Tool 注册表 + 执行器。

参考 MiniCode tool.ts 的 ToolRegistry 设计：
- ToolRegistry: 管理 Tool 实例的注册/查找
- ToolExecutor: 统一执行入口，传递 ToolContext 到每个 Tool
"""

import inspect

from minicode.tool.base import Tool, ToolResult, ToolContext


class ToolRegistry:
    """Tool 实例注册表。

    Tool 按 name 唯一索引，重复注册会覆盖。
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册一个 Tool 实例。"""
        self._tools[tool.name] = tool

    def register_many(self, tools: list[Tool]) -> None:
        """批量注册 Tool。"""
        for t in tools:
            self.register(t)

    def get(self, name: str) -> Tool | None:
        """按名称获取 Tool 实例。"""
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        """返回所有已注册 Tool 的名称。"""
        return list(self._tools.keys())

    def list_tools(self) -> list[dict]:
        """返回 LLM 可读的 Tool 列表（用于注入 prompt）。"""
        return [t.to_dict() for t in self._tools.values()]


class ToolExecutor:
    """真实 Tool 执行器。

    参考 MiniCode ToolRegistry.execute() 的设计：
    - 通过 ToolContext 传递 cwd/dry_run 到每个 Tool
    - 支持 awaitUser 结果（ask_user 工具）
    - 与 MockToolExecutor 接口兼容（execute + call_history）
    """

    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self.call_history: list[dict] = []
        self._context: ToolContext = ToolContext()

    def set_context(self, context: ToolContext) -> None:
        """设置执行上下文（cwd, dry_run 等）。"""
        self._context = context

    async def execute(self, tool_name: str, params: dict) -> ToolResult:
        """执行一个 Tool。

        自动检测 Tool.execute() 是否接受 context 参数，
        如果接受则传入当前 ToolContext。

        Args:
            tool_name: 工具名称
            params: 工具参数

        Returns:
            ToolResult: 执行结果
        """
        self.call_history.append({"tool": tool_name, "params": params})

        tool = self.registry.get(tool_name)
        if tool is None:
            return ToolResult(
                ok=False, output="",
                error=f"未知 Tool: {tool_name}（未注册）",
            )

        try:
            # 检测 Tool.execute 是否接受 context 参数
            sig = inspect.signature(tool.execute)
            if "context" in sig.parameters:
                return await tool.execute(**params, context=self._context)
            else:
                return await tool.execute(**params)
        except Exception as exc:
            return ToolResult(
                ok=False, output="",
                error=f"{type(exc).__name__}: {exc}",
            )

    @property
    def call_count(self) -> int:
        return len(self.call_history)
