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
from typing import AsyncIterator

from minicode.events import AgentEvent
from minicode.agent.planner import NextAction, StepResult, LoopContext


class QueryLoop:
    """MiniCode 核心 Agent 循环。

    接收用户任务，通过 Planner → Skill → Tool 管道执行，
    整个过程持续 yield AgentEvent 供 CLI 层渲染。
    """

    def __init__(
        self,
        planner,
        skill_registry,
        tool_executor,
        memory_store,
        context_builder,
        security_classifier,
    ):
        self.planner = planner
        self.skill_registry = skill_registry
        self.tool_executor = tool_executor
        self.memory_store = memory_store
        self.context_builder = context_builder
        self.security_classifier = security_classifier

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

        # ── 初始分析 ──
        yield AgentEvent(type="thinking", message="分析中...", detail={"phase": "planning"})
        memories = await self.memory_store.search(task, top_k=3)
        skill = await self.skill_registry.select(task)

        context = LoopContext(task=task, memories=memories)

        yield AgentEvent(type="progress", message=f"Skill: {skill}")
        yield AgentEvent(type="thinking", message="分析完毕", detail={"phase": "ready"})

        # ══════════════════════════════════════════════════
        # 真正的 while 循环 — 每步 LLM 重新决策
        # ══════════════════════════════════════════════════
        while True:
            self.step_count += 1

            # ── Step 2: Think (LLM 决策) ──
            yield AgentEvent(type="thinking", message="决策中...", detail={"phase": "deciding"})

            next_action = await self.planner.next_step(context)

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
            risk = self.security_classifier.classify(
                next_action.tool or "", next_action.params or {}
            )

            if risk in ("medium", "high"):
                approval_event = asyncio.Event()
                approval_result = {"approved": False}

                yield AgentEvent(
                    type="need_approval",
                    message=f"需要审批: {next_action.tool} [{risk.upper()}]",
                    detail={
                        "tool": next_action.tool,
                        "risk": risk,
                        "description": next_action.description,
                        "params": next_action.params,
                        "_approval_event": approval_event,
                        "_approval_result": approval_result,
                    },
                )

                # 🔒 阻塞等待 CLI 层设置 approval_event
                await approval_event.wait()

                if not approval_result["approved"]:
                    # 用户拒绝 → 记录失败历史，让下一轮 LLM 重规划
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
                # 🔧 执行异常 → 记录失败，让 LLM 决策下一步
                status_icon = "✗"
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
            status_icon = "✓" if result.success else "✗"
            yield AgentEvent(
                type="tool_result",
                message=f"  {status_icon} {result.output[:100]}",
                detail={
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                },
            )

            # ── Step 6: Update Context ──
            context.history.append(StepResult(
                step=self.step_count,
                tool=next_action.tool or "unknown",
                description=next_action.description,
                success=result.success,
                output=result.output[:200],
            ))

            if result.success:
                await self.memory_store.add_episodic(
                    task=task,
                    step=next_action.description,
                    tool=next_action.tool or "unknown",
                    result=result.output[:200],
                )

        # ── Done ──
        yield AgentEvent(
            type="done",
            message=f"任务完成 · {self.step_count} 步 · {self.tool_count} Tool",
            detail={
                "steps": self.step_count,
                "tools": self.tool_count,
                "skill": skill,
            },
        )

    async def run_all(self, task: str) -> list[AgentEvent]:
        """收集所有事件到列表（测试用）。"""
        events = []
        async for event in self.run(task):
            events.append(event)
        return events
