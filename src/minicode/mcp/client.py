"""MCP Client — stdio JSON-RPC 通信。

参考 MiniCode mcp.ts StdioMcpClient 的设计：
- 通过 asyncio subprocess 启动 MCP server
- 支持 content-length 和 newline-json 两种帧协议
- JSON-RPC 2.0: initialize → tools/list → tools/call
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field


# ── 类型 ──


@dataclass
class McpToolDescriptor:
    """MCP 工具描述符。"""
    name: str
    description: str = ""
    inputSchema: dict = field(default_factory=dict)


@dataclass
class McpResourceDescriptor:
    """MCP 资源描述符。"""
    uri: str
    name: str = ""
    description: str = ""
    mimeType: str = ""


@dataclass
class McpPromptDescriptor:
    """MCP Prompt 描述符。"""
    name: str
    description: str = ""
    arguments: list[dict] = field(default_factory=list)


@dataclass
class McpServerSummary:
    """MCP Server 状态摘要。"""
    name: str
    command: str = ""
    status: str = "connecting"  # connecting/connected/error/disabled
    toolCount: int = 0
    error: str = ""
    protocol: str = ""


# ── 常量 ──

MCP_INITIALIZE_TIMEOUT = 10.0
MCP_DEFAULT_TIMEOUT = 5.0


# ── 工具函数 ──


def _sanitize_segment(value: str) -> str:
    """清理 MCP server/tool 名称为合法标识符片段。"""
    import re
    result = re.sub(r"[^a-z0-9_-]+", "_", value.lower()).strip("_")
    return result or "tool"


def _format_tool_call_result(result) -> dict:
    """将 MCP tools/call 响应格式化为 ToolResult 兼容字典。

    参考 MiniCode formatToolCallResult。
    """
    if not isinstance(result, dict):
        return {"ok": True, "output": json.dumps(result, ensure_ascii=False, indent=2)}

    content = result.get("content", [])
    is_error = result.get("isError", False)
    parts: list[str] = []

    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" and "text" in block:
                    parts.append(str(block["text"]))
                else:
                    parts.append(json.dumps(block, ensure_ascii=False, indent=2))
            elif isinstance(block, str):
                parts.append(block)
    elif isinstance(content, str):
        parts.append(content)

    if not parts:
        parts.append(json.dumps(result, ensure_ascii=False, indent=2))

    return {"ok": not is_error, "output": "\n\n".join(parts).strip()}


# ── Stdio MCP Client ──


class StdioMcpClient:
    """通过 stdio 连接 MCP server 的客户端。

    参考 MiniCode StdioMcpClient:
    - spawn() MCP server 子进程
    - initialize() 握手 (initialize → initialized)
    - request(method, params) 发送 JSON-RPC 请求并等待响应
    - 支持 content-length 和 newline-json 帧协议
    """

    def __init__(
        self,
        server_name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str = ".",
        protocol: str = "content-length",
    ):
        self.server_name = server_name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.cwd = cwd
        self.protocol = protocol  # content-length | newline-json

        self._proc: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future] = {}
        self._buffer = b""
        self._line_buffer = ""
        self._lock = asyncio.Lock()

    # ── 生命周期 ──

    async def start(self) -> None:
        """启动 MCP server 并握手。"""
        if self._proc is not None:
            return

        await self._spawn()
        await self._initialize()

    async def close(self) -> None:
        """关闭连接。"""
        # 取消所有等待中的请求
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(
                    RuntimeError(f"MCP {self.server_name}: connection closed")
                )
        self._pending.clear()

        if self._proc is not None:
            try:
                self._proc.kill()
            except Exception:
                pass
            self._proc = None

    # ── MCP 方法 ──

    async def list_tools(self) -> list[McpToolDescriptor]:
        """发现 MCP server 暴露的工具。"""
        result = await self._request("tools/list", {})
        tools_data = result.get("tools", []) if isinstance(result, dict) else []
        return [
            McpToolDescriptor(
                name=t.get("name", "unknown"),
                description=t.get("description", ""),
                inputSchema=t.get("inputSchema", {}),
            )
            for t in tools_data
        ]

    async def list_resources(self) -> list[McpResourceDescriptor]:
        """发现 MCP server 暴露的资源。"""
        try:
            result = await self._request("resources/list", {}, timeout=3.0)
        except Exception:
            return []
        resources = result.get("resources", []) if isinstance(result, dict) else []
        return [
            McpResourceDescriptor(
                uri=r.get("uri", ""),
                name=r.get("name", ""),
                description=r.get("description", ""),
                mimeType=r.get("mimeType", ""),
            )
            for r in resources
        ]

    async def read_resource(self, uri: str) -> dict:
        """读取 MCP 资源。"""
        result = await self._request("resources/read", {"uri": uri}, timeout=5.0)
        if isinstance(result, dict):
            contents = result.get("contents", [])
            if not contents:
                return {"ok": True, "output": "无资源内容"}
            lines = []
            for item in contents:
                if isinstance(item, dict):
                    lines.append(f"URI: {item.get('uri', '?')}")
                    if item.get("mimeType"):
                        lines.append(f"MIME: {item['mimeType']}")
                    lines.append("")
                    if "text" in item:
                        lines.append(str(item["text"]))
                    elif "blob" in item:
                        lines.append(f"BLOB: {str(item['blob'])[:500]}")
            return {"ok": True, "output": "\n".join(lines)}
        return {"ok": False, "output": str(result)}

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """调用 MCP 工具。"""
        result = await self._request(
            "tools/call", {"name": name, "arguments": arguments}
        )
        return _format_tool_call_result(result)

    # ── JSON-RPC 核心 ──

    async def _initialize(self) -> None:
        """MCP 握手: initialize → initialized。"""
        await self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "minicode", "version": "0.1.0"},
            },
            timeout=MCP_INITIALIZE_TIMEOUT,
        )
        self._notify("notifications/initialized", {})

    def _notify(self, method: str, params: dict) -> None:
        """发送 JSON-RPC notification（无 id，无响应）。"""
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _request(
        self, method: str, params: dict, timeout: float = MCP_DEFAULT_TIMEOUT
    ) -> dict:
        """发送 JSON-RPC request 并等待响应。"""
        req_id = self._next_id
        self._next_id += 1
        message = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        try:
            self._send(message)
            result = await asyncio.wait_for(future, timeout=timeout)
            return result if isinstance(result, dict) else {}
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"MCP {self.server_name}: {method} 请求超时 ({timeout}s)"
            )
        finally:
            self._pending.pop(req_id, None)

    def _send(self, message: dict) -> None:
        """发送 JSON-RPC 消息到 MCP server stdin。"""
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError(f"MCP {self.server_name}: 未连接")

        body = json.dumps(message, ensure_ascii=False).encode("utf-8")

        if self.protocol == "newline-json":
            self._proc.stdin.write(body + b"\n")
        else:
            # content-length framing
            header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
            self._proc.stdin.write(header + body)

    # ── 子进程管理 ──

    async def _spawn(self) -> None:
        """启动 MCP server 子进程。"""
        env = {**os.environ, **{k: str(v) for k, v in self.env.items()}}

        try:
            self._proc = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
                env=env,
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"MCP {self.server_name}: 命令未找到: {self.command}"
            )
        except OSError as e:
            raise RuntimeError(
                f"MCP {self.server_name}: 启动失败: {e}"
            )

        # 启动 stdout 读取循环
        asyncio.create_task(self._read_stdout())

        # 给进程一点启动时间
        await asyncio.sleep(0.1)

    async def _read_stdout(self) -> None:
        """持续读取 MCP server stdout，解析 JSON-RPC 响应。"""
        if self._proc is None or self._proc.stdout is None:
            return

        try:
            while True:
                if self.protocol == "newline-json":
                    line = await self._proc.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace").strip()
                    if decoded:
                        self._handle_message(decoded)
                else:
                    # content-length framing
                    # 读取 header
                    header_bytes = b""
                    while b"\r\n\r\n" not in header_bytes:
                        chunk = await self._proc.stdout.read(1)
                        if not chunk:
                            return
                        header_bytes += chunk

                    header_text = header_bytes.decode("utf-8", errors="replace")
                    content_length = 0
                    for line in header_text.split("\r\n"):
                        if line.lower().startswith("content-length:"):
                            content_length = int(line.split(":")[1].strip())
                            break

                    # 读取 body
                    body_bytes = await self._proc.stdout.readexactly(content_length)
                    decoded = body_bytes.decode("utf-8", errors="replace")
                    self._handle_message(decoded)
        except (asyncio.IncompleteReadError, ConnectionResetError, OSError):
            pass  # 进程退出
        except Exception:
            pass

    def _handle_message(self, raw: str) -> None:
        """解析单条 JSON-RPC 响应并分发到对应 future。"""
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_id = message.get("id")
        if msg_id is None or not isinstance(msg_id, int):
            return  # notification or invalid

        future = self._pending.get(msg_id)
        if future is None or future.done():
            return

        if "error" in message:
            err = message["error"]
            future.set_exception(
                RuntimeError(
                    f"MCP {self.server_name}: {err.get('message', 'unknown error')}"
                )
            )
        else:
            future.set_result(message.get("result", {}))
