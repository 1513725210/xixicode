"""MemoryManager 测试 — Markdown+YAML 持久化。"""

import pytest
from pathlib import Path

from minicode.memory.manager import MemoryManager


@pytest.fixture
def manager(tmp_path):
    return MemoryManager(memory_dir=str(tmp_path / ".minicode" / "memory"))


class TestMemoryManager:
    def test_write_and_read(self, manager):
        manager.write("NPE经验", "procedural", "NPE发生时先检查DTO mapping", "NPE → DTO mapping")
        mem = manager.read("npe经验")
        assert mem is not None
        assert mem["name"] == "NPE经验"
        assert mem["type"] == "procedural"
        assert "DTO mapping" in mem["body"]

    def test_index_is_maintained(self, manager):
        manager.write("skill1", "knowledge", "desc1", "body1")
        manager.write("skill2", "procedural", "desc2", "body2")
        index = manager.read_index()
        assert len(index) >= 2
        assert "skill1" in index
        assert "skill2" in index

    def test_search_keyword_match(self, manager):
        manager.write("Java编码规范", "knowledge", "使用Java 17+", "详细规范内容...")
        manager.write("Python测试", "procedural", "pytest fixture用法", "pytest 内容...")
        manager.write("NPE修复经验", "procedural", "NPE→检查DTO", "NPE 修复步骤...")

        results = manager.search("NPE")
        assert len(results) == 1
        assert "NPE" in results[0]["name"]

        results = manager.search("python")
        assert len(results) >= 1

    def test_search_no_match(self, manager):
        results = manager.search("xyz_nonexistent_keyword")
        assert results == []

    def test_empty_store(self, manager):
        results = manager.search("anything")
        assert results == []

    def test_read_nonexistent(self, manager):
        assert manager.read("ghost") is None

    def test_overwrite_updates(self, manager):
        manager.write("note", "knowledge", "desc1", "old body")
        manager.write("note", "knowledge", "desc2", "new body")
        mem = manager.read("note")
        assert mem["body"] == "new body"
        assert "desc2" in mem["description"]

    def test_names_are_slugs(self, manager):
        """名称中的空格应转为 slug。"""
        manager.write("Java Spring 规范", "knowledge", "desc", "body")
        mem = manager.read("java-spring-规范")
        assert mem is not None

    def test_index_rebuild(self, manager):
        manager.write("a", "knowledge", "desc a", "body a")
        manager.write("b", "procedural", "desc b", "body b")
        # 删除 index 文件后重建
        index_path = manager._dir / "MEMORY.md"
        index_path.unlink()
        manager._rebuild_index()
        index = manager.read_index()
        assert "a" in index
        assert "b" in index
