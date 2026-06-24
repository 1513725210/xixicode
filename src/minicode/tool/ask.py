"""Ask User Tool — Agent 向用户提问。

参考 MiniCode ask-user.ts：
- Tool 执行后设置 awaitUser=True
- Agent Loop 检测到 awaitUser 后暂停当前回合
- 用户回复后继续

这个 Tool 是 Agent 与用户交互的唯一渠道（除了审批流）。
"""

from minicode.tool.base import Tool, ToolResult


class AskUser(Tool):
    """向用户提问 — 暂停当前回合等待回复。

    参考 MiniCode ask-user.ts：
    - 所有参数中只有 question 是必需的
    - 执行后 ToolResult.awaitUser = True
    - Agent Loop 检测到此标志后暂停并等待用户输入
    """

    name = "ask_user"
    description = (
        "向用户提问并暂停等待回复。当需要用户澄清需求、"
        "确认选择或提供额外信息时使用。"
    )
    parameters = {
        "question": "要问用户的问题",
    }
    risk_level = "safe"

    async def execute(self, question: str) -> ToolResult:
        """提出一个问题并等待用户回复。

        Args:
            question: 问题文本

        Returns:
            ToolResult: ok=True, awaitUser=True, output=question
        """
        q = question.strip()
        if not q:
            return ToolResult(
                ok=False, output="", error="问题不能为空",
            )

        return ToolResult(
            ok=True,
            output=q,
            awaitUser=True,
        )
