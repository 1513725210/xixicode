"""Grep Tool 测试 — 正则内容搜索。"""

import asyncio
import pytest

from minicode.tool.search import Grep


class TestGrep:
    """Grep 的文件内容搜索功能。"""

    @pytest.fixture
    def tool(self):
        return Grep()

    @pytest.fixture
    def project(self, tmp_file):
        """创建模拟项目结构。"""
        tmp_file("class OrderService:\n    def create(self): pass\n", "src/order.py")
        tmp_file("class UserService:\n    def find(self): pass\n    def create(self): pass\n", "src/user.py")
        tmp_file("import unittest\n", "tests/test_order.py")
        tmp_file("README\nno code here\n", "README.md")

    def test_find_matches(self, tool, tmp_dir, project):
        result = asyncio.run(tool.execute(pattern="class \\w+Service", path=str(tmp_dir)))
        assert result.success
        assert "order.py" in result.output
        assert "user.py" in result.output

    def test_no_matches(self, tool, tmp_dir, project):
        result = asyncio.run(tool.execute(pattern="NO_SUCH_THING_XYZ", path=str(tmp_dir)))
        assert result.success
        assert "0 处" in result.output or "未找到" in result.output

    def test_glob_filter(self, tool, tmp_dir, project):
        result = asyncio.run(tool.execute(pattern="def ", path=str(tmp_dir), glob="*.py"))
        assert result.success
        assert "order.py" in result.output  # def create
        assert "README.md" not in result.output

    def test_includes_line_numbers(self, tool, tmp_dir, project):
        result = asyncio.run(tool.execute(pattern="class", path=str(tmp_dir)))
        assert result.success
        # 每行匹配应有行号
        output = result.output
        assert any(char.isdigit() for char in output[:50])

    def test_invalid_regex(self, tool, tmp_dir):
        result = asyncio.run(tool.execute(pattern="[invalid", path=str(tmp_dir)))
        assert not result.success
        assert result.error is not None

    def test_nonexistent_path(self, tool):
        result = asyncio.run(tool.execute(pattern="x", path="/nonexistent/path/xyz"))
        assert not result.success

    def test_multiline_pattern(self, tool, tmp_file, tmp_dir):
        path = tmp_file("line1\nline2\nline3\n", "f.py")
        result = asyncio.run(tool.execute(pattern="line2", path=str(tmp_dir)))
        assert result.success
        assert "line2" in result.output
