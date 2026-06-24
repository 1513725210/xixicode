"""Skill Loader — YAML 文件加载。

从 skills/ 目录扫描 .yaml 文件，解析为 skill 字典。
每个 skill 含：name, description, system_prompt, tool_allowlist, tags。
"""

import os
from pathlib import Path

import yaml


def load_skill_from_yaml(path: str) -> dict | None:
    """从 YAML 文件加载单个 Skill 定义。

    Args:
        path: .yaml 文件路径

    Returns:
        dict | None: 成功返回 skill 字典，失败返回 None
    """
    file_path = Path(path)
    if not file_path.exists() or file_path.suffix not in (".yaml", ".yml"):
        return None

    try:
        text = file_path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
    except (yaml.YAMLError, OSError, UnicodeDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    # 必需字段
    name = data.get("name", "").strip()
    if not name:
        return None

    return {
        "name": name,
        "description": data.get("description", "").strip(),
        "system_prompt": data.get("system_prompt", "").strip(),
        "tool_allowlist": data.get("tool_allowlist", []),
        "tags": data.get("tags", []),
    }


def scan_skills_directory(directory: str) -> list[dict]:
    """扫描目录下所有 .yaml/.yml 文件并加载为 skill 定义。

    Args:
        directory: skills 目录路径

    Returns:
        list[dict]: 成功加载的 skill 列表
    """
    path = Path(directory)
    if not path.is_dir():
        return []

    skills = []
    for f in sorted(path.iterdir()):
        if f.suffix in (".yaml", ".yml"):
            skill = load_skill_from_yaml(str(f))
            if skill is not None:
                skills.append(skill)
    return skills
