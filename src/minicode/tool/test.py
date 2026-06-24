"""测试执行 Tool — RunTest。

执行项目测试套件（pytest/tox/自定义命令）。
中等风险 — 仅执行只读操作，但可能消耗大量资源。
"""

import asyncio
from pathlib import Path

from minicode.tool.base import Tool, ToolResult


class RunTest(Tool):
    """运行测试套件。

    默认使用 pytest，可通过 command 参数自定义。
    """

    name = "run_test"
    description = "运行测试套件（默认 pytest）"
    parameters = {
        "target": "测试目标（文件/目录/标记，默认全部）",
        "command": "自定义测试命令（可选，覆盖默认 pytest）",
    }
    risk_level = "medium"

    MAX_OUTPUT = 3000
    TIMEOUT_SEC = 60

    async def execute(self, target: str = "", command: str = "") -> ToolResult:
        """运行测试。

        Args:
            target: 测试目标（pytest 路径或标记表达式）
            command: 自定义命令（为空时使用 pytest）

        Returns:
            ToolResult
        """
        if command and command.strip():
            cmd = command.strip()
        else:
            cmd_parts = ["pytest", "-v", "--tb=short"]
            if target and target.strip():
                cmd_parts.append(target.strip())
            cmd = " ".join(cmd_parts)

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
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
                error=f"测试超时（{self.TIMEOUT_SEC}s）: {cmd[:100]}",
            )
        except OSError as exc:
            return ToolResult(
                success=False,
                output="",
                error=f"测试执行失败: {cmd[:100]} ({exc})",
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
            error=None if proc.returncode == 0 else f"测试失败，退出码: {proc.returncode}",
            artifacts=[{
                "returncode": proc.returncode,
                "command": cmd,
                "stdout_bytes": len(out_text),
                "stderr_bytes": len(err_text),
            }],
        )
