"""Prompt Injection Detection — 安全层 Level 2。

检测以下注入模式：
1. 指令覆盖 — "ignore previous instructions"
2. System prompt 泄露 — "reveal your system prompt"
3. 凭证提取 — "what is your API key"

参考 MiniCode 的安全设计，注入检测不阻断执行，而是标记风险供后续审批。
"""

from dataclasses import dataclass, field


@dataclass
class InjectionVerdict:
    """注入检测结论。

    Attributes:
        detected: 是否检测到注入
        risk_level: 风险等级 (safe/low/medium/high)
        patterns_matched: 匹配到的注入模式列表
        sanitized: 清洗后的文本（如有）
    """

    detected: bool = False
    risk_level: str = "safe"
    patterns_matched: list[str] = field(default_factory=list)
    sanitized: str | None = None


# ── 注入模式库 ──


# 指令覆盖模式 — 诱导模型忽略原始 system prompt
OVERRIDE_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|directives?)",
    r"(?i)forget\s+(all\s+)?(previous|prior|your)\s+(instructions?|training|rules?)",
    r"(?i)you\s+are\s+now\s+(a\s+)?(different|new)\s+(AI|assistant|model|role)",
    r"(?i)disregard\s+(all\s+)?(previous|prior|earlier)\s+(instructions?|prompts?)",
    r"(?i)override\s+(your\s+)?(system\s+)?(prompt|instructions?|rules?)",
    r"(?i)from\s+now\s+on\s+you\s+(are|will\s+be|must)",
    r"(?i)your\s+new\s+(role|identity|persona|instructions?)\s+(is|are)",
    r"(?i)pretend\s+(you\s+are|to\s+be)",
    r"(?i)act\s+as\s+(if\s+)?(you\s+are|a\s+different)",
    r"(?i)do\s+not\s+follow\s+(your\s+)?(system\s+)?(instructions?|rules?|prompts?)",
]

# System prompt 泄露模式 — 诱导模型暴露内部指令
LEAK_PATTERNS = [
    r"(?i)(reveal|show|tell|print|output|display|repeat|dump)\s+(me\s+)?(your\s+)?(system\s+)?(prompt|instructions?|rules?|directives?)",
    r"(?i)what\s+(is|are)\s+(your\s+)?(system\s+)?(prompt|instructions?|rules?)",
    r"(?i)(what|how)\s+were\s+you\s+(programmed|instructed|trained|told)",
    r"(?i)repeat\s+(back\s+)?(the\s+)?(beginning|start|first\s+part)\s+of\s+(the\s+)?(conversation|prompt)",
    r"(?i)what\s+(does\s+)?(the\s+)?(above|preceding|system)\s+(text|message|prompt)\s+say",
    r"(?i)(write|output)\s+(your\s+)?(system\s+)?(prompt|instructions?)\s+(verbatim|word\s+for\s+word|exactly)",
]

# 凭证提取模式 — 诱导模型泄露密钥
CREDENTIAL_PATTERNS = [
    r"(?i)what\s+is\s+(your\s+)?(api|auth|access)\s+(key|token|secret)",
    r"(?i)(reveal|show|tell|give)\s+(me\s+)?(your\s+)?(api|auth|access)\s+(key|token|secret)",
    r"(?i)(print|output|echo)\s+(the\s+)?(environment|env)\s+variable",
    r"(?i)what\s+(environment|env)\s+variables?\s+(are|do\s+you)\s+(set|have|see)",
]

# 所有模式合并为带分类标签的列表
ALL_PATTERNS: list[tuple[str, str, str]] = (
    [("override", p, "指令覆盖") for p in OVERRIDE_PATTERNS]
    + [("leak", p, "Prompt 泄露") for p in LEAK_PATTERNS]
    + [("credential", p, "凭证提取") for p in CREDENTIAL_PATTERNS]
)


# ── 检测函数 ──


def detect_injection(text: str, tool_name: str = "", params: dict | None = None) -> InjectionVerdict:
    """检测用户输入中是否包含注入攻击模式。

    检查范围：
    - 用户任务文本
    - Tool 参数中的字符串值（如 WriteFile 的 content）
    - 命令参数中的字符串值（如 RunCommand 的 command）

    Args:
        text: 主要输入文本（用户任务）
        tool_name: 关联的工具名（用于上下文判断）
        params: 工具参数（也需检查）

    Returns:
        InjectionVerdict: 检测结论
    """
    verdict = InjectionVerdict()

    # 检查所有文本源
    texts_to_check = [text]
    if params:
        for value in params.values():
            if isinstance(value, str) and len(value) > 10:
                texts_to_check.append(value)

    import re

    matched_categories: set[str] = set()

    for check_text in texts_to_check:
        for category, pattern, label in ALL_PATTERNS:
            if re.search(pattern, check_text):
                verdict.patterns_matched.append(f"[{label}] {pattern}")
                matched_categories.add(category)

    if verdict.patterns_matched:
        verdict.detected = True

        # 凭证提取 = high risk
        if "credential" in matched_categories:
            verdict.risk_level = "high"
        # 指令覆盖 = medium risk
        elif "override" in matched_categories:
            verdict.risk_level = "medium"
        # Prompt 泄露 = low risk
        else:
            verdict.risk_level = "low"

    return verdict


def sanitize_input(text: str) -> str:
    """清洗用户输入中的明显注入模式。

    不用于阻断执行，只用于日志记录和安全审计。

    先扫描原始文本收集所有匹配项，再一次性替换，
    避免顺序替换导致的连锁修改问题。

    Args:
        text: 原始输入

    Returns:
        str: 清洗后的文本（标注了可疑部分）
    """
    import re

    # 1) 先扫描原始文本，收集所有匹配
    matches: list[tuple[int, int, str]] = []  # (start, end, label)
    for _, pattern, label in ALL_PATTERNS:
        for m in re.finditer(pattern, text):
            matches.append((m.start(), m.end(), label))

    if not matches:
        return text

    # 2) 按位置排序，处理重叠（保留最长匹配）
    matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    filtered_matches: list[tuple[int, int, str]] = []
    last_end = 0
    for start, end, label in matches:
        if start >= last_end:
            filtered_matches.append((start, end, label))
            last_end = end

    # 3) 从后往前替换，避免索引移位
    result = text
    for start, end, label in reversed(filtered_matches):
        result = result[:start] + f"[FILTERED:{label}]" + result[end:]

    return f"[安全标记] {result}"
