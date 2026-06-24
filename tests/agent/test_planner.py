"""Planner 单元测试 — KeywordPlanner + LLMPlanner。"""

import asyncio
import pytest

from minicode.agent.planner import (
    KeywordPlanner,
    LLMPlanner,
    NextAction,
    LoopContext,
    StepResult,
)
from minicode.llm.client import MockLLMClient, LLMError


# ── KeywordPlanner ──


class TestKeywordPlanner:
    @pytest.fixture
    def planner(self):
        return KeywordPlanner()

    def test_classify_fix(self, planner):
        assert planner._classify("修复 NPE 错误") == "fix"
        assert planner._classify("fix the bug") == "fix"

    def test_classify_refactor(self, planner):
        assert planner._classify("重构模块") == "refactor"

    def test_classify_test(self, planner):
        assert planner._classify("添加测试") == "test"

    def test_classify_default_explore(self, planner):
        assert planner._classify("随便看看") == "explore"

    @pytest.mark.asyncio
    async def test_next_step_returns_action(self, planner):
        ctx = LoopContext(task="修复 NPE 错误")
        action = await planner.next_step(ctx)
        assert isinstance(action, NextAction)
        assert not action.done
        assert action.tool is not None
        assert action.description

    @pytest.mark.asyncio
    async def test_next_step_completes_when_all_steps_done(self, planner):
        ctx = LoopContext(task="fix bug")
        for _ in range(10):
            action = await planner.next_step(ctx)
            if action.done:
                return  # Planner correctly finished
            ctx.history.append(StepResult(
                step=len(ctx.history), tool=action.tool or "",
                description=action.description, success=True, output="ok"
            ))
        pytest.fail("Planner did not return done after exhausting steps")

    @pytest.mark.asyncio
    async def test_synthesize_returns_summary(self, planner):
        ctx = LoopContext(task="修复 Bug")
        ctx.history.append(StepResult(
            step=1, tool="grep", description="搜索",
            success=True, output="found 3 matches"
        ))
        result = await planner.synthesize(ctx)
        assert "修复 Bug" in result
        assert "grep" in result


# ── LLMPlanner ──


class TestLLMPlanner:
    @pytest.fixture
    def planner(self):
        return LLMPlanner(MockLLMClient())

    @pytest.mark.asyncio
    async def test_next_step_parses_mock_response(self, planner):
        ctx = LoopContext(task="test")
        action = await planner.next_step(ctx)
        assert isinstance(action, NextAction)
        assert action.done  # Mock returns {"done": true}

    @pytest.mark.asyncio
    async def test_next_step_fallback_on_invalid_json(self):
        class BadLLM:
            async def chat(self, **kw):
                from minicode.llm.client import LLMResponse
                return LLMResponse(content="not json at all!!!")
        planner = LLMPlanner(BadLLM())
        ctx = LoopContext(task="test")
        action = await planner.next_step(ctx)
        assert not action.done
        assert action.tool == "list_directory"

    @pytest.mark.asyncio
    async def test_next_step_fallback_on_llm_error(self):
        class ErrorLLM:
            async def chat(self, **kw):
                raise LLMError("API down")
        planner = LLMPlanner(ErrorLLM())
        ctx = LoopContext(task="test")
        action = await planner.next_step(ctx)
        assert not action.done

    @pytest.mark.asyncio
    async def test_synthesize_with_llm(self, planner):
        ctx = LoopContext(task="分析项目")
        ctx.history.append(StepResult(
            step=1, tool="list_directory", description="列出",
            success=True, output="src/"
        ))
        result = await planner.synthesize(ctx)
        assert isinstance(result, str)
        assert len(result) > 0


# ── NextAction ──


class TestNextAction:
    def test_defaults(self):
        a = NextAction()
        assert not a.done
        assert a.tool is None
        assert a.params is None

    def test_done_action(self):
        a = NextAction(done=True, reasoning="完成任务")
        assert a.done


# ── LoopContext ──


class TestLoopContext:
    def test_defaults(self):
        ctx = LoopContext(task="test")
        assert ctx.task == "test"
        assert ctx.history == []
        assert ctx.max_steps == 10

    def test_custom_max_steps(self):
        ctx = LoopContext(task="t", max_steps=5)
        assert ctx.max_steps == 5
