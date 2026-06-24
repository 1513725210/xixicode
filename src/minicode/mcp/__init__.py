"""MCP — Model Context Protocol 动态能力接入层。

参考 MiniCode mcp.ts 的设计：
- StdioMcpClient: 通过 stdio JSON-RPC 连接 MCP server
- 支持 content-length 和 newline-json 两种帧协议
- 自动发现 tools/resources/prompts 并包装为本地 Tool
"""

from minicode.mcp.client import StdioMcpClient
from minicode.mcp.tools import create_mcp_backed_tools, McpServerSummary

__all__ = ["StdioMcpClient", "create_mcp_backed_tools", "McpServerSummary"]
