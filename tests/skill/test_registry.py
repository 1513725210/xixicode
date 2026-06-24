"""MockSkillRegistry 单元测试。"""

import asyncio
import pytest

from minicode.skill.registry import MockSkillRegistry


class TestMockSkillRegistry:
    @pytest.fixture
    def registry(self):
        return MockSkillRegistry()

    def test_explore_is_default(self, registry):
        """未知任务返回 explore。"""
        assert asyncio.run(registry.select("随便看看")) == "explore"

    def test_select_explore(self, registry):
        assert asyncio.run(registry.select("分析项目架构")) == "explore"

    def test_select_bug_fix(self, registry):
        assert asyncio.run(registry.select("修复 NPE 错误")) == "bug_fix"

    def test_select_bug_fix_english(self, registry):
        assert asyncio.run(registry.select("fix the null pointer bug")) == "bug_fix"

    def test_select_refactor(self, registry):
        assert asyncio.run(registry.select("重构用户模块")) == "refactor"

    def test_select_code_review(self, registry):
        assert asyncio.run(registry.select("审查代码变更")) == "code_review"

    def test_select_write_test(self, registry):
        assert asyncio.run(registry.select("添加测试用例")) == "write_test"

    def test_list_all_skills(self, registry):
        skills = registry.list_skills()
        assert "bug_fix" in skills
        assert "refactor" in skills
        assert "code_review" in skills
        assert "write_test" in skills
        assert "explore" in skills
        assert len(skills) == 5

    def test_empty_task_returns_explore(self, registry):
        assert asyncio.run(registry.select("")) == "explore"
