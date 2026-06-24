"""ContextBuilder 测试 — Jinja2 模板拼装。"""

import pytest
from pathlib import Path

from minicode.context.builder import ContextBuilder


@pytest.fixture
def template_dir():
    return Path(__file__).parent.parent.parent / "src" / "minicode" / "context" / "templates"


class TestContextBuilder:
    """ContextBuilder 的模板渲染功能。"""

    @pytest.fixture
    def builder(self, template_dir):
        return ContextBuilder(template_dir=str(template_dir))

    def test_renders_with_task_and_workspace(self, builder):
        result = builder.build(task="修复 Bug", workspace="/home/user/repo")
        assert "修复 Bug" in result
        assert "/home/user/repo" in result

    def test_renders_tools(self, builder):
        tools = [
            {"name": "read_file", "description": "读取文件"},
            {"name": "grep", "description": "搜索内容"},
        ]
        result = builder.build(task="x", workspace="/tmp", tools=tools)
        assert "read_file" in result
        assert "搜索内容" in result
        assert "grep" in result

    def test_renders_memories(self, builder):
        class Mem:
            name = "NPE 经验"
            body = "NPE → 先检查 DTO mapping"
        result = builder.build(task="x", workspace="/tmp", memories=[Mem()])
        assert "NPE 经验" in result
        assert "DTO mapping" in result

    def test_renders_skill_prompt(self, builder):
        result = builder.build(
            task="x", workspace="/tmp",
            skill_prompt="你是 Bug 修复专家。仅使用 read_file、grep、edit_file。"
        )
        assert "Bug 修复专家" in result
        assert "read_file" in result

    def test_no_skill_section_when_empty(self, builder):
        result = builder.build(task="x", workspace="/tmp")
        assert "当前技能指导" not in result

    def test_no_memory_section_when_empty(self, builder):
        result = builder.build(task="x", workspace="/tmp")
        assert "相关记忆" not in result

    def test_renders_history(self, builder):
        result = builder.build(task="x", workspace="/tmp", history="1. [+] read_file...")
        assert "执行历史" in result
        assert "read_file" in result

    def test_empty_fields_dont_crash(self, builder):
        """空值不应导致模板错误。"""
        result = builder.build(task="", workspace="")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_string_not_dict(self, builder):
        result = builder.build(task="test", workspace="/tmp")
        assert isinstance(result, str)
        assert len(result) > 50  # 应有实质内容


class TestContextBuilderEdgeCases:
    """ContextBuilder 边界情况。"""

    @pytest.fixture
    def builder(self, template_dir):
        return ContextBuilder(template_dir=str(template_dir))

    def test_missing_template_dir(self):
        """模板目录不存在时 fallback。"""
        cb = ContextBuilder(template_dir="/nonexistent/templates")
        result = cb.build(task="test", workspace="/tmp")
        assert isinstance(result, str)
        assert "Coding Agent" in result  # fallback 消息

    def test_large_input_doesnt_crash(self, builder):
        result = builder.build(
            task="分析项目" * 100,
            workspace="/tmp",
            tools=[{"name": f"tool_{i}", "description": f"desc_{i}"} for i in range(50)],
        )
        assert isinstance(result, str)

    def test_special_characters_in_task(self, builder):
        """特殊字符不应破坏模板。"""
        result = builder.build(
            task='修复 OrderService 的 NullPointerException (NPE) -- 用户报 "系统崩溃"',
            workspace="/tmp"
        )
        assert "OrderService" in result
        assert "NullPointerException" in result
