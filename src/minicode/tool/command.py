"""命令执行 Tool — RunCommand。"""

import asyncio

from minicode.tool.base import Tool, ToolResult, BackgroundTask


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
                ok=False, output="", error="命令为空",
            )

        trimmed = command.strip()

        # ── 后台任务检测（参考 MiniCode run-command.ts:141-152）──
        is_background = trimmed.endswith("&") and "&&" not in trimmed
        if is_background:
            clean_cmd = trimmed.rstrip("&").strip()
            try:
                proc = await asyncio.create_subprocess_shell(
                    clean_cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                # 注册后台任务
                from minicode.tool.background import get_registry
                task = get_registry().register(command=clean_cmd, pid=proc.pid or -1)
                return ToolResult(
                    ok=True,
                    output=f"后台命令已启动\nTASK: {task.task_id}\nPID: {task.pid}",
                    backgroundTask=BackgroundTask(
                        task_id=task.task_id,
                        command=clean_cmd,
                        pid=task.pid,
                        started_at=task.started_at,
                    ),
                )
            except OSError as exc:
                return ToolResult(
                    ok=False, output="",
                    error=f"后台命令启动失败: {command[:80]} ({exc})",
                )

        # ── 同步执行 ──
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
