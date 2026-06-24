"""Git 操作 Tool — GitStatus, GitDiff, GitLog, GitShow。

参考 MiniCode 的只读 git 操作设计，用于代码探索和变更审查。
"""

import asyncio
from pathlib import Path

from minicode.tool.base import Tool, ToolResult


async def _run_git(args: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    """执行 git 命令并返回 (returncode, stdout, stderr)。

    Args:
        args: git 子命令及参数列表 (不含 'git' 前缀)
        cwd: 工作目录

    Returns:
        tuple: (returncode, stdout, stderr)
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await proc.communicate()
        out_text = stdout.decode("utf-8", errors="replace")
        err_text = stderr.decode("utf-8", errors="replace")
        return proc.returncode or 0, out_text, err_text
    except FileNotFoundError:
        return 1, "", "git 未安装或不在 PATH 中"
    except OSError as exc:
        return 1, "", f"git 执行失败: {exc}"


class GitStatus(Tool):
    """查看 Git 工作区状态（已暂存 / 未暂存 / 未跟踪）。"""

    name = "git_status"
    description = "查看 Git 工作区状态（变更、暂存、未跟踪文件）"
    parameters = {
        "path": "仓库路径（可选，默认当前目录）",
    }
    risk_level = "safe"

    async def execute(self, path: str = ".") -> ToolResult:
        """执行 git status。

        Returns:
            ToolResult: output 为简短状态摘要
        """
        cwd = str(Path(path).expanduser().resolve())
        returncode, stdout, stderr = await _run_git(["status", "--short", "--branch"], cwd=cwd)

        if returncode != 0:
            return ToolResult(
                success=False,
                output="",
                error=f"git status 失败: {stderr.strip() or stdout.strip()}",
            )

        output = stdout.strip()
        if not output:
            output = "工作区干净（无变更）"

        return ToolResult(
            success=True,
            output=output,
            artifacts=[{"command": "git status --short --branch", "lines": len(output.split("\n"))}],
        )


class GitDiff(Tool):
    """查看 Git 工作区差异（未暂存的变更）。"""

    name = "git_diff"
    description = "查看 Git 工作区差异（未暂存 + 已暂存）"
    parameters = {
        "path": "仓库路径（可选，默认当前目录）",
    }
    risk_level = "safe"

    async def execute(self, path: str = ".") -> ToolResult:
        """执行 git diff (unstaged) + git diff --cached (staged)。

        Returns:
            ToolResult: output 为 unified diff 摘要
        """
        cwd = str(Path(path).expanduser().resolve())

        # 分别获取 unstaged 和 staged diff
        parts: list[str] = []

        # Unstaged
        rc1, stdout1, stderr1 = await _run_git(["diff", "--stat"], cwd=cwd)
        if rc1 == 0 and stdout1.strip():
            parts.append("### 未暂存变更 (unstaged)\n" + stdout1.strip())

        # Staged
        rc2, stdout2, stderr2 = await _run_git(["diff", "--cached", "--stat"], cwd=cwd)
        if rc2 == 0 and stdout2.strip():
            parts.append("### 已暂存变更 (staged)\n" + stdout2.strip())

        if not parts:
            return ToolResult(
                success=True,
                output="工作区无差异",
                artifacts=[{"files_changed": 0}],
            )

        output = "\n\n".join(parts)
        return ToolResult(
            success=True,
            output=output,
            artifacts=[{"files_changed": len(parts)}],
        )


class GitLog(Tool):
    """查看 Git 提交历史。"""

    name = "git_log"
    description = "查看 Git 提交历史（最近 N 条）"
    parameters = {
        "count": "返回条数（默认 10，最大 50）",
        "path": "仓库路径（可选，默认当前目录）",
    }
    risk_level = "safe"

    async def execute(self, count: int = 10, path: str = ".") -> ToolResult:
        """执行 git log。

        Args:
            count: 返回的最近提交数
            path: 仓库路径

        Returns:
            ToolResult
        """
        count = max(1, min(int(count), 50))
        cwd = str(Path(path).expanduser().resolve())

        returncode, stdout, stderr = await _run_git(
            ["log", f"-{count}", "--oneline", "--decorate"],
            cwd=cwd,
        )

        if returncode != 0:
            return ToolResult(
                success=False,
                output="",
                error=f"git log 失败: {stderr.strip() or stdout.strip()}",
            )

        output = stdout.strip()
        if not output:
            output = "（仓库无提交记录）"

        return ToolResult(
            success=True,
            output=output,
            artifacts=[{"count": count, "command": f"git log -{count} --oneline"}],
        )


class GitShow(Tool):
    """查看 Git 具体提交的详细信息。"""

    name = "git_show"
    description = "查看指定 commit 的详细信息（diff + message）"
    parameters = {
        "commit": "commit hash 或引用（如 HEAD, HEAD~1）",
        "path": "仓库路径（可选，默认当前目录）",
    }
    risk_level = "safe"

    MAX_OUTPUT = 3000

    async def execute(self, commit: str, path: str = ".") -> ToolResult:
        """执行 git show。

        Args:
            commit: commit hash 或引用
            path: 仓库路径

        Returns:
            ToolResult
        """
        cwd = str(Path(path).expanduser().resolve())

        returncode, stdout, stderr = await _run_git(
            ["show", "--stat", "--format=fuller", commit],
            cwd=cwd,
        )

        if returncode != 0:
            return ToolResult(
                success=False,
                output="",
                error=f"git show 失败: {stderr.strip() or stdout.strip()}",
            )

        output = stdout.strip()
        if len(output) > self.MAX_OUTPUT:
            output = output[:self.MAX_OUTPUT] + f"\n... (输出截断，原 {len(output)} 字节)"

        return ToolResult(
            success=True,
            output=output,
            artifacts=[{"commit": commit, "bytes": len(output)}],
        )
