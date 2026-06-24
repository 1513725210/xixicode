"""Skill Loader 测试 — YAML 文件加载。"""

import pytest
from pathlib import Path

from minicode.skill.loader import load_skill_from_yaml, scan_skills_directory


@pytest.fixture
def skills_dir():
    return Path(__file__).parent.parent.parent / "skills" / "builtins"


class TestLoadSkillFromYaml:
    def test_load_explore(self, skills_dir):
        path = skills_dir / "explore.yaml"
        skill = load_skill_from_yaml(str(path))
        assert skill is not None
        assert skill["name"] == "explore"
        assert "项目结构" in skill["description"]
        assert "system_prompt" in skill
        assert "tool_allowlist" in skill
        assert "list_directory" in skill["tool_allowlist"]
        assert "read_file" in skill["tool_allowlist"]

    def test_load_bug_fix(self, skills_dir):
        path = skills_dir / "bug_fix.yaml"
        skill = load_skill_from_yaml(str(path))
        assert skill["name"] == "bug_fix"
        assert "edit_file" in skill["tool_allowlist"]
        assert "run_test" in skill["tool_allowlist"]
        assert "Bug" in skill["system_prompt"]

    def test_load_refactor(self, skills_dir):
        path = skills_dir / "refactor.yaml"
        skill = load_skill_from_yaml(str(path))
        assert skill["name"] == "refactor"
        assert "write_file" in skill["tool_allowlist"]

    def test_load_write_test(self, skills_dir):
        path = skills_dir / "write_test.yaml"
        skill = load_skill_from_yaml(str(path))
        assert skill["name"] == "write_test"

    def test_load_code_review(self, skills_dir):
        path = skills_dir / "code_review.yaml"
        skill = load_skill_from_yaml(str(path))
        assert skill["name"] == "code_review"
        # code_review 不应包含写操作 tool
        assert "edit_file" not in skill["tool_allowlist"]
        assert "write_file" not in skill["tool_allowlist"]
        assert "git_diff" in skill["tool_allowlist"]

    def test_load_nonexistent_file(self):
        skill = load_skill_from_yaml("/nonexistent/path.yaml")
        assert skill is None

    def test_load_invalid_yaml(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text(": : : : broken: [")
        skill = load_skill_from_yaml(str(bad))
        assert skill is None


class TestScanSkillsDirectory:
    def test_scans_builtins(self, skills_dir):
        skills = scan_skills_directory(str(skills_dir))
        names = {s["name"] for s in skills}
        assert "explore" in names
        assert "bug_fix" in names
        assert "refactor" in names
        assert "write_test" in names
        assert "code_review" in names
        assert len(skills) == 5

    def test_empty_directory(self, tmp_path):
        skills = scan_skills_directory(str(tmp_path))
        assert skills == []

    def test_skips_non_yaml(self, skills_dir, tmp_path):
        # 应忽略非 .yaml 文件
        readme = tmp_path / "README.md"
        readme.write_text("not a skill")
        skills = scan_skills_directory(str(tmp_path))
        assert len(skills) == 0

    def test_nonexistent_directory(self):
        skills = scan_skills_directory("/nonexistent/dir")
        assert skills == []
