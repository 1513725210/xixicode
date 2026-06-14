"""Mock ContextBuilder — 构建 LLM 上下文。

V1 第一阶段：返回固定上下文。
后续接入 Memory 检索 + Prompt 模板拼装。
"""


class MockContextBuilder:
    """Mock 上下文构建器。"""

    async def build(self, task: str, memories: list) -> dict:
        """构建 Agent 上下文。

        Args:
            task: 用户任务
            memories: 检索到的相关记忆

        Returns:
            dict: 组装好的上下文
        """
        return {
            "task": task,
            "memories": [m.content for m in memories],
            "skill_prompt": "",
            "history_summary": "",
        }
