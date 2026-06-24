"""Planner — 任务拆解。

KeywordPlanner: 基于关键词匹配（测试/离线用）
LLMPlanner: LLM 驱动的推理规划（生产用）

核心方法:
- next_step(context) → NextAction  —— 每步评估"下一步做什么"（真正的 Agent 循环）
- plan(task) → Plan                —— 一次性规划（保留兼容）
"""

import json
from dataclasses import dataclass, field

from minicode.llm.client import LLMError


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
        "create": [
            ("确认目标目录", "list_directory", {"path": "."}),
            ("创建文件", "write_file", {"path": "output.txt", "content": ""}),
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
        if any(kw in tl for kw in ["create", "创建", "写", "生成", "新建", "添加文件", "写入", "touch"]):
            return "create"
        return "explore"

    @staticmethod
    def _extract_filename(task: str) -> str:
        """从任务描述中尝试提取文件名。

        策略：匹配常见文件名模式 *.txt, *.py, *.md 等。
        """
        import re
        # 匹配 xxx.xxx 模式的文件名
        m = re.search(r"([\w\-一-鿿]+\.(?:txt|py|md|json|js|ts|yaml|yml|toml|csv|html|css|sh|bat))", task)
        if m:
            return m.group(1)
        # 匹配 "叫/名为 xxx" 的模式
        m = re.search(r"(?:叫|名为|命名为?|文件名?[是为]?)\s*[\"']?([^\"'\s]+)", task)
        if m:
            name = m.group(1)
            # 如果有常见扩展名就用，否则默认 .txt
            return name if "." in name else name + ".txt"
        return "output.txt"

    async def next_step(self, context: LoopContext, system_prompt: str | None = None) -> NextAction:
        """基于关键词和已执行历史返回下一步动作。

        Args:
            context: 当前循环上下文
            system_prompt: 可选（KeywordPlanner 不使用，保持接口兼容）

        Returns:
            NextAction: 下一步（或 done=True）
        """
        category = self._classify(context.task)
        steps = self._PLANS.get(category, self._PLANS["explore"])
        idx = len(context.history)

        if idx >= len(steps) or idx >= context.max_steps:
            return NextAction(done=True, reasoning=f"已完成全部 {len(steps)} 步")

        desc, tool, params = steps[idx]

        # 对 create 计划，动态替换文件名
        if category == "create" and tool == "write_file" and params.get("path") == "output.txt":
            filename = self._extract_filename(context.task)
            params = {**params, "path": filename}

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

    async def synthesize(self, context: LoopContext) -> str:
        """基于执行历史合成最终回答（离线模式）。

        Args:
            context: 循环上下文（含完整执行历史）

        Returns:
            str: 人类可读的总结
        """
        if not context.history:
            return "未执行任何步骤。"

        lines = [f"## 任务执行总结\n"]
        lines.append(f"**任务:** {context.task}\n")
        lines.append(f"**执行步数:** {len(context.history)}\n")

        successes = [h for h in context.history if h.success]
        failures = [h for h in context.history if not h.success]
        lines.append(f"**成功:** {len(successes)} 步，**失败:** {len(failures)} 步\n")

        lines.append("### 执行过程\n")
        for h in context.history:
            icon = "+" if h.success else "x"
            lines.append(f"- {icon} [{h.tool}] {h.description}")
            if h.output:
                # 摘要: 取输出的第一行或前 80 字符
                first_line = h.output.split("\n")[0][:120]
                lines.append(f"  → {first_line}")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# LLMPlanner — 生产用（DeepSeek API 驱动）
# ═══════════════════════════════════════════════════════════


class LLMPlanner:
    """LLM 驱动的任务规划器。

    每次 next_step() 调用 LLM 评估：
    "基于当前任务和执行历史，下一步该做什么？"

    LLM 不可用时的 fallback 策略：
    - 第 1-2 次失败: 尝试不同的探索工具
    - 第 3 次失败: 返回 done=true，清晰报错
    """

    # ── LLM 不可用时的智能 fallback 工具序列 ──
    _FALLBACK_TOOLS = [
        ("list_directory", {"path": "."}, "浏览项目结构"),
        ("search_file", {"pattern": "*.py", "path": "."}, "查找 Python 源文件"),
        ("git_status", {}, "检查 Git 变更"),
    ]

    AVAILABLE_TOOLS = [
        {"name": "list_directory", "description": "列出目录内容", "params": {"path": "目录路径"}},
        {"name": "read_file", "description": "读取文件内容", "params": {"path": "文件路径"}},
        {"name": "grep", "description": "搜索文件内容 (正则)", "params": {"pattern": "搜索模式", "path": "搜索目录"}},
        {"name": "search_file", "description": "按文件名搜索", "params": {"pattern": "文件名模式", "path": "搜索目录"}},
        {"name": "edit_file", "description": "SEARCH/REPLACE 精确编辑", "params": {"path": "文件路径", "search": "原文本", "replace": "新文本"}},
        {"name": "patch_file", "description": "批量 SEARCH/REPLACE 替换", "params": {"path": "文件路径", "replacements": [{"search": "原文本", "replace": "新文本"}]}},
        {"name": "modify_file", "description": "用新内容完整替换文件", "params": {"path": "文件路径", "content": "新内容"}},
        {"name": "write_file", "description": "写入/创建文件", "params": {"path": "文件路径", "content": "内容"}},
        {"name": "run_command", "description": "执行 shell 命令", "params": {"command": "命令字符串"}},
        {"name": "run_test", "description": "运行测试", "params": {"target": "测试目标"}},
        {"name": "git_status", "description": "Git 工作区状态", "params": {}},
        {"name": "git_diff", "description": "Git 差异", "params": {}},
        {"name": "git_log", "description": "Git 提交历史", "params": {"count": "条数"}},
        {"name": "web_fetch", "description": "获取网页内容", "params": {"url": "URL地址"}},
        {"name": "web_search", "description": "搜索网页", "params": {"query": "搜索关键词"}},
        {"name": "ask_user", "description": "向用户提问并等待回复", "params": {"question": "问题文本"}},
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
        # 连续失败计数器（LLM 错误 和 JSON 解析错误 共用）
        self._consecutive_failures: int = 0
        # Provider usage 累积
        self.accumulated_prompt_tokens: int = 0
        self.accumulated_completion_tokens: int = 0
        self.llm_call_count: int = 0

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """从 LLM 响应中提取 JSON，支持多种常见格式。

        策略（按优先级）：
        1. ```json ... ``` 代码块
        2. ``` ... ``` 代码块
        3. 以 { 开头以 } 结尾的裸 JSON
        4. 文本中首个 { 到末个 } 之间的内容（处理 LLM 在 JSON 前后加说明文字）
        """
        import re

        # 策略 1: ```json ... ``` 代码块
        m = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 策略 2: ``` ... ``` 代码块
        m = re.search(r"```\s*\n(.*?)\n\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 策略 3: 直接尝试解析全文
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # 策略 4: 找到第一个 { 和最后一个 }，提取中间内容
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        # 策略 5: 尝试修复常见错误（单引号、尾部逗号等）
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            # 替换单引号为双引号
            fixed = re.sub(r"(?<!\\)'([^']*?)(?<!\\)'", r'"\1"', candidate)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass

        return None

    async def next_step(self, context: LoopContext, system_prompt: str | None = None) -> NextAction:
        """调用 LLM 决定下一步动作。

        Args:
            context: 当前循环上下文（含历史）
            system_prompt: 可选的自定义 system prompt（由 ContextBuilder 提供）

        Returns:
            NextAction: 下一步动作或完成信号
        """
        # 新任务开始 → 重置失败计数器
        if len(context.history) == 0:
            self._consecutive_failures = 0

        # 强制 max_steps 检查（LLM 可能忽略 prompt 中的限制）
        if len(context.history) >= context.max_steps:
            return NextAction(
                done=True,
                reasoning=f"已达最大步数上限 ({context.max_steps})",
            )

        tools_json = json.dumps(self.AVAILABLE_TOOLS, ensure_ascii=False, indent=2)
        if system_prompt:
            system_prompt = system_prompt + f"\n\n可用 Tool：\n{tools_json}"
        else:
            system_prompt = self.SYSTEM_PROMPT.format(tools_json=tools_json)

        # 构建执行历史
        history_lines = []
        for h in context.history:
            status = "+" if h.success else "x"
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

        try:
            response = await self.llm.chat(
                messages=messages,
                model="deepseek-chat",
                temperature=0.1,
                max_tokens=512,
            )
        except LLMError as e:
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                return NextAction(
                    done=True,
                    reasoning=(
                        f"LLM API 连续 {self._consecutive_failures} 次调用失败 ({e.message})。"
                        "请检查 API Key 是否有效、网络是否正常。"
                    ),
                )
            idx = (self._consecutive_failures - 1) % len(self._FALLBACK_TOOLS)
            tool_name, params, desc = self._FALLBACK_TOOLS[idx]
            return NextAction(
                done=False,
                tool=tool_name,
                params=params,
                description=f"{desc}（LLM 不可用，使用本地策略）",
                reasoning=f"LLM 调用失败 ({e.message})，fallback #{self._consecutive_failures}",
            )

        # ── LLM 调用成功 → 累积 token ──
        self.accumulated_prompt_tokens += getattr(response, "prompt_tokens", 0)
        self.accumulated_completion_tokens += getattr(response, "completion_tokens", 0)
        self.llm_call_count += 1

        # ── 安全的 content 提取 ──
        try:
            content = response.content.strip()
        except AttributeError:
            self._consecutive_failures += 1
            return NextAction(
                done=False,
                tool="list_directory",
                params={"path": "."},
                description="探索项目结构（LLM 响应格式异常）",
                reasoning="LLM 响应缺少 content 字段",
            )

        # ── JSON 提取（多策略，处理各种 LLM 响应格式）──
        import re
        data = self._extract_json(content)
        if data is None:
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                return NextAction(
                    done=True,
                    reasoning=(
                        f"LLM 连续 {self._consecutive_failures} 次返回无法解析的响应。"
                        "已自动降级到本地 KeywordPlanner 模式。"
                        "请检查: 1) API Key 是否有效 2) 模型是否兼容。"
                    ),
                )
            idx = (self._consecutive_failures - 1) % len(self._FALLBACK_TOOLS)
            tool_name, params, desc = self._FALLBACK_TOOLS[idx]
            return NextAction(
                done=False,
                tool=tool_name,
                params=params,
                description=f"{desc}（LLM JSON 解析失败）",
                reasoning=f"JSON 解析失败 (尝试 #{self._consecutive_failures})",
            )

        if data.get("done", False):
            return NextAction(
                done=True,
                reasoning=data.get("reasoning", "任务完成"),
            )

        # 验证 tool 名称
        tool = data.get("tool", "")
        valid_tools = {t["name"] for t in self.AVAILABLE_TOOLS}
        if tool not in valid_tools:
            tool = "list_directory"

        return NextAction(
            done=False,
            tool=tool,
            params=data.get("params") or {},
            description=data.get("description", "探索"),
            reasoning=data.get("reasoning", ""),
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

        try:
            response = await self.llm.chat(messages=messages, temperature=0.1, max_tokens=1024)
        except LLMError as e:
            return Plan(
                reasoning=f"LLM 不可用: {e.message}",
                steps=[
                    PlanStep("探索项目结构", "list_directory", {"path": "."}),
                    PlanStep("阅读关键文件", "read_file", {"path": "src/"}),
                ],
            )

        try:
            content = response.content.strip()
            data = self._extract_json(content)
            if data is None:
                raise json.JSONDecodeError("No JSON found", content, 0)
            steps = [PlanStep(s["description"], s["tool"], s.get("params", {})) for s in data.get("steps", [])]
            return Plan(reasoning=data.get("reasoning", ""), steps=steps)
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            return Plan(
                reasoning="Fallback plan",
                steps=[
                    PlanStep("探索项目结构", "list_directory", {"path": "."}),
                    PlanStep("阅读关键文件", "read_file", {"path": "src/"}),
                ],
            )

    # ── Synthesize: 合成最终回答 ──

    SYNTHESIZE_PROMPT = """你是一个 Coding Agent。用户给了你一个任务，你已经执行了一系列步骤来探索/分析/修改代码。

现在，请基于执行历史，**用中文写一段简洁的总结回答**。要求：

1. 直接回应用户最可能的意图（理解项目、定位问题、分析代码等）
2. 点出关键发现、重要文件、值得注意的地方
3. 结构化：用小标题分段，用列表而非大段文字
4. 控制在 500 字以内
5. 如果执行中有失败步骤，诚实说明

不用复述每个步骤的细节——给用户一个"结论"而非"流水账"。
"""

    async def synthesize(self, context: LoopContext) -> str:
        """基于执行历史合成最终回答（LLM 模式）。

        Args:
            context: 循环上下文（含完整执行历史）

        Returns:
            str: LLM 合成的总结
        """
        if not context.history:
            return "未执行任何步骤。"

        # 构建历史摘要
        history_lines = []
        for h in context.history:
            status = "+" if h.success else "x"
            history_lines.append(
                f"  {h.step}. [{status}] {h.tool}: {h.description}\n"
                f"     输出: {h.output[:200]}"
            )
        history_text = "\n".join(history_lines)

        messages = [
            {"role": "system", "content": self.SYNTHESIZE_PROMPT},
            {"role": "user", "content": f"任务: {context.task}\n\n执行历史:\n{history_text}"},
        ]

        try:
            response = await self.llm.chat(
                messages=messages,
                temperature=0.3,
                max_tokens=800,
            )
            return response.content.strip()
        except Exception:
            # LLM 不可用时 fallback 到简单摘要
            lines = [f"## {context.task}\n"]
            successes = [h for h in context.history if h.success]
            for h in context.history:
                icon = "+" if h.success else "x"
                lines.append(f"- {icon} [{h.tool}] {h.description}")
                if h.output:
                    lines.append(f"  → {h.output.split(chr(10))[0][:120]}")
            return "\n".join(lines)
