"""Reflection Agent — 任务后反思与经验提取。

参考 MiniCode spec Section 11 的 Reflection Pipeline：
1. 任务结束后评估反思深度（跳过/轻量/深度/全量）
2. 调用 LLM 分析执行过程
3. 提取经验教训
4. 分类存储到 Memory（Procedural/Episodic/Knowledge）

触发条件：
  - 成功 + < 3 Tool 调用  → 跳过（仅记录 Episodic Memory）
  - 成功 + ≥ 3 Tool 调用  → 轻量反思（1 条 Procedural Memory）
  - 失败                 → 深度反思（Procedural + Episodic + 根因分析）
  - 用户显式 /reflect    → 全量反思
"""

from dataclasses import dataclass, field
from enum import Enum

from minicode.llm.client import LLMError


class ReflectionDepth(Enum):
    """反思深度级别。"""

    SKIP = "skip"           # 跳过反思
    LIGHT = "light"         # 轻量反思
    DEEP = "deep"           # 深度反思
    FULL = "full"           # 全量反思


@dataclass
class ReflectionResult:
    """反思结果。

    Attributes:
        depth: 使用的反思深度
        lessons: 提取的经验教训列表
        procedural_memories: 应存入 Procedural Memory 的内容
        knowledge_memories: 应存入 Knowledge Memory 的内容
        suggested_skill: 建议创建的新 Skill（如有）
        root_cause: 失败时的根因分析
        summary: 反思总结文本
    """

    depth: ReflectionDepth = ReflectionDepth.SKIP
    lessons: list[str] = field(default_factory=list)
    procedural_memories: list[str] = field(default_factory=list)
    knowledge_memories: list[str] = field(default_factory=list)
    suggested_skill: str | None = None
    root_cause: str | None = None
    summary: str = ""


