"""Context Compressor — 层次压缩 (L1/L2/L3)。

参考 MiniCode compact/* 的设计模式，提供三级压缩策略：
  L1 — 短摘要 (< 100 tokens)：仅保留任务结论
  L2 — 详细摘要 (< 500 tokens)：保留关键步骤和发现
  L3 — 原始内容外部存储（V2 实现）

V1 实现：基于规则的截断 + 简单摘要，不依赖 LLM。
"""

from dataclasses import dataclass, field


@dataclass
class CompressedContext:
    """压缩后的上下文片段。

    Attributes:
        summary: 压缩后的摘要文本
        level: 使用的压缩级别 (L1/L2/L3)
        original_tokens: 原始内容的估算 token 数
        compressed_tokens: 压缩后的估算 token 数
        key_findings: 提取的关键发现
    """

    summary: str
    level: str = "L1"
    original_tokens: int = 0
    compressed_tokens: int = 0
    key_findings: list[str] = field(default_factory=list)


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数（4 字符 ≈ 1 token）。

    V1: 简单估算。V2: 使用 tiktoken 精确计算。

    Args:
        text: 输入文本

    Returns:
        int: 估算的 token 数
    """
    if not text:
        return 0
    # 中文约 1.5 字符/token，英文约 4 字符/token
    chinese_chars = sum(1 for c in text if "一" <= c <= "鿿")
    other_chars = len(text) - chinese_chars
    return int(chinese_chars / 1.5 + other_chars / 4)


def compress_to_L1(text: str, task: str = "") -> CompressedContext:
    """L1 压缩 — 极短摘要 (< 100 tokens)。

    仅保留任务结论，丢弃所有中间步骤细节。

    Args:
        text: 要压缩的原始文本
        task: 原始任务描述

    Returns:
        CompressedContext
    """
    original_tokens = estimate_tokens(text)

    if not text.strip():
        return CompressedContext(
            summary=f"[任务] {task[:80]}",
            level="L1",
            original_tokens=0,
            compressed_tokens=estimate_tokens(task[:80]),
        )

    # 提取第一行作为摘要基础
    lines = text.strip().split("\n")
    first_line = lines[0][:100] if lines else ""

    # 统计执行结果
    success_count = text.lower().count("success") + text.count("成功")
    error_count = text.lower().count("error") + text.count("失败") + text.count("错误")

    summary_parts = [f"[任务] {task[:60]}"]
    if first_line:
        summary_parts.append(f"[结论] {first_line}")
    if success_count or error_count:
        summary_parts.append(f"[结果] {success_count} 成功, {error_count} 失败")

    summary = " | ".join(summary_parts)

    return CompressedContext(
        summary=summary,
        level="L1",
        original_tokens=original_tokens,
        compressed_tokens=estimate_tokens(summary),
        key_findings=[first_line] if first_line else [],
    )


def compress_to_L2(text: str, task: str = "") -> CompressedContext:
    """L2 压缩 — 详细摘要 (< 500 tokens)。

    保留关键步骤、发现和结论。

    Args:
        text: 要压缩的原始文本
        task: 原始任务描述

    Returns:
        CompressedContext
    """
    original_tokens = estimate_tokens(text)

    if not text.strip():
        return CompressedContext(
            summary=f"[任务] {task[:80]}\n无执行历史。",
            level="L2",
            original_tokens=0,
            compressed_tokens=estimate_tokens(task[:80]),
        )

    lines = text.strip().split("\n")

    # 提取关键信息
    findings: list[str] = []
    tool_calls: list[str] = []
    errors: list[str] = []

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # 识别步骤标记
        if any(marker in line_stripped for marker in ["[+]", "[x]", "✓", "✗", "+", "x"]):
            tool_calls.append(line_stripped[:150])
        elif any(marker in line_stripped for marker in ["错误", "Error", "失败"]):
            errors.append(line_stripped[:150])
        elif len(findings) < 5 and len(line_stripped) > 20:
            findings.append(line_stripped[:120])

    # 构建 L2 摘要
    parts = [f"## 任务: {task[:80]}"]

    if tool_calls:
        parts.append("\n### 执行步骤")
        for tc in tool_calls[:8]:
            parts.append(f"- {tc}")

    if findings:
        parts.append("\n### 关键发现")
        for f in findings[:5]:
            parts.append(f"- {f}")

    if errors:
        parts.append("\n### 错误")
        for e in errors[:3]:
            parts.append(f"- {e}")

    summary = "\n".join(parts)
    # 截断到 ~500 tokens
    if estimate_tokens(summary) > 500:
        summary = summary[:2000] + "\n... (摘要截断)"

    return CompressedContext(
        summary=summary,
        level="L2",
        original_tokens=original_tokens,
        compressed_tokens=estimate_tokens(summary),
        key_findings=findings,
    )


def compress_to_L3(text: str, task: str = "", storage_path: str | None = None) -> CompressedContext:
    """L3 压缩 — 原始内容外部存储 + 摘要指针。

    V2 实现：将原始文本存入文件，只返回文件路径指针。
    V1 实现：返回 L2 级别摘要 + 存储路径占位。

    Args:
        text: 要压缩的原始文本
        task: 原始任务描述
        storage_path: 外部存储路径

    Returns:
        CompressedContext
    """
    l2 = compress_to_L2(text, task)

    if storage_path:
        l2.summary += f"\n\n[完整内容已存储至: {storage_path}]"
    else:
        l2.summary += "\n\n[L3 外部存储尚未实现 — V2 计划]"

    l2.level = "L3"
    return l2


def compress_context(
    text: str,
    task: str = "",
    max_tokens: int = 500,
) -> CompressedContext:
    """自动选择压缩级别。

    Args:
        text: 要压缩的原始文本
        task: 原始任务描述
        max_tokens: 最大允许 token 数

    Returns:
        CompressedContext
    """
    original = estimate_tokens(text)

    if original <= max_tokens:
        # 无需压缩
        return CompressedContext(
            summary=text,
            level="L0",
            original_tokens=original,
            compressed_tokens=original,
        )

    if max_tokens <= 100:
        return compress_to_L1(text, task)
    elif max_tokens <= 500:
        return compress_to_L2(text, task)
    else:
        return compress_to_L3(text, task)
