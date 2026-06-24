"""Tool 测试共享夹具 — 临时文件/目录。"""

import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def tmp_dir():
    """在系统临时目录创建独立的测试目录。

    每个测试有独立目录，测试结束后自动清理。
    """
    with tempfile.TemporaryDirectory(prefix="minicode_test_") as d:
        yield Path(d)


@pytest.fixture
def tmp_file(tmp_dir):
    """临时目录中创建一个可写入的测试文件。

    Returns:
        函数: 调用时接受 (content, name) → 返回文件 Path
    """
    def _create(content: str = "", name: str = "test.txt") -> Path:
        path = tmp_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path
    return _create
