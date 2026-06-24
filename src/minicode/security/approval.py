"""Approval — 安全层 Level 4: 用户审批。

从 main.py 中提取审批 UI 逻辑，提供独立的审批模块。
支持：批准/拒绝/全部批准/编辑/跳过/放弃。

审批流程：
1. Security Layer 3 (classifier) 标记风险等级
2. medium/high 操作触发审批请求
3. 审批模块生成 ApprovalRequest（含 diff 预览）
4. CLI 层展示审批 UI 并等待用户输入
5. 返回 ApprovalResult 决定是否执行
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Awaitable


class ApprovalAction(Enum):
    """用户审批动作。"""

    APPROVE = "approve"         # 批准本次执行
    REJECT = "reject"           # 拒绝，Agent 重新规划
    APPROVE_ALL = "approve_all" # 批准本次任务后续所有操作
    SKIP = "skip"               # 跳过此 Tool，继续下一步
    ABORT = "abort"             # 放弃整个任务
    EDIT = "edit"               # 打开编辑器修改后执行


@dataclass
class ApprovalRequest:
    """审批请求 — 包含审批 UI 所需的全部信息。

    Attributes:
        tool_name: 工具名
        risk_level: 风险等级 (medium/high)
        description: 操作描述
        diff_preview: 文件变更预览（EditFile/WriteFile 时显示）
        params: 工具参数
        file_path: 影响的文件路径
    """

    tool_name: str
    risk_level: str
    description: str = ""
    diff_preview: str = ""
    params: dict = field(default_factory=dict)
    file_path: str = ""

    def format_for_display(self) -> str:
        """生成 CLI 审批 UI 文本。"""
        lines = [
            f"  ⚠ High Risk Action",
            f"  Tool:  {self.tool_name}",
            f"  Risk:  {self.risk_level.upper()}",
        ]

        if self.file_path:
            lines.append(f"  File:  {self.file_path}")

        if self.description:
            lines.append(f"  Desc:  {self.description}")

        if self.diff_preview:
            lines.append(f"\n  Diff:")
            for diff_line in self.diff_preview.split("\n")[:20]:
                lines.append(f"    {diff_line}")

        lines.append(f"\n  Approve? [y/n/e/s/a] >")
        return "\n".join(lines)


@dataclass
class ApprovalResult:
    """审批结果。

    Attributes:
        action: 用户选择的动作
        approved: 简化布尔（仅 APPROVE/APPROVE_ALL 时 True）
        edited_params: 编辑后的参数（仅 EDIT 时有效）
    """

    action: ApprovalAction = ApprovalAction.REJECT
    approved: bool = False
    edited_params: dict | None = None


class ApprovalHandler:
    """审批处理器 — 管理审批流程。

    Usage:
        handler = ApprovalHandler(ui_callback=my_ui_func)
        result = await handler.request_approval(request)
    """

    def __init__(
        self,
        ui_callback: Callable[[ApprovalRequest], Awaitable[ApprovalResult]] | None = None,
    ):
        """
        Args:
            ui_callback: 自定义审批 UI 回调。
                         为 None 时使用默认 CLI 交互。
        """
        self._ui_callback = ui_callback
        self._approve_all = False  # 本次任务后续全部自动批准

    def reset(self) -> None:
        """重置审批状态（新任务开始时调用）。"""
        self._approve_all = False

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        """请求用户审批。

        如果已设置 approve_all，自动返回批准：
        默认 CLI 交互：
        - y: 批准
        - n: 拒绝
        - a: 全部批准（后续自动通过）
        - e: 编辑
        - s: 跳过
        - q: 放弃

        Args:
            request: 审批请求

        Returns:
            ApprovalResult
        """
        # 全部批准模式下自动通过
        if self._approve_all:
            return ApprovalResult(
                action=ApprovalAction.APPROVE,
                approved=True,
            )

        # 自定义 UI 回调
        if self._ui_callback:
            return await self._ui_callback(request)

        # 默认 sync CLI 交互
        return await self._default_cli_approval(request)

    async def _default_cli_approval(self, request: ApprovalRequest) -> ApprovalResult:
        """默认 CLI 审批交互。

        使用 asyncio.to_thread 避免阻塞事件循环。
        """
        print()
        print(request.format_for_display())

        try:
            choice = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("  > ").strip().lower()
            )
        except (KeyboardInterrupt, EOFError):
            return ApprovalResult(action=ApprovalAction.ABORT, approved=False)

        if choice in ("y", "yes", ""):
            return ApprovalResult(action=ApprovalAction.APPROVE, approved=True)
        elif choice in ("a", "all", "y all"):
            self._approve_all = True
            return ApprovalResult(action=ApprovalAction.APPROVE_ALL, approved=True)
        elif choice in ("s", "skip"):
            return ApprovalResult(action=ApprovalAction.SKIP, approved=False)
        elif choice in ("q", "abort", "quit"):
            return ApprovalResult(action=ApprovalAction.ABORT, approved=False)
        elif choice.startswith("e"):
            # 编辑模式下返回 REJECT + 提示重新输入
            return ApprovalResult(action=ApprovalAction.EDIT, approved=False)
        else:
            # 默认拒绝
            return ApprovalResult(action=ApprovalAction.REJECT, approved=False)

    @property
    def is_approve_all(self) -> bool:
        """是否处于全部批准模式。"""
        return self._approve_all


def build_approval_request(
    tool_name: str,
    risk_level: str,
    description: str = "",
    params: dict | None = None,
    diff_preview: str = "",
    file_path: str = "",
) -> ApprovalRequest:
    """构建审批请求的便捷函数。

    Args:
        tool_name: 工具名
        risk_level: 风险等级
        description: 操作描述
        params: 工具参数
        diff_preview: 变更预览
        file_path: 影响文件路径

    Returns:
        ApprovalRequest
    """
    return ApprovalRequest(
        tool_name=tool_name,
        risk_level=risk_level,
        description=description,
        params=params or {},
        diff_preview=diff_preview,
        file_path=file_path or params.get("path", "") if params else "",
    )
