"""搜索 Tool — Grep, SearchFile, ListDirectory。"""

import re
from pathlib import Path

from minicode.tool.base import Tool, ToolResult


class Grep(Tool):
    """正则搜索文件内容 — 基于 Python re 模块。

    在指定目录下搜索匹配正则模式的文件内容。
    支持 glob 过滤和最大匹配数限制。
    """

    name = "grep"
    description = "搜索文件内容（正则表达式，支持 glob 过滤）"
    parameters = {
        "pattern": "正则表达式模式（Python re 语法）",
        "path": "搜索目录路径",
        "glob": "可选，文件名过滤 glob（如 *.py）",
    }
    risk_level = "safe"

    MAX_MATCHES = 50

    async def execute(
        self,
        pattern: str,
        path: str,
        glob: str | None = None,
    ) -> ToolResult:
        """在指定目录下搜索文件内容。

        Args:
            pattern: Python 正则表达式
            path: 搜索根目录
            glob: 可选的文件名模式（如 "*.py"）

        Returns:
            ToolResult: output 为带文件和行号的匹配结果
        """
        root = Path(path).expanduser().resolve()
        if not root.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"路径不存在: {path}",
            )
        if not root.is_dir():
            return ToolResult(
                success=False,
                output="",
                error=f"路径不是目录: {path}",
            )

        # 编译正则
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            return ToolResult(
                success=False,
                output="",
                error=f"正则表达式无效: {pattern} ({exc})",
            )

        # 选择文件
        if glob:
            candidates = list(root.rglob(glob))
        else:
            candidates = [f for f in root.rglob("*") if f.is_file()]

        results: list[str] = []
        total_matches = 0

        for file_path in candidates:
            if total_matches >= self.MAX_MATCHES:
                break
            # 跳过二进制/超大文件
            if file_path.suffix in {".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".zip", ".gz", ".png", ".jpg"}:
                continue

            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except (OSError, PermissionError):
                continue

            for i, line in enumerate(text.split("\n"), 1):
                if total_matches >= self.MAX_MATCHES:
                    break
                if compiled.search(line):
                    relative = file_path.relative_to(root) if root in file_path.parents else file_path
                    results.append(f"{relative}:{i}: {line.strip()[:150]}")
                    total_matches += 1

        if not results:
            return ToolResult(
                success=True,
                output=f"在 {path} 中搜索 '{pattern[:60]}' → 未找到匹配",
                artifacts=[{"matches": 0, "files_scanned": len(candidates)}],
            )

        if total_matches >= self.MAX_MATCHES:
            results.append(f"\n（已达上限 {self.MAX_MATCHES} 处，结果截断）")

        output = "\n".join(results)
        return ToolResult(
            success=True,
            output=output,
            artifacts=[{
                "matches": total_matches,
                "files_scanned": len(candidates),
                "pattern": pattern,
            }],
        )


class SearchFile(Tool):
    """按文件名搜索。"""

    name = "search_file"
    description = "按文件名模式搜索文件（glob 匹配）"
    parameters = {
        "pattern": "文件名模式（如 *.py, test_*）",
        "path": "搜索目录路径",
    }
    risk_level = "safe"

    async def execute(self, pattern: str, path: str) -> ToolResult:
        """在指定目录下按文件名搜索。

        Args:
            pattern: 文件名 glob 模式
            path: 搜索根目录

        Returns:
            ToolResult
        """
        root = Path(path).expanduser().resolve()
        if not root.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"路径不存在: {path}",
            )

        candidates = list(root.rglob(pattern))
        # 排除常见忽略目录
        filtered = [
            f for f in candidates
            if "__pycache__" not in str(f)
            and ".git" not in str(f)
            and ".egg" not in str(f)
        ]

        if not filtered:
            return ToolResult(
                success=True,
                output=f"在 {path} 中搜索 '{pattern}' → 未找到匹配文件",
            )

        results = []
        for f in filtered[:50]:
            rel = f.relative_to(root) if root in f.parents else f
            results.append(str(rel))

        output = "\n".join(results)
        return ToolResult(
            success=True,
            output=output,
            artifacts=[{"matches": len(filtered), "pattern": pattern}],
        )


class ListDirectory(Tool):
    """列出目录内容。"""

    name = "list_directory"
    description = "列出目录内容（文件和子目录）"
    parameters = {
        "path": "目录路径",
    }
    risk_level = "safe"

    async def execute(self, path: str) -> ToolResult:
        """列出目录内容。

        Args:
            path: 目录路径

        Returns:
            ToolResult: output 为格式化的目录树
        """
        root = Path(path).expanduser().resolve()
        if not root.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"路径不存在: {path}",
            )
        if not root.is_dir():
            return ToolResult(
                success=False,
                output="",
                error=f"不是目录: {path}",
            )

        lines = [f"{root}/"]

        try:
            entries = sorted(root.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return ToolResult(
                success=False,
                output="",
                error=f"无权限读取目录: {path}",
            )

        file_count = 0
        dir_count = 0
        for entry in entries[:100]:
            # 跳过隐藏文件和缓存
            if entry.name.startswith(".") or entry.name == "__pycache__":
                continue
            if entry.is_dir():
                dir_count += 1
                lines.append(f"  > {entry.name}/")
            else:
                file_count += 1
                lines.append(f"  - {entry.name}")

        if len(entries) > 100:
            lines.append(f"  ... 及其他 {len(entries) - 100} 项")

        output = "\n".join(lines)
        return ToolResult(
            success=True,
            output=output,
            artifacts=[{
                "path": str(root),
                "dirs": dir_count,
                "files": file_count,
                "total_visible": dir_count + file_count,
            }],
        )
