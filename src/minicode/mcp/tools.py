"""MCP Tools — 动态工具发现与包装。

参考 MiniCode mcp.ts createMcpBackedTools 的设计：
- 遍历 mcpServers 配置
- 连接每个 server → 发现 tools
- 包装为本地 Tool 实例（命名: mcp__server__tool）
- 可选: list_mcp_resources / read_mcp_resource（有资源时）
"""

from dataclasses import dataclass, field

from minicode.tool.base import Tool, ToolResult
from minicode.mcp.client import StdioMcpClient, McpServerSummary


# ── MCP 工具包装器 ──


class _McpToolWrapper(Tool):
    """将 MCP 工具包装为本地 Tool 实例。

    动态生成 name, description, parameters, execute。
    """

    def __init__(
        self,
        wrapped_name: str,
        descriptor: dict,
        client: StdioMcpClient,
        original_name: str,
    ):
        self.name = wrapped_name
        self.description = descriptor.get("description", "").strip() or (
            f"调用 MCP 工具 {original_name}（来自 {client.server_name}）"
        )
        self.parameters = descriptor.get("inputSchema", {})
        self.risk_level = "medium"  # MCP 工具默认为中等风险
        self._client = client
        self._original_name = original_name

    async def execute(self, **params) -> ToolResult:
        """调用 MCP 工具。"""
        try:
            result = await self._client.call_tool(self._original_name, params)
            return ToolResult(
                ok=result.get("ok", True),
                output=result.get("output", ""),
            )
        except Exception as exc:
            return ToolResult(
                ok=False,
                output="",
                error=f"MCP 工具调用失败 [{self._client.server_name}/{self._original_name}]: {exc}",
            )


class _McpResourcesTool(Tool):
    """list_mcp_resources — 列出已连接 MCP server 的资源。"""

    name = "list_mcp_resources"
    description = "列出已连接 MCP server 的资源（如有发布）"
    parameters = {"server": "可选，指定 server 名称"}
    risk_level = "safe"

    def __init__(self, clients: dict[str, StdioMcpClient]):
        self._clients = clients

    async def execute(self, server: str = "") -> ToolResult:
        targets = (
            [self._clients[server]] if server and server in self._clients
            else list(self._clients.values())
        )
        lines: list[str] = []
        for client in targets:
            try:
                resources = await client.list_resources()
                for r in resources:
                    lines.append(
                        f"{client.server_name}: {r.uri}"
                        f"{' (' + r.name + ')' if r.name else ''}"
                    )
            except Exception as exc:
                lines.append(
                    f"{client.server_name}: 列出资源失败 ({exc})"
                )
        return ToolResult(
            ok=True,
            output="\n".join(lines) if lines else "无已发布的 MCP 资源",
        )


class _McpReadResourceTool(Tool):
    """read_mcp_resource — 读取指定 MCP 资源。"""

    name = "read_mcp_resource"
    description = "读取指定 MCP server 的指定资源"
    parameters = {
        "server": "MCP server 名称",
        "uri": "资源 URI",
    }
    risk_level = "safe"

    def __init__(self, clients: dict[str, StdioMcpClient]):
        self._clients = clients

    async def execute(self, server: str, uri: str) -> ToolResult:
        client = self._clients.get(server)
        if client is None:
            return ToolResult(ok=False, output="", error=f"未知 MCP server: {server}")
        result = await client.read_resource(uri)
        return ToolResult(
            ok=result.get("ok", True),
            output=result.get("output", ""),
        )


# ── 主入口 ──


@dataclass
class McpBackedToolsResult:
    """MCP 工具发现结果。

    Attributes:
        tools: 包装后的 Tool 列表
        servers: Server 状态摘要列表
        dispose: 清理函数
    """

    tools: list[Tool] = field(default_factory=list)
    servers: list[McpServerSummary] = field(default_factory=list)
    dispose: callable = lambda: None


async def create_mcp_backed_tools(
    mcp_servers: dict[str, dict],
    cwd: str = ".",
) -> McpBackedToolsResult:
    """从 MCP server 配置创建本地工具。

    参考 MiniCode createMcpBackedTools。

    Args:
        mcp_servers: {server_name: {command, args, env, protocol, enabled}}
        cwd: 工作目录

    Returns:
        McpBackedToolsResult: 含 tools + servers + dispose
    """
    clients: list[StdioMcpClient] = []
    clients_by_name: dict[str, StdioMcpClient] = {}
    tools: list[Tool] = []
    servers: list[McpServerSummary] = []
    has_resources = False

    for server_name, config in mcp_servers.items():
        command = (config.get("command") or "").strip()
        if not command:
            servers.append(McpServerSummary(
                name=server_name, status="error",
                error="未配置 command",
            ))
            continue

        if config.get("enabled") is False:
            servers.append(McpServerSummary(
                name=server_name, command=command,
                status="disabled", toolCount=0,
            ))
            continue

        protocol = config.get("protocol", "content-length")
        args = config.get("args", [])
        env = config.get("env", {})
        server_cwd = config.get("cwd", cwd)

        client = StdioMcpClient(
            server_name=server_name,
            command=command,
            args=args if isinstance(args, list) else [],
            env=env if isinstance(env, dict) else {},
            cwd=server_cwd,
            protocol=protocol if protocol in ("content-length", "newline-json") else "content-length",
        )

        try:
            await client.start()
            descriptors = await client.list_tools()
        except Exception as exc:
            await client.close()
            servers.append(McpServerSummary(
                name=server_name, command=command,
                status="error", toolCount=0,
                error=str(exc),
            ))
            continue

        clients.append(client)
        clients_by_name[server_name] = client

        for desc in descriptors:
            wrapped_name = f"mcp__{_sanitize_segment(server_name)}__{_sanitize_segment(desc.name)}"
            wrapper = _McpToolWrapper(
                wrapped_name=wrapped_name,
                descriptor={
                    "description": desc.description,
                    "inputSchema": desc.inputSchema,
                },
                client=client,
                original_name=desc.name if hasattr(desc, 'name') else desc.get('name', 'unknown'),
            )
            wrapper.name = wrapped_name
            tools.append(wrapper)

        # 尝试发现资源
        try:
            resources = await client.list_resources()
            if resources:
                has_resources = True
        except Exception:
            pass

        servers.append(McpServerSummary(
            name=server_name, command=command,
            status="connected", toolCount=len(descriptors),
            protocol=protocol,
        ))

    # 如果有服务器发布了资源，添加 helper 工具
    if has_resources:
        tools.append(_McpResourcesTool(clients_by_name))
        tools.append(_McpReadResourceTool(clients_by_name))

    async def _dispose():
        for c in clients:
            await c.close()

    return McpBackedToolsResult(tools=tools, servers=servers, dispose=_dispose)


def _sanitize_segment(value: str) -> str:
    """清理名称为合法片段。"""
    import re
    result = re.sub(r"[^a-z0-9_-]+", "_", value.lower()).strip("_")
    return result or "tool"
