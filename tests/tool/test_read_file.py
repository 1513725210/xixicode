"""ReadFile Tool 测试。"""

import asyncio
import pytest

from minicode.tool.file import ReadFile


class TestReadFile:
    """ReadFile 的文件读取功能。"""

    @pytest.fixture
    def tool(self):
        return ReadFile()

    def test_read_entire_file(self, tool, tmp_file):
        path = tmp_file("line1\nline2\nline3\n", "hello.txt")
        result = asyncio.run(tool.execute(path=str(path)))
        assert result.success
        assert "line1" in result.output
        assert "line3" in result.output

    def test_read_with_offset_and_limit(self, tool, tmp_file):
        content = "\n".join(f"line{i}" for i in range(10))
        path = tmp_file(content, "data.txt")
        result = asyncio.run(tool.execute(path=str(path), offset=2, limit=3))
        assert result.success
        assert "line2" in result.output
        assert "line3" in result.output
        assert "line4" in result.output
        assert "line5" not in result.output

    def test_read_nonexistent_file(self, tool, tmp_dir):
        result = asyncio.run(tool.execute(path=str(tmp_dir / "ghost.txt")))
        assert not result.success
        assert result.error is not None
        assert "不存在" in result.error or "找不到" in result.error

    def test_read_directory_fails(self, tool, tmp_dir):
        result = asyncio.run(tool.execute(path=str(tmp_dir)))
        assert not result.success

    def test_output_includes_line_numbers(self, tool, tmp_file):
        path = tmp_file("a\nb\nc\n", "lines.txt")
        result = asyncio.run(tool.execute(path=str(path)))
        assert result.success
        # 应包含行号标记
        assert any("1" in line or "│" in line for line in result.output.split("\n")[:3])

    def test_metadata_in_details(self, tool, tmp_file):
        path = tmp_file("hello\nworld", "meta.txt")
        result = asyncio.run(tool.execute(path=str(path)))
        assert result.success
        assert result.artifacts  # 应有元数据
        meta = result.artifacts[0]
        assert meta["path"] == str(path)
        assert meta["total_lines"] == 2
