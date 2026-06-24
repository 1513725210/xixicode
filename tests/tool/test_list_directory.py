"""ListDirectory Tool 测试。"""

import asyncio
import pytest

from minicode.tool.search import ListDirectory, SearchFile


class TestListDirectory:
    """ListDirectory 功能。"""

    @pytest.fixture
    def tool(self):
        return ListDirectory()

    def test_lists_files_and_dirs(self, tool, tmp_dir, tmp_file):
        tmp_file("content", "a.py")
        tmp_file("content", "b.py")
        (tmp_dir / "sub").mkdir()
        result = asyncio.run(tool.execute(path=str(tmp_dir)))
        assert result.success
        assert "a.py" in result.output
        assert "b.py" in result.output
        assert "sub" in result.output

    def test_nonexistent_path(self, tool):
        result = asyncio.run(tool.execute(path="/xyz/nonexistent"))
        assert not result.success

    def test_file_rejected(self, tool, tmp_file):
        path = tmp_file("hello", "f.txt")
        result = asyncio.run(tool.execute(path=str(path)))
        assert not result.success

    def test_empty_directory(self, tool, tmp_dir):
        result = asyncio.run(tool.execute(path=str(tmp_dir)))
        assert result.success

    def test_hidden_files_excluded(self, tool, tmp_dir, tmp_file):
        tmp_file("x", ".hidden")
        result = asyncio.run(tool.execute(path=str(tmp_dir)))
        assert result.success
        assert ".hidden" not in result.output

    def test_artifacts_has_counts(self, tool, tmp_dir, tmp_file):
        tmp_file("a", "f1.py")
        tmp_file("b", "f2.py")
        (tmp_dir / "subdir").mkdir()
        result = asyncio.run(tool.execute(path=str(tmp_dir)))
        assert result.success
        assert result.artifacts
        meta = result.artifacts[0]
        assert meta["files"] >= 2
        assert meta["dirs"] >= 1


class TestSearchFile:
    """SearchFile 功能。"""

    @pytest.fixture
    def tool(self):
        return SearchFile()

    def test_finds_py_files(self, tool, tmp_dir, tmp_file):
        tmp_file("x", "a.py")
        tmp_file("x", "b.py")
        tmp_file("x", "c.txt")
        result = asyncio.run(tool.execute(pattern="*.py", path=str(tmp_dir)))
        assert result.success
        assert "a.py" in result.output
        assert "b.py" in result.output
        assert "c.txt" not in result.output

    def test_no_match(self, tool, tmp_dir):
        result = asyncio.run(tool.execute(pattern="*.rs", path=str(tmp_dir)))
        assert result.success
        assert "未找到" in result.output or "0" in result.output
