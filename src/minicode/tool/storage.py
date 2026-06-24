"""Tool Result Storage — 大工具结果移出 Prompt。

参考 MiniCode utils/tool-result-storage.ts 的设计：
- 超大 tool output 持久化到 ~/.minicode/tool-results/
- 在模型可见上下文中替换为短预览 + 文件路径
- 支持单结果替换 + 批量 budget 控制

与简单截断的区别：截断 = 数据丢失；preview+path = 数据可查。
"""

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from minicode.config import MINICODE_HOME

# ── 路径 ──

TOOL_RESULTS_DIR = os.path.join(MINICODE_HOME, "tool-results")

# ── 数据结构 ──


@dataclass
class StoredResult:
    """已存储的工具结果。

    Attributes:
        result_id: 唯一标识
        file_path: 完整结果文件路径
        preview: 截断预览文本
        original_size: 原始字节数
    """

    result_id: str
    file_path: str
    preview: str
    original_size: int = 0


@dataclass
class ReplacedResult:
    """替换后的工具结果（用于 prompt 上下文）。

    Attributes:
        tool_name: 工具名
        preview: 短预览文本
        full_path: 完整结果文件路径
        original_size: 原始大小
    """

    tool_name: str
    preview: str
    full_path: str
    original_size: int = 0

    def format_for_prompt(self) -> str:
        """生成 prompt 中可见的替换文本。"""
        return (
            f"[工具输出已截断]\n"
            f"工具: {self.tool_name}\n"
            f"预览: {self.preview}\n"
            f"完整结果: {self.full_path} ({self.original_size} 字节)"
        )


# ── 管理类 ──


class ToolResultStorage:
    """大工具结果存储管理器。

    参考 MiniCode 的 ContentReplacementState 模式：
    - store(): 写入完整结果到磁盘，返回 preview + path
    - apply_budget(): 对一批结果应用总量控制
    """

    # 默认阈值：超过此字节数的 tool output 会被移出 prompt
    DEFAULT_MAX_PROMPT_BYTES = 2000
    # 每步工具结果总字节上限
    DEFAULT_TOTAL_BUDGET = 8000

    def __init__(self, storage_dir: str | None = None):
        self._dir = Path(storage_dir or TOOL_RESULTS_DIR)
        self._dir.mkdir(parents=True, exist_ok=True)

    def store(
        self,
        tool_name: str,
        output: str,
        max_prompt_bytes: int | None = None,
    ) -> ReplacedResult:
        """如果 output 过大，将其移出 prompt。

        Args:
            tool_name: 工具名称
            output: 原始输出文本
            max_prompt_bytes: 触发阈值（None = 使用默认值）

        Returns:
            ReplacedResult: 始终返回，小结果也返回完整文本作为 preview
        """
        threshold = max_prompt_bytes or self.DEFAULT_MAX_PROMPT_BYTES

        if len(output) <= threshold:
            # 无需存储 — 返回原文本
            return ReplacedResult(
                tool_name=tool_name,
                preview=output,
                full_path="",
                original_size=len(output),
            )

        # 生成存储文件
        result_id = uuid.uuid4().hex[:12]
        file_path = self._dir / f"{tool_name}_{result_id}.txt"
        file_path.write_text(output, encoding="utf-8")

        # 生成预览：前 500 字符 + 摘要
        preview = output[:500]
        if len(output) > 500:
            total_lines = output.count("\n") + 1
            preview += f"\n... (共 {total_lines} 行, {len(output)} 字节)"

        return ReplacedResult(
            tool_name=tool_name,
            preview=preview,
            full_path=str(file_path),
            original_size=len(output),
        )

    def apply_budget(
        self,
        results: list[ReplacedResult],
        total_budget: int | None = None,
    ) -> list[ReplacedResult]:
        """对一批工具结果应用总量控制。

        确保所有结果的 preview 之和不超过 total_budget。
        超出预算时，较早的结果会被进一步压缩。

        Args:
            results: 替换后的结果列表
            total_budget: 总字节预算

        Returns:
            list[ReplacedResult]: 调整后的结果列表
        """
        budget = total_budget or self.DEFAULT_TOTAL_BUDGET
        total = sum(len(r.preview) for r in results)

        if total <= budget:
            return results

        # 超出预算：逐个缩减
        adjusted = list(results)
        excess = total - budget

        for r in adjusted:
            if excess <= 0:
                break
            if len(r.preview) > 200:
                cut = min(excess, len(r.preview) - 200)
                r.preview = r.preview[:len(r.preview) - cut] + f"\n... ({cut} 字符省略)"
                excess -= cut

        return adjusted

    def read_full(self, result_id_or_path: str) -> str | None:
        """读取完整结果。

        Args:
            result_id_or_path: 结果 ID 或完整路径

        Returns:
            str | None: 完整内容，文件不存在返回 None
        """
        # 尝试作为完整路径
        path = Path(result_id_or_path)
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")

        # 尝试作为 ID 在存储目录中查找
        for f in self._dir.glob(f"*{result_id_or_path}*"):
            return f.read_text(encoding="utf-8", errors="replace")

        return None


# ── 便捷函数 ──


def replace_large_result(
    tool_name: str,
    output: str,
    storage: ToolResultStorage | None = None,
) -> ReplacedResult:
    """将大工具结果替换为 preview + path。

    Args:
        tool_name: 工具名
        output: 原始输出
        storage: 存储实例（None 时自动创建）

    Returns:
        ReplacedResult: 替换后的结果（小结果直接返回原文本）
    """
    store = storage or ToolResultStorage()
    return store.store(tool_name, output)
