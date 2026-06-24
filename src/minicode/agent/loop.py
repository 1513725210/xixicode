"""Query Loop — MiniCode 核心执行引擎。

真正的 while 循环架构：

    while not task_completed:
        update_context()       # 检索 Memory + 构建上下文
        next_action = planner.next_step(context)  # LLM: "下一步做什么？"
        if next_action.done: break
        security check         # 风险分级
        if risky: await approval  # asyncio.Event 阻塞等待审批
        execute()              # 调用 Tool（try/except 容错）
        observe()              # 记录结果到历史

每步执行完让 LLM 重新评估，而不是一次性规划全部步骤。
"""

import asyncio
import inspect
from typing import AsyncIterator

from minicode.events import AgentEvent
from minicode.agent.planner import NextAction, StepResult, LoopContext


class QueryLoop:
    """MiniCode 核心 Agent 循环。

    接收用户任务，通过 Planner → Skill → Tool 管道执行，
    整个过程持续 yield AgentEvent 供 CLI 层渲染。
    """

    # 审批等待超时（秒）
    _APPROVAL_TIMEOUT = 300

    def __init__(
        self,
        planner,
        skill_registry,
        tool_executor,
        memory_store,
        context_builder,
        security_classifier,
        auto_approve: bool = False,
        no_memory: bool = False,
    ):
        self.planner = planner
        self.skill_registry = skill_registry
        self.tool_executor = tool_executor
        self.memory_store = memory_store
        self.context_builder = context_builder
        self.security_classifier = security_classifier
        self._auto_approve = auto_approve
        self._no_memory = no_memory

        self.step_count = 0
        self.tool_count = 0

    async def run(self, task: str) -> AsyncIterator[AgentEvent]:
        """执行真正的 Query Loop — 每步 LLM 重评估。

        Args:
            task: 用户任务描述

        Yields:
            AgentEvent: 流式事件
        """
        self.step_count = 0
        self.tool_count = 0

        # ── 用户输入事件 ──
        yield AgentEvent(
            type="user",
            message=task,
            detail={"phase": "input"},
        )

        # ── 注入检测（Security Layer 2）──
        try:
            from minicode.security.injection import detect_injection
            injection_verdict = detect_injection(task, tool_name="", params={})
            if injection_verdict.detected:
                yield AgentEvent(
                    type="need_approval",
                    message=f"检测到可能的注入攻击 [{injection_verdict.risk_level.upper()}]: {', '.join(injection_verdict.patterns_matched[:3])}",
                    detail={
                        "injection_detected": True,
                        "risk_level": injection_verdict.risk_level,
                        "patterns": injection_verdict.patterns_matched,
                    },
                )
        except Exception:
            # 注入检测失败不影响主流程
            pass

        # ── 初始分析 ──
        yield AgentEvent(type="thinking", message="分析中...", detail={"phase": "planning"})
        memories = await self.memory_store.search(task, top_k=3) if not self._no_memory else []
        skill = await self.skill_registry.select(task)

        context = LoopContext(task=task, memories=memories)

        # ── Skill 注入：获取完整 Skill 定义 ──
        skill_def = None
        skill_prompt = ""
        if hasattr(self.skill_registry, "get_skill"):
            skill_def = self.skill_registry.get_skill(skill)

        # ── 构建 system prompt ──
        tools = getattr(
            getattr(self.tool_executor, "registry", None), "list_tools", lambda: []
        )()
        # Skill 的 tool_allowlist 约束可用工具
        if skill_def and skill_def.get("tool_allowlist"):
            allowed = set(skill_def["tool_allowlist"])
            tools = [t for t in tools if t["name"] in allowed]
        if skill_def and skill_def.get("system_prompt"):
            skill_prompt = skill_def["system_prompt"]

        # 兼容 sync/async ContextBuilder
        build_fn = self.context_builder.build
        if inspect.iscoroutinefunction(build_fn):
            system_prompt = await build_fn(
                task=task,
                workspace="",
                tools=tools,
                memories=memories,
                skill_prompt=skill_prompt,
            )
        else:
            system_prompt = build_fn(
                task=task,
                workspace="",
                tools=tools,
                memories=memories,
                skill_prompt=skill_prompt,
            )

        yield AgentEvent(type="progress", message=f"Skill: {skill}")
        yield AgentEvent(type="thinking", message="分析完毕", detail={"phase": "ready"})

        # ══════════════════════════════════════════════════
        # 真正的 while 循环 — 每步 LLM 重新决策
        # ══════════════════════════════════════════════════
        while True:
            self.step_count += 1

            # ── Step 2: Think (LLM 决策) ──
            # 附加 token 使用信息（如可用）
            thinking_detail: dict = {"phase": "deciding"}
            if hasattr(self.planner, "accumulated_prompt_tokens"):
                thinking_detail["tokens_prompt"] = self.planner.accumulated_prompt_tokens
                thinking_detail["tokens_completion"] = self.planner.accumulated_completion_tokens
                thinking_detail["llm_calls"] = self.planner.llm_call_count
            yield AgentEvent(type="thinking", message="决策中...", detail=thinking_detail)

            next_action = await self.planner.next_step(context, system_prompt=system_prompt)

            # ── 检查完成 ──
            if next_action.done:
                yield AgentEvent(
                    type="thinking",
                    message="分析完毕",
                    detail={"phase": "done", "reasoning": next_action.reasoning},
                )
                break

            # 重复检测：连续 3 步相同动作 → 强制完成
            if len(context.history) >= 3:
                last_three = [(h.tool, h.description) for h in context.history[-3:]]
                if len(set(last_three)) == 1:
                    yield AgentEvent(
                        type="progress",
                        message="连续 3 步相同，任务可能已完成或陷入循环，强制结束",
                    )
                    break

            if self.step_count > context.max_steps:
                yield AgentEvent(
                    type="progress",
                    message=f"已达最大步数 ({context.max_steps})，强制完成",
                )
                break

            # ── 展示 reasoning ──
            if next_action.reasoning:
                yield AgentEvent(
                    type="thinking",
                    message=f"决定: {next_action.description}",
                    detail={"phase": "decision", "reasoning": next_action.reasoning},
                )

            # ── Step 3: Security Check + 审批 ──
            verdict = self.security_classifier.check(
                next_action.tool or "", next_action.params or {}
            )

            if verdict.blocked:
                # 被安全规则阻断 → 不可恢复，记录并跳过
                yield AgentEvent(
                    type="need_approval",
                    message=f"操作被阻断: {verdict.reason}",
                    detail={
                        "tool": next_action.tool,
                        "risk": "high",
                        "blocked": True,
                        "reason": verdict.reason,
                        "description": next_action.description,
                        "params": next_action.params,
                    },
                )
                context.history.append(StepResult(
                    step=self.step_count,
                    tool=next_action.tool or "unknown",
                    description=next_action.description,
                    success=False,
                    output=f"安全阻断: {verdict.reason}",
                ))
                continue

            if verdict.risk_level in ("medium", "high"):
                # 自动批准模式 → 跳过审批
                if self._auto_approve:
                    yield AgentEvent(
                        type="need_approval",
                        message=f"自动批准: {next_action.tool} [{verdict.risk_level.upper()}]",
                        detail={
                            "tool": next_action.tool,
                            "risk": verdict.risk_level,
                            "description": next_action.description,
                            "auto_approved": True,
                        },
                    )
                else:
                    approval_event = asyncio.Event()
                    approval_result = {"approved": False}

                    yield AgentEvent(
                        type="need_approval",
                        message=f"需要审批: {next_action.tool} [{verdict.risk_level.upper()}]",
                        detail={
                            "tool": next_action.tool,
                            "risk": verdict.risk_level,
                            "description": next_action.description,
                            "params": next_action.params,
                            "_approval_event": approval_event,
                            "_approval_result": approval_result,
                        },
                    )

                    # 等待 CLI 层审批（带超时保护）
                    try:
                        await asyncio.wait_for(
                            approval_event.wait(),
                            timeout=self._APPROVAL_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        # 超时 → 自动拒绝
                        context.history.append(StepResult(
                            step=self.step_count,
                            tool=next_action.tool or "unknown",
                            description=next_action.description,
                            success=False,
                            output="审批超时，已自动拒绝",
                        ))
                        continue

                    if not approval_result["approved"]:
                        context.history.append(StepResult(
                            step=self.step_count,
                            tool=next_action.tool or "unknown",
                            description=next_action.description,
                            success=False,
                            output="用户拒绝了此操作",
                        ))
                        continue

            # ── Step 4: Execute Tool（容错） ──
            self.tool_count += 1
            yield AgentEvent(
                type="tool_call",
                message=f"{next_action.tool}: {next_action.description}",
                detail={"tool": next_action.tool, "params": next_action.params},
            )

            try:
                result = await self.tool_executor.execute(
                    next_action.tool or "unknown", next_action.params or {}
                )
            except Exception as exc:
                status_icon = "x"
                output = f"执行异常: {type(exc).__name__}: {exc}"
                yield AgentEvent(
                    type="tool_result",
                    message=f"  {status_icon} {output[:100]}",
                    detail={"success": False, "output": output, "error": str(exc)},
                )
                context.history.append(StepResult(
                    step=self.step_count,
                    tool=next_action.tool or "unknown",
                    description=next_action.description,
                    success=False,
                    output=output[:200],
                ))
                continue

            # ── Step 5: Observe ──
            status_icon = "+" if result.ok else "x"
            yield AgentEvent(
                type="tool_result",
                message=f"  {status_icon} {result.output[:100]}",
                detail={
                    "success": result.ok,
                    "output": result.output,
                    "error": result.error,
                    "awaitUser": result.awaitUser,
                },
            )

            # ── Step 6: Update Context ──
            context.history.append(StepResult(
                step=self.step_count,
                tool=next_action.tool or "unknown",
                description=next_action.description,
                success=result.ok,
                output=result.output[:200],
            ))

            # ── 处理 awaitUser（参考 MiniCode agent-loop.ts:439-453）──
            if result.awaitUser:
                question = result.output.strip()
                if question:
                    # 通知外部：Agent 需要用户输入
                    yield AgentEvent(
                        type="need_approval",
                        message=f"Agent 提问: {question[:100]}",
                        detail={
                            "tool": next_action.tool,
                            "question": question,
                            "_await_user": True,
                        },
                    )
                # 暂停当前回合 — 等待用户回复后继续
                # （REPL 模式下，用户的下一条消息会作为新任务继续）
                break

            # ── Step 7: Session 持久化 ──
            try:
                from minicode.session import save_event as save_session_event  # noqa: F811
                save_session_event(
                    session_id=getattr(self, "_session_id", "default"),
                    event_type="tool_call",
                    content=f"{next_action.tool}: {next_action.description}",
                    metadata={
                        "tool": next_action.tool,
                        "params": next_action.params,
                        "ok": result.ok,
                        "output_snippet": result.output[:100],
                    },
                )
            except Exception:
                pass  # session 保存失败不影响主流程

            # ── Step 8: 自动上下文压缩检查 ──
            if self.step_count % 3 == 0 and len(context.history) > 5:
                try:
                    from minicode.context.compressor import estimate_tokens, compress_to_L2
                    history_text = "\n".join(
                        f"[{h.tool}] {h.description} → {h.output}"
                        for h in context.history
                    )
                    est_tokens = estimate_tokens(history_text)
                    # 超过 2000 token 时触发压缩
                    if est_tokens > 2000:
                        compressed = compress_to_L2(history_text, task)
                        yield AgentEvent(
                            type="summary",
                            message=compressed.summary[:200],
                            detail={
                                "phase": "compaction",
                                "pre_tokens": est_tokens,
                                "post_tokens": compressed.compressed_tokens,
                                "level": compressed.level,
                                "full_summary": compressed.summary,
                            },
                        )
                except Exception:
                    pass  # 压缩失败不影响主流程

            if result.ok and not self._no_memory:
                await self.memory_store.add_episodic(
                    task=task,
                    step=next_action.description,
                    tool=next_action.tool or "unknown",
                    result=result.output[:200],
                )

        # ── Synthesize: 合成最终回答 ──
        yield AgentEvent(
            type="reflection",
            message="合成总结中...",
            detail={"phase": "synthesizing"},
        )

        try:
            summary = await self.planner.synthesize(context)
        except Exception:
            summary = f"任务完成 · {self.step_count} 步 · {self.tool_count} Tool"

        # ── assistant 事件: Agent 最终自然语言回复 ──
        yield AgentEvent(
            type="assistant",
            message=summary[:200],
            detail={
                "phase": "final_response",
                "full_response": summary,
            },
        )

        yield AgentEvent(
            type="done",
            message=f"任务完成 · {self.step_count} 步 · {self.tool_count} Tool",
            detail={
                "steps": self.step_count,
                "tools": self.tool_count,
                "skill": skill,
                "summary": summary,
            },
        )

        # ── Reflection: 任务结束后反思 ──
        try:
            from minicode.agent.reflection import ReflectionAgent
            llm = getattr(self, "_llm_client", None)
            if llm:
                yield AgentEvent(
                    type="reflection",
                    message="反思中...",
                    detail={"phase": "reflecting"},
                )

                task_success = all(h.success for h in context.history) if context.history else True
                reflection = ReflectionAgent(llm, self.memory_store)
                result = await reflection.reflect(
                    task=task,
                    history=context.history,
                    success=task_success,
                )
                if result.summary:
                    yield AgentEvent(
                        type="reflection",
                        message=f"经验: {result.summary[:200]}",
                        detail={
                            "phase": "reflection_done",
                            "lessons": result.lessons,
                            "root_cause": result.root_cause,
                        },
                    )
        except Exception:
            # 反思失败不影响任务结果
            pass

    async def close(self):
        """释放所有资源（LLM client、MCP client、HTTP 连接等）。"""
        if hasattr(self, "_llm_client") and hasattr(self._llm_client, "close"):
            await self._llm_client.close()
        # 清理 MCP connections
        if hasattr(self, "_mcp_dispose") and self._mcp_dispose:
            try:
                await self._mcp_dispose()
            except Exception:
                pass

    async def run_all(self, task: str) -> list[AgentEvent]:
        """收集所有事件到列表（测试用）。"""
        events = []
        async for event in self.run(task):
            events.append(event)
        return events
