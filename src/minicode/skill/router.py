"""Skill Router — 基于 LLM 的 Skill 选择。

参考 MiniCode skills.ts 和 spec Section 8 的设计：
  V1: LLM 直接选择（Skill < 20 个，全部 name+description 放入 prompt）
  V2: 两阶段 Embedding Recall + LLM Rerank（Skill > 30 个）

当前 V1 实现：
- build_skill_prompt(): 将 Skill 目录注入 system prompt
- LLMSkillRouter: 调用 LLM 选择最匹配的 Skill
"""

from minicode.llm.client import LLMError


def build_skill_catalog_prompt(skills: list[dict]) -> str:
    """构建 Skill 目录 prompt 片段。

    将所有 Skill 的 name + description 格式化为 LLM 可读的列表。
    用于注入 system prompt 的 "Available Skills" 段。

    Args:
        skills: Skill 列表，每个含 name, description

    Returns:
        str: 格式化的 Skill 目录文本
    """
    if not skills:
        return "（无可用 Skill）"

    lines = ["## 可用 Skill"]
    for s in skills:
        name = s.get("name", "unknown")
        desc = s.get("description", "")
        lines.append(f"- **{name}**: {desc}")

    return "\n".join(lines)


class SkillRouter:
    """基于 LLM 的 Skill 路由器。

    给 LLM 一个简短的 prompt，让它从 Skill 目录中选择最合适的。

    Usage:
        router = SkillRouter(llm_client)
        skill_name = await router.select(task_description, skill_catalog)
    """

    SELECT_PROMPT = """根据用户任务，从可用 Skill 列表中选择最合适的一个。

用户任务：{task}

可用 Skill：
{skills}

规则：
1. 只返回一个 Skill 名称（精确匹配列表中的名称）
2. 如果多个 Skill 都适用，选择最专门/最匹配的那个
3. 如果都不匹配，返回 "explore"
4. 不要返回 JSON，只返回 Skill 名称文本"""

    def __init__(self, llm_client):
        """
        Args:
            llm_client: LLMClient 实例 (需有 chat 方法)
        """
        self._llm = llm_client

    async def select(self, task: str, skill_catalog: list[dict]) -> str:
        """调用 LLM 选择最合适的 Skill。

        Args:
            task: 用户任务描述
            skill_catalog: Skill 目录列表 [{name, description}, ...]

        Returns:
            str: 选中的 Skill 名称
        """
        if not skill_catalog:
            return "explore"

        # 只有 1 个 Skill → 无需 LLM 选择
        if len(skill_catalog) == 1:
            return skill_catalog[0]["name"]

        # 构建 Skill 列表文本
        skill_lines = []
        skill_names = []
        for s in skill_catalog:
            name = s.get("name", "unknown")
            desc = s.get("description", "")
            skill_lines.append(f"  - {name}: {desc}")
            skill_names.append(name)

        skills_text = "\n".join(skill_lines)

        messages = [
            {
                "role": "system",
                "content": "你是 Skill 路由器。根据用户任务选择最合适的 Skill。只返回 Skill 名称，不要其他内容。",
            },
            {
                "role": "user",
                "content": self.SELECT_PROMPT.format(task=task, skills=skills_text),
            },
        ]

        try:
            response = await self._llm.chat(
                messages=messages,
                temperature=0.0,
                max_tokens=32,
            )
            chosen = response.content.strip().lower()

            # 尝试精确匹配
            for name in skill_names:
                if name.lower() == chosen or name.lower() in chosen:
                    return name

            # 模糊匹配
            for name in skill_names:
                if chosen in name.lower():
                    return name

            # Fallback
            return "explore" if "explore" in skill_names else skill_names[0]

        except LLMError:
            # LLM 不可用时回退到第一个 Skill
            return "explore" if "explore" in skill_names else skill_names[0]


class KeywordSkillRouter:
    """基于关键词的 Skill 路由器（离线/测试用）。

    不依赖 LLM，纯关键词匹配选择 Skill。
    """

    KEYWORD_MAP = {
        "explore": ["架构", "arch", "结构", "分析", "overview", "项目", "代码库", "看看"],
        "bug_fix": ["fix", "修复", "bug", "npe", "错误", "exception"],
        "refactor": ["refactor", "重构"],
        "code_review": ["review", "审查"],
        "write_test": ["test", "测试"],
    }

    async def select(self, task: str, skill_catalog: list[dict]) -> str:
        """基于关键词选择 Skill。

        Args:
            task: 用户任务描述
            skill_catalog: Skill 目录

        Returns:
            str: 选中的 Skill 名称
        """
        task_lower = task.lower()
        available_names = {s["name"] for s in skill_catalog}

        for skill_name, keywords in self.KEYWORD_MAP.items():
            if skill_name not in available_names:
                continue
            if any(kw in task_lower for kw in keywords):
                return skill_name

        return "explore" if "explore" in available_names else list(available_names)[0]
