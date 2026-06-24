"""Patch Tool — 批量 SEARCH/REPLACE + 文件覆盖。

参考 MiniCode 的 patch_file + modify_file 两个工具：
  patch_file:  对单个文件多次精确文本替换（search → replace，replaceAll 可选）
  modify_file:  用完整新内容覆盖文件（先展示 diff 再执行）
"""

from pathlib import Path

from minicode.tool.base import Tool, ToolResult, ToolContext


class PatchFile(Tool):
    """批量 SEARCH/REPLACE — 对单个文件执行多次精确文本替换。

    参考 MiniCode patch-file.ts：
    - 所有 replacement 必须顺序匹配
    - replaceAll=True 替换全部出现，默认只替换第一次
    - 任一 search 未找到 → 整体拒绝
    """

    name = "patch_file"
    description = (
        "对单个文件执行多次精确文本替换（SEARCH/REPLACE）。"
        "所有替换按顺序执行，任一未匹配则整体失败。"
    )
    parameters = {
        "path": "文件路径",
        "replacements": [
            {
                "search": "要替换的原文本（精确匹配）",
                "replace": "替换后的新文本",
                "replaceAll": "是否替换全部出现（默认 false，只替换第一次）",
            }
        ],
    }
    risk_level = "high"

    async def execute(
        self,
        path: str,
        replacements: list[dict],
        context: ToolContext | None = None,
    ) -> ToolResult:
        """执行批量替换。

        Args:
            path: 文件路径
            replacements: 替换列表 [{search, replace, replaceAll?}]
            context: 执行上下文

        Returns:
            ToolResult
        """
        file_path = Path(path).expanduser().resolve()
        if not file_path.exists():
            return ToolResult(ok=False, output="", error=f"文件不存在: {path}")
        if file_path.is_dir():
            return ToolResult(ok=False, output="", error=f"路径是目录: {path}")

        # dry_run 模式
        if context and context.dry_run:
            return ToolResult(
                ok=True,
                output=f"[dry-run] 将对 {path} 执行 {len(replacements)} 处替换",
            )

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            return ToolResult(ok=False, output="", error=f"无法读取文件: {path} ({exc})")

        applied: list[str] = []
        for idx, rep in enumerate(replacements):
            search = rep.get("search", "")
            replace = rep.get("replace", "")
            replace_all = rep.get("replaceAll", False)

            if not search:
                return ToolResult(
                    ok=False, output="",
                    error=f"替换 #{idx + 1}: search 文本不能为空",
                )

            count = content.count(search)
            if count == 0:
                return ToolResult(
                    ok=False, output="",
                    error=f"替换 #{idx + 1}: SEARCH 文本未在 {path} 中找到",
                )

            if replace_all:
                content = content.replace(search, replace)
                applied.append(f"#{idx + 1} replaceAll ({count} 处)")
            else:
                content = content.replace(search, replace, 1)
                applied.append(f"#{idx + 1} replaceOnce")

        try:
            file_path.write_text(content, encoding="utf-8")
        except Exception as exc:
            return ToolResult(ok=False, output="", error=f"无法写入文件: {path} ({exc})")

        return ToolResult(
            ok=True,
            output=f"已修补 {path}：{'; '.join(applied)}",
            artifacts=[{"path": str(file_path), "replacements": len(applied)}],
        )


class ModifyFile(Tool):
    """覆盖文件内容 — 用完整新内容替换文件。

    参考 MiniCode modify-file.ts：
    - 适合大范围重写或生成新文件
    - 与 write_file 的区别：write_file 是基础写入，modify_file 侧重 diff review
    """

    name = "modify_file"
    description = (
        "用新内容完全替换文件。适合大范围重写或更新整个文件。"
        "与 write_file 相比，modify_file 会在审批时展示变更预览。"
    )
    parameters = {
        "path": "文件路径",
        "content": "新文件内容（完整）",
    }
    risk_level = "high"

    async def execute(
        self,
        path: str,
        content: str,
        context: ToolContext | None = None,
    ) -> ToolResult:
        """覆盖文件。

        Args:
            path: 文件路径
            content: 新内容
            context: 执行上下文

        Returns:
            ToolResult
        """
        file_path = Path(path).expanduser().resolve()

        # 读取旧内容（如有）→ 计算 diff 摘要
        old_content = ""
        if file_path.exists():
            try:
                old_content = file_path.read_text(encoding="utf-8")
            except Exception:
                pass

        if context and context.dry_run:
            old_lines = old_content.count("\n") + 1 if old_content else 0
            new_lines = content.count("\n") + 1
            return ToolResult(
                ok=True,
                output=f"[dry-run] 将修改 {path}：{old_lines} 行 → {new_lines} 行",
            )

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
        except Exception as exc:
            return ToolResult(ok=False, output="", error=f"写入失败: {path} ({exc})")

        old_lines = old_content.count("\n") + 1 if old_content else 0
        new_lines = content.count("\n") + 1
        return ToolResult(
            ok=True,
            output=f"已修改 {path}：{old_lines} 行 → {new_lines} 行",
            artifacts=[{
                "path": str(file_path),
                "old_lines": old_lines,
                "new_lines": new_lines,
                "bytes_written": len(content),
            }],
        )
