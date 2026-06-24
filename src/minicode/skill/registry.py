"""Skill Registry — 技能注册与选择。

SkillRegistry: 从 YAML 文件加载技能定义（双层注入模式）
  Tier 1: name + description 进 system prompt（始终可见）
  Tier 2: system_prompt + tool_allowlist 选中后注入（按需）

MockSkillRegistry: 测试保留，硬编码 5 个技能。
"""

import os
from pathlib import Path

from minicode.skill.loader import scan_skills_directory


class SkillRegistry:
    """文件驱动的技能注册表。

    从 skills/ 目录加载 YAML 文件，
    select() 用关键词匹配选择技能。
    """

    def __init__(self, skills_dir: str | None = None):
        """
        Args:
            skills_dir: 技能 YAML 文件目录。默认查找项目内 skills/builtins/。
        """
        if skills_dir is None:
            # 从包位置推导 skills 目录
            package_dir = Path(__file__).parent.parent.parent.parent
            skills_dir = str(package_dir / "skills" / "builtins")

        self._skills: dict[str, dict] = {}
        loaded = scan_skills_directory(skills_dir)
        for s in loaded:
            self._skills[s["name"]] = s

    def get_skill(self, name: str) -> dict | None:
        """获取完整的 Skill 定义。

        Returns:
            dict | None: name, description, system_prompt, tool_allowlist, tags
        """
        return self._skills.get(name)

    def list_skills(self) -> list[str]:
        """列出所有已注册技能的名称。"""
        return list(self._skills.keys())

    def list_catalog(self) -> list[dict]:
        """返回 Tier 1 目录（name + description），用于注入 system prompt。

        Returns:
            list[dict]: [{"name": ..., "description": ...}, ...]
        """
        return [
            {"name": s["name"], "description": s["description"]}
            for s in self._skills.values()
        ]

    async def select(self, task: str) -> str:
        """根据任务关键词选择最合适的技能。

        Args:
            task: 用户任务描述

        Returns:
            str: 技能名称
        """
        task_lower = task.lower()

        # 关键词 → 技能名 映射
        if any(kw in task_lower for kw in ["架构", "arch", "结构", "explore", "分析", "overview", "项目", "代码库", "看看"]):
            if "explore" in self._skills:
                return "explore"
        if any(kw in task_lower for kw in ["refactor", "重构"]):
            if "refactor" in self._skills:
                return "refactor"
        if any(kw in task_lower for kw in ["review", "审查", "review"]):
            if "code_review" in self._skills:
                return "code_review"
        if any(kw in task_lower for kw in ["test", "测试"]):
            if "write_test" in self._skills:
                return "write_test"
        if any(kw in task_lower for kw in ["fix", "修复", "bug", "npe", "错误", "exception"]):
            if "bug_fix" in self._skills:
                return "bug_fix"

        # 默认
        return "explore" if "explore" in self._skills else list(self._skills.keys())[0]


class MockSkillRegistry:
    """Mock 技能注册表 — 测试保留。"""

    SKILLS = {
        "explore": "分析项目架构、理解代码库组织方式",
        "bug_fix": "定位并修复代码中的 Bug",
        "refactor": "重构代码，改善结构不改变行为",
        "code_review": "审查代码变更",
        "write_test": "为代码编写测试用例",
    }

    async def select(self, task: str) -> str:
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
        return "explore"

    def list_skills(self) -> list[str]:
        return list(self.SKILLS.keys())