class ReflectionAgent:
    """反思 Agent — 从任务执行中提取可复用经验。

    Usage:
        agent = ReflectionAgent(llm_client, memory_store)
        result = await agent.reflect(task, history, success=True)
    """

    REFLECTION_PROMPT = """你是一个 Coding Agent 的反思模块。分析以下任务执行过程，提取可复用的经验教训。

## 任务
{task}

## 执行历史
{history}

## 要求
1. 指出哪些步骤做得好（what worked）
2. 指出哪些步骤有问题（what failed）
3. 提炼 1-3 条可复用的经验（可用于未来的类似任务）
4. 评估是否值得创建一个新的 Skill
5. 用中文回答，控制在 300 字以内

输出格式：
{{
  "lessons": ["经验1", "经验2"],
  "procedural": ["应存入 Procedural Memory 的经验"],
  "knowledge": ["应存入 Knowledge Memory 的知识"],
  "suggested_skill": null,
  "summary": "总结文本"
}}
"""

    ROOT_CAUSE_PROMPT = """你是一个 Coding Agent 的根因分析模块。以下任务执行失败了，请分析根因。

## 任务
{task}

## 执行历史
{history}

## 要求
1. 找出失败的根本原因（root cause）
2. 区分是 Agent 策略问题还是环境/代码问题
3. 提出预防建议
4. 用中文回答，控制在 200 字以内
"""

    def __init__(self, llm_client, memory_store):
        """
        Args:
            llm_client: LLMClient 实例（需有 chat 方法）
            memory_store: MemoryStore 实例（需有 add_procedural, add_episodic 方法）
        """
        self._llm = llm_client
        self._memory = memory_store

    def determine_depth(
        self,
        success: bool,
        tool_count: int,
        user_requested: bool = False,
    ) -> ReflectionDepth:
        """根据执行结果判断反思深度。

        Args:
            success: 任务是否成功
            tool_count: Tool 调用次数
            user_requested: 用户是否显式请求反思 (/reflect)

        Returns:
            ReflectionDepth
        """
        if user_requested:
            return ReflectionDepth.FULL
        if not success:
            return ReflectionDepth.DEEP
        if tool_count >= 3:
            return ReflectionDepth.LIGHT
        return ReflectionDepth.SKIP

    async def reflect(
        self,
        task: str,
        history: list,
        success: bool = True,
        user_requested: bool = False,
    ) -> ReflectionResult:
        """执行反思流程。

        Args:
            task: 原始任务描述
            history: 执行历史（StepResult 列表或 dict 列表）
            success: 任务是否成功
            user_requested: 是否用户显式请求

        Returns:
            ReflectionResult
        """
        depth = self.determine_depth(success, len(history), user_requested)

        if depth == ReflectionDepth.SKIP:
            # 仅记录 Episodic Memory
            if hasattr(self._memory, "add_episodic"):
                await self._memory.add_episodic(
                    task=task,
                    step="completed",
                    tool=f"{len(history)} tools",
                    result="success",
                )
            return ReflectionResult(depth=depth, summary="任务简单，跳过反思。")

        # 构建执行历史文本
        history_text = self._format_history(history)

        # Light 反思
        if depth == ReflectionDepth.LIGHT:
            result = await self._run_reflection(task, history_text, self.REFLECTION_PROMPT)
            await self._store_memories(result)
            return result

        # Deep 反思
        if depth == ReflectionDepth.DEEP:
            result = await self._run_reflection(task, history_text, self.REFLECTION_PROMPT)
            root_cause = await self._run_root_cause(task, history_text)
            result.root_cause = root_cause
            result.depth = depth
            await self._store_memories(result)
            return result

        # Full 反思
        result = await self._run_reflection(task, history_text, self.REFLECTION_PROMPT)
        result.depth = depth
        if not success:
            root_cause = await self._run_root_cause(task, history_text)
            result.root_cause = root_cause
        await self._store_memories(result)
        return result

    async def _run_reflection(
        self, task: str, history_text: str, prompt_template: str
    ) -> ReflectionResult:
        """调用 LLM 执行反思。"""
        messages = [
            {"role": "system", "content": "你是 Coding Agent 反思模块。只输出合法 JSON。"},
            {
                "role": "user",
                "content": prompt_template.format(
                    task=task, history=history_text
                ),
            },
        ]

        try:
            response = await self._llm.chat(
                messages=messages,
                temperature=0.3,
                max_tokens=600,
            )
            import json

            content = response.content.strip()
            # 去除可能的 markdown 代码块（健壮版本）
            import re as _re
            m = _re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, _re.DOTALL)
            if m:
                content = m.group(1).strip()
            elif content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:]).strip()

            data = json.loads(content)

            return ReflectionResult(
                lessons=data.get("lessons", []),
                procedural_memories=data.get("procedural", []),
                knowledge_memories=data.get("knowledge", []),
                suggested_skill=data.get("suggested_skill"),
                summary=data.get("summary", ""),
            )
        except (LLMError, json.JSONDecodeError, KeyError):
            # LLM 不可用时的 fallback
            return ReflectionResult(
                lessons=[f"任务执行了 {history_text.count(chr(10))+1} 步"],
                summary="反思模块暂不可用（LLM 连接失败）。",
            )

    async def _run_root_cause(self, task: str, history_text: str) -> str:
        """分析失败根因。"""
        messages = [
            {"role": "system", "content": "你是根因分析专家。只输出分析文本，不要 JSON。"},
            {
                "role": "user",
                "content": self.ROOT_CAUSE_PROMPT.format(
                    task=task, history=history_text
                ),
            },
        ]

        try:
            response = await self._llm.chat(
                messages=messages,
                temperature=0.2,
                max_tokens=400,
            )
            return response.content.strip()
        except LLMError:
            return "根因分析不可用（LLM 连接失败）。"

    async def _store_memories(self, result: ReflectionResult) -> None:
        """将反思结果存入 Memory。"""
        store = self._memory

        # Procedural memories
        if hasattr(store, "add_procedural"):
            for lesson in result.procedural_memories:
                try:
                    await store.add_procedural(lesson)
                except Exception:
                    pass

        # Lessons as procedural
        if hasattr(store, "add_procedural"):
            for lesson in result.lessons:
                try:
                    await store.add_procedural(lesson)
                except Exception:
                    pass

        # Root cause as episodic
        if result.root_cause and hasattr(store, "add_episodic"):
            try:
                await store.add_episodic(
                    task="root_cause_analysis",
                    step="analyze",
                    tool="reflection",
                    result=result.root_cause,
                )
            except Exception:
                pass

    @staticmethod
    def _format_history(history: list) -> str:
        """将执行历史格式化为文本。"""
        if not history:
            return "（无执行历史）"

        lines = []
        for i, h in enumerate(history, 1):
            if hasattr(h, "description"):
                status = "+" if getattr(h, "success", False) else "x"
                lines.append(
                    f"  {i}. [{status}] {getattr(h, 'tool', '?')}: "
                    f"{h.description} → {getattr(h, 'output', '')[:150]}"
                )
            elif isinstance(h, dict):
                status = "+" if h.get("success", False) else "x"
                lines.append(
                    f"  {i}. [{status}] {h.get('tool', '?')}: "
                    f"{h.get('description', '')} → {h.get('output', '')[:150]}"
                )

        return "\n".join(lines) if lines else "（无执行历史）"
