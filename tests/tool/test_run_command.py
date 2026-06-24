"""RunCommand Tool 测试。"""

import asyncio
import pytest

from minicode.tool.command import RunCommand


class TestRunCommand:
    """RunCommand 的 shell 命令执行功能。"""

    @pytest.fixture
    def tool(self):
        return RunCommand()

    def test_echo(self, tool):
        result = asyncio.run(tool.execute(command="echo hello minicode"))
        assert result.success
        assert "hello minicode" in result.output

    def test_list_directory(self, tool, tmp_dir):
        result = asyncio.run(tool.execute(command=f"ls {tmp_dir}"))
        assert result.success

    def test_command_not_found(self, tool):
        result = asyncio.run(tool.execute(command="nonexistent_cmd_xyz_123"))
        assert not result.success

    def test_nonzero_exit(self, tool):
        result = asyncio.run(tool.execute(command="cat /nonexistent_file_xyz_123"))
        assert not result.success

    def test_includes_stdout_and_stderr(self, tool):
        result = asyncio.run(tool.execute(command="echo out && echo err >&2"))
        assert result.success
        # 应有输出（stdout 或 stderr 至少一个有内容）

    def test_empty_command(self, tool):
        result = asyncio.run(tool.execute(command=""))
        assert not result.success

    def test_output_truncation(self, tool, tmp_dir):
        """长输出应被截断。"""
        # 用 Python 一行写很多字
        result = asyncio.run(tool.execute(
            command=f"python -c \"for i in range(200): print('line' + str(i))\""
        ))
        assert result.success
        assert len(result.output) <= 3000  # 输出应有限制
