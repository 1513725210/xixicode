"""EditFile Tool 测试 — SEARCH/REPLACE 精确编辑。"""

import asyncio
import pytest

from minicode.tool.file import EditFile


class TestEditFile:
    """EditFile 的 SEARCH/REPLACE 功能。"""

    @pytest.fixture
    def tool(self):
        return EditFile()

    def test_replace_single_occurrence(self, tool, tmp_file):
        path = tmp_file("old_value = 42\n", "code.py")
        result = asyncio.run(tool.execute(
            path=str(path), search="old_value = 42", replace="old_value = 99"
        ))
        assert result.success
        assert "old_value = 99" in path.read_text()
        assert "old_value = 42" not in path.read_text()

    def test_search_not_found(self, tool, tmp_file):
        path = tmp_file("hello world\n", "f.txt")
        result = asyncio.run(tool.execute(
            path=str(path), search="nonexistent", replace="x"
        ))
        assert not result.success
        assert "SEARCH" in result.error and ("找到" in result.error or "未在" in result.error)

    def test_search_matches_multiple_times(self, tool, tmp_file):
        path = tmp_file("x = 1\ny = 1\nx = 2\n", "dup.py")
        result = asyncio.run(tool.execute(
            path=str(path), search="1", replace="99"
        ))
        assert not result.success
        assert "2 次" in result.error or "多次" in result.error

    def test_nonexistent_file(self, tool, tmp_dir):
        result = asyncio.run(tool.execute(
            path=str(tmp_dir / "no.txt"), search="a", replace="b"
        ))
        assert not result.success

    def test_directory_rejected(self, tool, tmp_dir):
        result = asyncio.run(tool.execute(
            path=str(tmp_dir), search="a", replace="b"
        ))
        assert not result.success

    def test_multiline_replace(self, tool, tmp_file):
        path = tmp_file("def old():\n    pass\n", "func.py")
        result = asyncio.run(tool.execute(
            path=str(path),
            search="def old():\n    pass",
            replace="def new():\n    return True",
        ))
        assert result.success
        content = path.read_text()
        assert "def new()" in content
        assert "return True" in content
        assert "def old()" not in content

    def test_diff_summary_in_output(self, tool, tmp_file):
        path = tmp_file("AAA\nBBB\n", "diff_test.txt")
        result = asyncio.run(tool.execute(
            path=str(path),
            search="AAA",
            replace="CCC",
        ))
        assert result.success
        assert "删除" in result.output or "added" in result.output or "行" in result.output

    def test_preserves_other_content(self, tool, tmp_file):
        content = "import os\n\n# TODO: fix this\ndef main():\n    pass\n"
        path = tmp_file(content, "app.py")
        result = asyncio.run(tool.execute(
            path=str(path),
            search="# TODO: fix this",
            replace="# TODO: fixed",
        ))
        assert result.success
        new_content = path.read_text()
        assert "# TODO: fixed" in new_content
        assert "import os" in new_content
        assert "def main()" in new_content
        assert "# TODO: fix this" not in new_content
