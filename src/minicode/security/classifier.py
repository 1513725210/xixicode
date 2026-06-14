"""Mock SecurityClassifier — 安全分级。

V1 第一阶段：所有操作归类为 "safe"。
后续接入真实的命令黑名单、注入检测、风险分级。
"""

from typing import Literal

RiskLevel = Literal["safe", "medium", "high"]


class MockSecurityClassifier:
    """Mock 安全分级器。

    当前阶段：所有 Tool 调用都标记为 safe，无需审批。
    真实实现将在 Security Layer 1-4 中逐步添加。
    """

    # 高风险命令模式（V1 后续阶段启用）
    BLOCKED_PATTERNS = [
        "rm -rf",
        "sudo ",
        "shutdown",
        "mkfs.",
        "dd if=",
        "> /dev/",
    ]

    def classify(self, tool_name: str, params: dict) -> RiskLevel:
        """对 Tool 调用进行风险分级。

        Args:
            tool_name: 工具名称
            params: 工具参数

        Returns:
            RiskLevel: 当前 Mock 始终返回 "safe"
        """
        # Mock: 所有操作安全
        # 真实实现会检查 params 中的命令模式、文件路径等
        return "safe"

    def check_command(self, command: str) -> bool:
        """检查 shell 命令是否在黑名单中。

        Returns:
            bool: True = 允许执行, False = 阻断
        """
        for pattern in self.BLOCKED_PATTERNS:
            if pattern in command:
                return False
        return True
