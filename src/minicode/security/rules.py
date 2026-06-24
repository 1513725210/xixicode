"""Security Rules — 可组合的安全规则。

每个规则是一个 callable，接收工具名和参数，返回 None（无意见）或 SecurityVerdict。
规则之间互不感知，由 SecurityPipeline 统一编排。
"""

from dataclasses import dataclass, field
from typing import Protocol


class SecurityRule(Protocol):
    """安全规则协议。"""

    def check(self, **params) -> "SecurityVerdict | None":
        """检查工具调用。

        Returns:
            SecurityVerdict | None: 有风险结论则返回，无意见则返回 None
        """
        ...


@dataclass
class SecurityVerdict:
    """安全检查结论。

    Attributes:
        risk_level: 风险等级 (safe/medium/high)
        blocked: 是否阻断执行
        reason: 阻断或分级原因
    """

    risk_level: str = "safe"
    blocked: bool = False
    reason: str | None = None


# ── 内置规则 ──


class DenyListRule:
    """命令黑名单 — 匹配到即阻断。

    检查 params 中的 command 字段，与硬编码的危险模式比较。
    """

    BLOCKED = [
        "rm -rf",
        "sudo ",
        "sudo\t",
        "shutdown",
        "mkfs.",
        "mkfs ",
        "dd if=",
        "> /dev/sd",
        "> /dev/hd",
        "> /dev/nvme",
        "> /dev/xvd",
        ":(){ :|:& };:",   # fork bomb
    ]

    def check(self, **params) -> SecurityVerdict | None:
        command = params.get("command", "")
        if not isinstance(command, str) or not command:
            return None

        for pattern in self.BLOCKED:
            if pattern in command:
                return SecurityVerdict(
                    risk_level="high",
                    blocked=True,
                    reason=f"命令包含危险模式 ({pattern}): {command[:80]}",
                )
        return None


class CommandPatternRule:
    """命令模式匹配 — 检测可疑命令组合。

    检查 curl/wget 管道到 shell、chmod 777 等模式。
    这些不是绝对危险，但需要用户确认。
    """

    PATTERNS = [
        (r"curl ", r"| bash", "curl 管道到 bash"),
        (r"curl ", r"| sh", "curl 管道到 sh"),
        (r"wget ", r"| bash", "wget 管道到 bash"),
        (r"wget ", r"| sh", "wget 管道到 sh"),
        (r"chmod 777", None, "chmod 777 权限过于开放"),
        (r"chmod -R 777", None, "递归 chmod 777"),
        (r"> /etc/", None, "写入 /etc/ 系统目录"),
        (r"eval ", None, "eval 命令"),
    ]

    def check(self, **params) -> SecurityVerdict | None:
        command = params.get("command", "")
        if not isinstance(command, str) or not command:
            return None

        for pattern_a, pattern_b, desc in self.PATTERNS:
            if pattern_a in command:
                if pattern_b is None or pattern_b in command:
                    return SecurityVerdict(
                        risk_level="high",
                        blocked=True,
                        reason=f"可疑命令模式 ({desc}): {command[:80]}",
                    )
        return None


class RiskClassifierRule:
    """基于工具名的风险分级。

    不阻断执行，只标记风险等级供审批流程使用。
    """

    # 按工具名预设的风险等级
    RISK_MAP = {
        # 只读
        "read_file": "safe",
        "grep": "safe",
        "search_file": "safe",
        "list_directory": "safe",
        "git_status": "safe",
        "git_diff": "safe",
        "git_log": "safe",
        "git_show": "safe",
        "web_fetch": "safe",
        "web_search": "safe",
        "ask_user": "safe",
        # 中等风险
        "run_test": "medium",
        # 高风险（修改文件系统）
        "run_command": "high",
        "write_file": "high",
        "edit_file": "high",
        "patch_file": "high",
        "modify_file": "high",
    }

    def check(self, **params) -> SecurityVerdict | None:
        tool_name = params.get("tool_name", "")
        if not tool_name:
            return None

        risk = self.RISK_MAP.get(tool_name, "medium")
        return SecurityVerdict(
            risk_level=risk,
            blocked=False,
            reason=f"工具 {tool_name} 风险等级: {risk}",
        )
