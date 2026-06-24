"""Security Pipeline — 安全规则编排。

按注册顺序执行规则。阻断优先：任一规则 blocked=True 立即返回。
否则合并所有规则的风险等级（取最高）。
"""

from minicode.security.rules import SecurityVerdict


class SecurityPipeline:
    """安全规则流水线。

    规则按注册顺序执行：
    - 阻断规则（DenyList、Pattern）先注册 → 阻断优先
    - 分级规则（RiskClassifier）后注册 → 不影响阻断结论
    """

    def __init__(self):
        self._rules: list = []

    def register(self, rule) -> None:
        """注册一条安全规则。

        Args:
            rule: 实现 SecurityRule 协议的对象（有 check 方法）
        """
        self._rules.append(rule)

    def check(self, tool_name: str, params: dict) -> SecurityVerdict:
        """执行所有规则，返回合并后的安全结论。

        Args:
            tool_name: 工具名称
            params: 工具参数

        Returns:
            SecurityVerdict: 合并后的结论
        """
        final = SecurityVerdict()

        for rule in self._rules:
            try:
                verdict = rule.check(tool_name=tool_name, **params)
            except Exception:
                # 规则本身出错不阻塞流程
                continue

            if verdict is None:
                continue

            if verdict.blocked:
                # 阻断优先 — 立即返回
                final.blocked = True
                final.reason = verdict.reason
                final.risk_level = "high"
                return final

            # 合并风险等级（取最高）
            if _risk_weight(verdict.risk_level) > _risk_weight(final.risk_level):
                final.risk_level = verdict.risk_level
                final.reason = final.reason or verdict.reason

        return final


def _risk_weight(level: str) -> int:
    """风险等级权重。"""
    return {"safe": 0, "medium": 1, "high": 2}.get(level, 1)
