"""SecurityClassifier — 安全分级入口。

委托 SecurityPipeline 执行实际检查。
保留 MockSecurityClassifier 用于测试兼容。
"""

from typing import Literal

from minicode.security.rules import (
    SecurityVerdict,
    DenyListRule,
    CommandPatternRule,
    RiskClassifierRule,
)
from minicode.security.pipeline import SecurityPipeline

RiskLevel = Literal["safe", "medium", "high"]


class SecurityClassifier:
    """真实安全分级器。

    内部使用 SecurityPipeline 编排规则：
    1. DenyListRule — 阻断已知危险命令
    2. CommandPatternRule — 阻断可疑模式
    3. RiskClassifierRule — 分级
    """

    def __init__(self, pipeline: SecurityPipeline | None = None):
        if pipeline is None:
            pipeline = SecurityPipeline()
            pipeline.register(DenyListRule())
            pipeline.register(CommandPatternRule())
            pipeline.register(RiskClassifierRule())
        self._pipeline = pipeline

    def classify(self, tool_name: str, params: dict) -> RiskLevel:
        """对 Tool 调用进行风险分级（兼容旧接口）。

        Returns:
            RiskLevel: safe/medium/high
        """
        verdict = self._pipeline.check(tool_name, params)
        return verdict.risk_level  # type: ignore[return-value]

    def check(self, tool_name: str, params: dict) -> SecurityVerdict:
        """执行完整安全检查。

        Returns:
            SecurityVerdict: 含 blocked 标志 + risk_level + reason
        """
        return self._pipeline.check(tool_name, params)


class MockSecurityClassifier:
    """Mock 安全分级器 — 测试保留。

    所有操作标记为 safe，不阻断任何操作。
    """

    def classify(self, tool_name: str, params: dict) -> RiskLevel:
        return "safe"

    def check(self, tool_name: str, params: dict) -> SecurityVerdict:
        return SecurityVerdict(risk_level="safe", blocked=False)


def build_default_classifier() -> SecurityClassifier:
    """构建默认的 SecurityClassifier（含内置规则）。

    Returns:
        SecurityClassifier: 已配置 DenyList + Pattern + RiskClassifier
    """
    pipeline = SecurityPipeline()
    pipeline.register(DenyListRule())
    pipeline.register(CommandPatternRule())
    pipeline.register(RiskClassifierRule())
    return SecurityClassifier(pipeline)
