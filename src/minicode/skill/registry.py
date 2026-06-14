"""Mock SkillRegistry — 返回固定 Skill。

V1 第一阶段：Skill 选择用 Mock。
后续接入真正的 Skill 文件加载和 LLM 路由。
"""


class MockSkillRegistry:
    """Mock 技能注册表。

    始终返回 "bug_fix" 作为选中技能。
    """

    SKILLS = {
        "explore": "分析项目架构、理解代码库组织方式",
        "bug_fix": "定位并修复代码中的 Bug",
        "refactor": "重构代码，改善结构不改变行为",
        "code_review": "审查代码变更",
        "write_test": "为代码编写测试用例",
    }

    async def select(self, task: str) -> str:
        """Mock 技能选择。

        Args:
            task: 用户任务描述

        Returns:
            str: 技能名称 (始终返回 "bug_fix")
        """
        task_lower = task.lower()
        if any(kw in task_lower for kw in ["架构", "arch", "结构", "explore", "分析", "overview", "项目"]):
            return "explore"
        if "refactor" in task_lower or "重构" in task_lower:
            return "refactor"
        if "review" in task_lower or "审查" in task_lower:
            return "code_review"
        if "test" in task_lower or "测试" in task_lower:
            return "write_test"
        if "fix" in task_lower or "修复" in task_lower or "bug" in task_lower or "npe" in task_lower:
            return "bug_fix"
        # 模糊任务默认走 explore 而非 bug_fix
        return "explore"

    def list_skills(self) -> list[str]:
        """列出所有可用 Skill。"""
        return list(self.SKILLS.keys())
