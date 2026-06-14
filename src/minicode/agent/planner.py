"""Planner — 任务拆解。

KeywordPlanner: 基于关键词匹配（测试/离线用）
LLMPlanner: LLM 驱动的推理规划（生产用）

核心方法:
- next_step(context) → NextAction  —— 每步评估"下一步做什么"（真正的 Agent 循环）
- plan(task) → Plan                —— 一次性规划（保留兼容）
"""

import json
from dataclasses import dataclass, field


@dataclass
class PlanStep:
    """计划中的一个步骤."""

    description: str
    tool: str
    params: dict = field(default_factory=dict)


@dataclass
class Plan:
    """任务执行计划（一次性规划用，保留兼容）。"""

    steps: list[PlanStep]
    reasoning: str = ""

    def __len__(self) -> int:
        return len(self.steps)


@dataclass
class NextAction:
    """每步评估的下一步动作。

    Attributes:
        done: True = 任务完成
        tool: 下一步 Tool 名称
        params: Tool 参数
        description: 人类可读的步骤描述
        reasoning: LLM 推理过程
    """

    done: bool = False
    tool: str | None = None
    params: dict | None = None
    description: str = ""
    reasoning: str = ""


@dataclass
class StepResult:
    """已完成步骤的结果，用于构建上下文历史。"""

    step: int
    tool: str
    description: str
    success: bool
    output: str


@dataclass
class LoopContext:
    """Loop 上下文，在每轮 next_step() 时传递。"""

    task: str
    history: list[StepResult] = field(default_factory=list)
    memories: list = field(default_factory=list)
    max_steps: int = 10


# ═══════════════════════════════════════════════════════════
# KeywordPlanner — 测试/离线用
# ═══════════════════════════════════════════════════════════


class KeywordPlanner:
    """基于关键词的任务规划器 — 用于测试和离线模式。"""

    # 预定义的步骤序列（按关键词分类）
    _PLANS: dict[str, list[tuple[str, str, dict]]] = {
        "fix": [
            ("定位相关源代码", "grep", {"pattern": "TODO", "path": "src/"}),
            ("阅读可疑源文件", "read_file", {"path": "src/"}),
            ("应用修复", "edit_file", {"path": "src/"}),
            ("运行测试验证", "run_test", {"target": "all"}),
        ],
        "refactor": [
            ("分析当前代码结构", "read_file", {"path": "src/"}),
            ("应用重构", "edit_file", {"path": "src/"}),
            ("验证行为不变", "run_test", {"target": "all"}),
        ],
        "test": [
            ("分析测试目标", "read_file", {"path": "src/"}),
            ("编写测试用例", "write_file", {"path": "tests/"}),
            ("运行测试", "run_test", {"target": "all"}),
        ],
        "explore": [
            ("获取项目顶层目录结构", "list_directory", {"path": "."}),
            ("识别关键模块和入口文件", "read_file", {"path": "src/"}),
            ("分析依赖和架构特征", "grep", {"pattern": "import |from ", "path": "src/", "glob": "*.py"}),
        ],
    }

    def _classify(self, task: str) -> str:
        """关键词分类。"""
        tl = task.lower()
        if any(kw in tl for kw in ["fix", "修复", "npe", "bug"]):
            return "fix"
        if any(kw in tl for kw in ["refactor", "重构"]):
            return "refactor"
        if any(kw in tl for kw in ["test", "测试"]):
            return "test"
        return "explore"

    async def next_step(self, context: LoopContext) -> NextAction:
        """基于关键词和已执行历史返回下一步动作。

        Args:
            context: 当前循环上下文

        Returns:
            NextAction: 下一步（或 done=True）
        """
        category = self._classify(context.task)
        steps = self._PLANS.get(category, self._PLANS["explore"])
        idx = len(context.history)

        if idx >= len(steps) or idx >= context.max_steps:
            return NextAction(done=True, reasoning=f"已完成全部 {len(steps)} 步")

        desc, tool, params = steps[idx]
        return NextAction(
            done=False,
            tool=tool,
            params=params,
            description=desc,
            reasoning=f"KeywordPlanner: 第 {idx+1}/{len(steps)} 步",
        )

    async def plan(self, task: str) -> Plan:
        """一次性规划（保留兼容旧接口）。"""
        category = self._classify(task)
        steps_data = self._PLANS.get(category, self._PLANS["explore"])
        steps = [PlanStep(d, t, p) for d, t, p in steps_data]
        return Plan(reasoning=f"KeywordPlanner: {category} flow", steps=steps)


# ═══════════════════════════════════════════════════════════
# LLMPlanner — 生产用（DeepSeek API 驱动）
# ═══════════════════════════════════════════════════════════


