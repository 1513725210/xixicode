"""ContextBuilder — 基于 Jinja2 模板构建 LLM 上下文。

将 task、tools、memories、skill_prompt 等各段
通过 Jinja2 模板拼装为完整的 system prompt 字符串。
"""

import os
from pathlib import Path
from typing import Any

import jinja2


class ContextBuilder:
    """LLM 上下文构建器。

    使用 Jinja2 模板将各信息段组装为 system prompt。
    模板变量：
    - workspace: 工作目录
    - task: 用户任务
    - tools: 可用工具列表 [{name, description, ...}]
    - memories: 相关记忆列表 [{name, body, ...}]
    - skill_prompt: 当前技能指导文本
    - history: 执行历史摘要
    """

    # 内置 Fallback 模板（模板文件不存在时使用）
    _FALLBACK_TEMPLATE = """你是一个 Coding Agent。

## 当前任务
{{ task }}

## 可用工具
{% for t in tools %}
- {{ t.name }}: {{ t.description }}{% endfor %}
{% if skill_prompt %}
## 技能指导
{{ skill_prompt }}
{% endif %}
{% if memories %}
## 相关记忆
{% for m in memories %}
- {{ m.name }}: {{ m.body }}
{% endfor %}
{% endif %}
"""

    def __init__(self, template_dir: str | None = None):
        """
        Args:
            template_dir: Jinja2 模板目录路径。默认从包内推导。
        """
        if template_dir is None:
            template_dir = os.path.join(
                os.path.dirname(__file__), "templates"
            )

        self._template_dir = template_dir
        self._env: jinja2.Environment | None = None

        # 尝试加载模板文件
        try:
            loader = jinja2.FileSystemLoader(template_dir)
            self._env = jinja2.Environment(
                loader=loader,
                autoescape=False,
                undefined=jinja2.StrictUndefined,
            )
            self._template = self._env.get_template("system.j2")
        except (jinja2.TemplateNotFound, jinja2.TemplateError, OSError):
            self._env = jinja2.Environment(autoescape=False)
            self._template = self._env.from_string(self._FALLBACK_TEMPLATE)

    def build(
        self,
        task: str = "",
        workspace: str = "",
        tools: list[dict[str, Any]] | None = None,
        memories: list[Any] | None = None,
        skill_prompt: str = "",
        history: str = "",
    ) -> str:
        """构建 system prompt 字符串。

        Args:
            task: 用户任务描述
            workspace: 当前工作目录
            tools: 可用工具列表
            memories: 相关记忆条目 (有 name, body 属性或 dict)
            skill_prompt: 当前技能的指导 prompt
            history: 执行历史摘要文本

        Returns:
            str: 组装好的 system prompt
        """
        tools = tools or []
        memories = memories or []

        # 标准化 memories: 支持 object 和 dict
        normalized_memories = []
        for m in memories:
            if isinstance(m, dict):
                normalized_memories.append(m)
            else:
                normalized_memories.append({
                    "name": getattr(m, "name", ""),
                    "body": getattr(m, "body", getattr(m, "content", "")),
                })

        try:
            return self._template.render(
                task=task,
                workspace=workspace or os.getcwd(),
                tools=tools,
                memories=normalized_memories,
                skill_prompt=skill_prompt,
                history=history,
            )
        except jinja2.TemplateError:
            # 渲染失败时用 fallback
            return self._FALLBACK_TEMPLATE.replace("{{ task }}", task)


class MockContextBuilder:
    """Mock 上下文构建器 — 测试保留。

    接口兼容真实 ContextBuilder，接受相同 kwargs 但返回固定 prompt 字符串。
    """

    async def build(
        self,
        task: str = "",
        workspace: str = "",
        tools: list | None = None,
        memories: list | None = None,
        skill_prompt: str = "",
        history: str = "",
    ) -> str:
        """Mock 构建 — 返回简单系统提示。

        Returns:
            str: 简单拼接的 prompt
        """
        return (
            f"你是一个 Coding Agent。\n"
            f"任务: {task}\n"
            f"工作目录: {workspace}\n"
        )
