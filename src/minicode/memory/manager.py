"""Memory Manager — Markdown+YAML 前言的持久化记忆。

参考 learn-claude-code s09 模式：
- .minicode/memory/ 目录，每条记忆一个 .md 文件
- 每个文件 = YAML 前言 + Markdown 正文
- MEMORY.md 索引文件 = 一行一个条目
- V1 用关键词匹配检索
"""

import os
import re
from pathlib import Path

import yaml


class MemoryManager:
    """管理基于文件的持久化记忆。

    文件格式：
        ---
        name: short-slug
        type: procedural|knowledge|user|episodic
        description: one-line summary
        ---
        body content here...
    """

    def __init__(self, memory_dir: str | None = None):
        if memory_dir is None:
            memory_dir = os.path.join(os.path.expanduser("~"), ".minicode", "memory")
        self._dir = Path(memory_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── 写入 ──

    def write(self, name: str, mem_type: str, description: str, body: str) -> Path:
        """写入一条记忆。

        Args:
            name: 记忆名称（显示用）
            mem_type: 类型 (procedural/knowledge/user/episodic)
            description: 一行摘要
            body: 正文内容

        Returns:
            Path: 写入的文件路径
        """
        slug = self._to_slug(name)
        file_path = self._dir / f"{slug}.md"

        # YAML 前言 + Markdown 正文
        frontmatter = {
            "name": name,
            "type": mem_type,
            "description": description,
        }
        yaml_block = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
        content = f"---\n{yaml_block}\n---\n\n{body}\n"
        file_path.write_text(content, encoding="utf-8")

        # 更新索引
        self._update_index(slug, name, mem_type, description)
        return file_path

    # ── 读取 ──

    def read(self, name: str) -> dict | None:
        """按名称（slug）读取一条记忆。

        Returns:
            dict | None: name, type, description, body, filename
        """
        slug = self._to_slug(name)
        file_path = self._dir / f"{slug}.md"
        if not file_path.exists():
            return None
        return self._parse_file(file_path)

    def read_index(self) -> dict[str, str]:
        """读取索引文件。

        Returns:
            dict: {slug: description}
        """
        index_path = self._dir / "MEMORY.md"
        if not index_path.exists():
            return {}
        result = {}
        text = index_path.read_text(encoding="utf-8")
        for line in text.strip().split("\n"):
            # 格式: - [name](file.md) — type: description
            match = re.match(r"- \[([^\]]+)\]\(([^)]+)\)\s*[-—]\s*(.+)", line)
            if match:
                name = match.group(1)
                filename = match.group(2)
                desc = match.group(3)
                slug = filename.replace(".md", "")
                result[slug] = desc
                result[name] = desc  # also index by display name
        return result

    # ── 检索 ──

    def search(self, query: str) -> list[dict]:
        """关键词检索相关记忆。

        V1: 简单关键词匹配（不区分大小写）。

        Args:
            query: 搜索查询

        Returns:
            list[dict]: 匹配的记忆列表
        """
        keywords = query.lower().split()
        results = []

        for f in sorted(self._dir.glob("*.md")):
            if f.name == "MEMORY.md":
                continue
            parsed = self._parse_file(f)
            if parsed is None:
                continue

            # 匹配名称、描述、正文
            text = (
                parsed["name"].lower() + " "
                + parsed.get("description", "").lower() + " "
                + parsed["body"].lower()
            )
            if any(kw in text for kw in keywords):
                results.append(parsed)

        return results

    # ── 内部 ──

    @staticmethod
    def _to_slug(name: str) -> str:
        """名称 → 文件名 slug。"""
        return re.sub(r"[^a-zA-Z0-9一-鿿]+", "-", name).strip("-").lower()

    def _parse_file(self, file_path: Path) -> dict | None:
        """解析一个 .md 记忆文件。"""
        try:
            text = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

        # 提取 YAML 前言
        match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
        if not match:
            return None
        try:
            meta = yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            return None
        body = match.group(2).strip()

        if not isinstance(meta, dict):
            return None

        return {
            "name": meta.get("name", file_path.stem),
            "type": meta.get("type", "knowledge"),
            "description": meta.get("description", ""),
            "body": body,
            "filename": file_path.name,
        }

    def _update_index(self, slug: str, name: str, mem_type: str, description: str):
        """更新 MEMORY.md 索引文件。"""
        index_path = self._dir / "MEMORY.md"
        filename = f"{slug}.md"

        # 读取现有索引
        existing = {}
        if index_path.exists():
            text = index_path.read_text(encoding="utf-8")
            for line in text.strip().split("\n"):
                if not line.startswith("- ["):
                    continue
                existing[line] = True

        # 生成新条目
        new_line = f"- [{name}]({filename}) — {mem_type}: {description}"

        # 去重写入
        all_lines = list(existing.keys())
        # 替换同名旧条目
        all_lines = [l for l in all_lines if f"({filename})" not in l]
        all_lines.append(new_line)

        index_path.write_text("\n".join(sorted(all_lines)) + "\n", encoding="utf-8")

    def _rebuild_index(self):
        """从所有 .md 文件重建索引。"""
        index_path = self._dir / "MEMORY.md"
        lines = []
        for f in sorted(self._dir.glob("*.md")):
            if f.name == "MEMORY.md":
                continue
            parsed = self._parse_file(f)
            if parsed:
                lines.append(
                    f"- [{parsed['name']}]({f.name})"
                    f" — {parsed['type']}: {parsed['description']}"
                )
        index_path.write_text("\n".join(sorted(lines)) + "\n", encoding="utf-8")