class LLMPlanner:
    """LLM 驱动的任务规划器。

    每次 next_step() 调用 LLM 评估：
    "基于当前任务和执行历史，下一步该做什么？"
    """

    AVAILABLE_TOOLS = [
        {"name": "list_directory", "description": "列出目录内容", "params": {"path": "目录路径"}},
        {"name": "read_file", "description": "读取文件内容", "params": {"path": "文件路径"}},
        {"name": "grep", "description": "搜索文件内容 (正则)", "params": {"pattern": "搜索模式", "path": "搜索目录"}},
        {"name": "search_file", "description": "按文件名搜索", "params": {"pattern": "文件名模式", "path": "搜索目录"}},
        {"name": "edit_file", "description": "SEARCH/REPLACE 精确编辑", "params": {"path": "文件路径", "search": "原文本", "replace": "新文本"}},
        {"name": "write_file", "description": "写入/创建文件", "params": {"path": "文件路径", "content": "内容"}},
        {"name": "run_command", "description": "执行 shell 命令", "params": {"command": "命令字符串"}},
        {"name": "run_test", "description": "运行测试", "params": {"target": "测试目标"}},
        {"name": "git_status", "description": "Git 工作区状态", "params": {}},
        {"name": "git_diff", "description": "Git 差异", "params": {}},
        {"name": "git_log", "description": "Git 提交历史", "params": {"count": "条数"}},
    ]

    SYSTEM_PROMPT = """你是一个 Coding Agent 的执行规划器。你的任务是根据执行历史，决定下一步应该做什么。

规则：
1. 每次只返回一个步骤（不是整个计划），因为执行完这步后会再次询问你
2. 仔细阅读执行历史——如果上一步失败，考虑换策略；如果最近几步结果相似，说明信息已足够，返回 done: true
3. 优先探索（读文件、搜索）再修改
4. 如果已有足够信息回答用户，立即返回 done: true，不要继续探索
5. 步骤总数不要超过 8 步
6. 不要重复执行已经做过的操作——如果同一步已经成功，不要再来一次
7. 输出必须是合法 JSON，不要包含 markdown 代码块

可用 Tool：
{tools_json}

输出格式（严格遵守）：
{{"done": false, "tool": "工具名", "params": {{"key": "value"}}, "description": "步骤描述", "reasoning": "为什么选择这一步"}}

或完成时：
{{"done": true, "reasoning": "任务完成的原因"}}
"""

    NEXT_STEP_PROMPT = """任务：{task}

已执行步骤：
{history}

现在应该执行哪一步？"""

    def __init__(self, llm_client):
        self.llm = llm_client

    async def next_step(self, context: LoopContext) -> NextAction:
        """调用 LLM 决定下一步动作。

        Args:
            context: 当前循环上下文（含历史）

        Returns:
            NextAction: 下一步动作或完成信号
        """
        tools_json = json.dumps(self.AVAILABLE_TOOLS, ensure_ascii=False, indent=2)
        system_prompt = self.SYSTEM_PROMPT.format(tools_json=tools_json)

        # 构建执行历史
        history_lines = []
        for h in context.history:
            status = "✓" if h.success else "✗"
            history_lines.append(
                f"  {h.step}. [{status}] {h.tool}: {h.description} → {h.output[:150]}"
            )
        history_text = "\n".join(history_lines) if history_lines else "（尚未执行任何步骤）"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self.NEXT_STEP_PROMPT.format(
                task=context.task,
                history=history_text,
            )},
        ]

        response = await self.llm.chat(
            messages=messages,
            model="deepseek-chat",
            temperature=0.1,
            max_tokens=512,
        )

        try:
            content = response.content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            data = json.loads(content)

            if data.get("done", False):
                return NextAction(
                    done=True,
                    reasoning=data.get("reasoning", "任务完成"),
                )

            return NextAction(
                done=False,
                tool=data.get("tool", "list_directory"),
                params=data.get("params", {"path": "."}),
                description=data.get("description", "探索"),
                reasoning=data.get("reasoning", ""),
            )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # 解析失败时返回一个安全的探索动作
            return NextAction(
                done=False,
                tool="list_directory",
                params={"path": "."},
                description="探索项目结构（fallback）",
                reasoning=f"LLM 响应解析失败: {e}",
            )

    async def plan(self, task: str) -> Plan:
        """一次性规划（保留兼容旧接口）。"""
        # 简单调用 next_step 几次来构建完整 Plan
        # 对于旧接口调用，用一次性 prompt
        tools_json = json.dumps(self.AVAILABLE_TOOLS, ensure_ascii=False, indent=2)

        prompt = """你是一个 Coding Agent 的任务规划器。将用户任务拆解为 1-5 个可执行步骤。

可用 Tool：
{tools_json}

输出格式：
{{"reasoning": "推理", "steps": [{{"description": "...", "tool": "...", "params": {{}}}}]}}
"""
        messages = [
            {"role": "system", "content": prompt.format(tools_json=tools_json)},
            {"role": "user", "content": f"任务：{task}"},
        ]

        response = await self.llm.chat(messages=messages, temperature=0.1, max_tokens=1024)

        try:
            content = response.content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            data = json.loads(content)
            steps = [PlanStep(s["description"], s["tool"], s.get("params", {})) for s in data.get("steps", [])]
            return Plan(reasoning=data.get("reasoning", ""), steps=steps)
        except (json.JSONDecodeError, KeyError, TypeError):
            return Plan(
                reasoning="Fallback plan",
                steps=[
                    PlanStep("探索项目结构", "list_directory", {"path": "."}),
                    PlanStep("阅读关键文件", "read_file", {"path": "src/"}),
                ],
            )
