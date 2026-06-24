"""文件操作 Tool — ReadFile, WriteFile, EditFile。"""

from pathlib import Path

from minicode.tool.base import Tool, ToolResult


class ReadFile(Tool):
    """读取文件内容，支持 offset/limit 分段读取。"""

    name = "read_file"
    description = "读取文件内容（支持行偏移和行数限制）"
    parameters = {
        "path": "文件路径（相对于仓库根目录）",
        "offset": "起始行号（0-based，可选，默认从头开始）",
        "limit": "读取行数（可选，默认全部）",
    }
    risk_level = "safe"

    async def execute(self, path: str, offset: int = 0, limit: int | None = None) -> ToolResult:
        """读取文件并返回带行号的内容。

        Args:
            path: 文件路径
            offset: 起始行（0-based），默认 0
            limit: 最大行数，默认 None = 全部

        Returns:
            ToolResult: success=True 时 output 为带行号的文件内容
        """
        file_path = Path(path).expanduser().resolve()
        if not file_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"文件不存在: {path}",
            )
        if file_path.is_dir():
            return ToolResult(
                success=False,
                output="",
                error=f"路径是目录，不是文件: {path}",
            )

        try:
            raw = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return ToolResult(
                success=False,
                output="",
                error=f"读取文件失败: {path} ({exc})",
            )

        lines = raw.split("\n")
        total = len(lines)

        start = max(0, offset)
        end = min(total, start + limit) if limit is not None else total
        selected = lines[start:end]

        # 构建带行号的输出
        output_lines = []
        for i, line_content in enumerate(selected, start=start + 1):
            output_lines.append(f"{i:>6}│ {line_content}")
        output = "\n".join(output_lines)

        return ToolResult(
            success=True,
            output=output,
            artifacts=[{
                "path": str(file_path),
                "total_lines": total,
                "offset": start,
                "limit": limit,
                "returned_lines": end - start,
            }],
        )


class WriteFile(Tool):
    """写入/覆盖文件。V1 占位 — 待 Phase 2 完整实现。"""

    name = "write_file"
    description = "写入/创建文件（覆盖模式）"
    parameters = {
        "path": "文件路径",
        "content": "要写入的内容",
    }
    risk_level = "high"

    async def execute(self, path: str, content: str) -> ToolResult:
        """写入文件内容。

        Args:
            path: 目标文件路径
            content: 要写入的文本内容

        Returns:
            ToolResult
        """
        file_path = Path(path).expanduser().resolve()
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            lines = content.count("\n") + 1
            return ToolResult(
                success=True,
                output=f"已写入 {str(file_path)} ({lines} 行, {len(content)} 字节)",
                artifacts=[{
                    "path": str(file_path),
                    "lines": lines,
                    "bytes": len(content),
                }],
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                output="",
                error=f"写入文件失败: {path} ({exc})",
            )


class EditFile(Tool):
    """SEARCH/REPLACE 精确编辑 — 语言无关的文本替换。

    search 文本必须在文件中恰好出现一次，否则拒绝编辑。
    """

    name = "edit_file"
    description = "SEARCH/REPLACE 精确编辑（search 文本必须唯一匹配一次）"
    parameters = {
        "path": "文件路径",
        "search": "要替换的原文本（精确匹配，必须在文件中恰好出现一次）",
        "replace": "替换后的新文本",
    }
    risk_level = "high"

    async def execute(self, path: str, search: str, replace: str) -> ToolResult:
        """在文件中执行一次 SEARCH/REPLACE。

        Args:
            path: 文件路径
            search: 精确匹配的原文本
            replace: 替换文本

        Returns:
            ToolResult: 成功时 output 为 diff 摘要
        """
        file_path = Path(path).expanduser().resolve()
        if not file_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"文件不存在: {path}",
            )
        if file_path.is_dir():
            return ToolResult(
                success=False,
                output="",
                error=f"路径是目录，不是文件: {path}",
            )

        try:
            original = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            return ToolResult(
                success=False,
                output="",
                error=f"无法读取文件: {path} ({exc})",
            )

        count = original.count(search)
        if count == 0:
            return ToolResult(
                success=False,
                output="",
                error=f"SEARCH 文本未在 {path} 中找到",
            )
        if count > 1:
            return ToolResult(
                success=False,
                output="",
                error=f"SEARCH 文本在 {path} 中匹配了 {count} 次（要求恰好 1 次）",
            )

        new_content = original.replace(search, replace, 1)

        try:
            file_path.write_text(new_content, encoding="utf-8")
        except Exception as exc:
            return ToolResult(
                success=False,
                output="",
                error=f"无法写入文件: {path} ({exc})",
            )

        # 构建简单 diff 摘要
        old_lines = search.split("\n")
        new_lines = replace.split("\n")
        diff_summary = (
            f"已编辑 {str(file_path)}:\n"
            f"  - {len(old_lines)} 行删除\n"
            f"  + {len(new_lines)} 行插入"
        )

        return ToolResult(
            success=True,
            output=diff_summary,
            artifacts=[{
                "path": str(file_path),
                "removed_lines": len(old_lines),
                "added_lines": len(new_lines),
            }],
        )
