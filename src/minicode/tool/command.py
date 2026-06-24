"""命令执行 Tool — RunCommand。"""

import asyncio

from minicode.tool.base import Tool, ToolResult


class RunCommand(Tool):
    """执行 shell 命令。

    高风险 Tool — 执行前触发 Security Layer 审批。
    输出截断到 MAX_OUTPUT 字节。
    """

    name = "run_command"
    description = "执行 shell 命令（高风险，会触发审批）"
    parameters = {
        "command": "要执行的 shell 命令字符串",
    }
    risk_level = "high"

    MAX_OUTPUT = 3000      # 最大输出字节
    TIMEOUT_SEC = 30       # 命令超时

    async def execute(self, command: str) -> ToolResult:
        """执行 shell 命令。

        Args:
            command: shell 命令字符串

        Returns:
            ToolResult: 成功时 output 含 stdout + stderr
        """
        if not command or not command.strip():
            return ToolResult(
                success=False,
                output="",
                error="命令为空",
            )

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error=f"命令超时（{self.TIMEOUT_SEC}s）: {command[:100]}",
            )
        except OSError as exc:
            return ToolResult(
                success=False,
                output="",
                error=f"命令执行失败: {command[:100]} ({exc})",
            )

        out_text = stdout.decode("utf-8", errors="replace")
        err_text = stderr.decode("utf-8", errors="replace")

        parts = []
        if out_text:
            parts.append(out_text)
        if err_text:
            parts.append(f"[stderr]\n{err_text}")

        combined = "\n".join(parts).strip()

        if len(combined) > self.MAX_OUTPUT:
            combined = combined[:self.MAX_OUTPUT] + f"\n... (输出截断，原 {len(combined)} 字节)"

        return ToolResult(
            success=proc.returncode == 0,
            output=combined,
            error=None if proc.returncode == 0 else f"命令退出码: {proc.returncode}",
            artifacts=[{
                "returncode": proc.returncode,
                "stdout_bytes": len(out_text),
                "stderr_bytes": len(err_text),
            }],
        )
