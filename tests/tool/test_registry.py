"""ToolRegistry + ToolExecutor 测试。"""

import asyncio
import pytest
from pathlib import Path

from minicode.tool.base import Tool, ToolResult
from minicode.tool.registry import ToolRegistry, ToolExecutor


# ── Stub Tool 用于测试注册 ──


class StubSuccess(Tool):
    name = "stub_ok"
    description = "总是成功的 stub tool"
    parameters = {"key": "string"}
    risk_level = "safe"

    async def execute(self, **params) -> ToolResult:
        return ToolResult(success=True, output=f"OK: {params}")


class StubFail(Tool):
    name = "stub_fail"
    description = "总是失败的 stub tool"
    risk_level = "medium"

    async def execute(self, **params) -> ToolResult:
        return ToolResult(success=False, output="fail", error="stub error")


class StubExplode(Tool):
    name = "stub_bomb"
    description = "执行时抛异常的 stub tool"
    risk_level = "high"

    async def execute(self, **params) -> ToolResult:
        raise RuntimeError("BANG")


# ── Registry 测试 ──


class TestToolRegistry:
    """ToolRegistry 的注册/查找/列表功能。"""

    def test_register_and_get(self):
        reg = ToolRegistry()
        reg.register(StubSuccess())
        tool = reg.get("stub_ok")
        assert tool is not None
        assert tool.name == "stub_ok"

    def test_get_missing_returns_none(self):
        reg = ToolRegistry()
        assert reg.get("nonexistent") is None

    def test_register_duplicate_overwrites(self):
        reg = ToolRegistry()
        a = StubSuccess()
        b = StubSuccess()
        reg.register(a)
        reg.register(b)
        assert reg.get("stub_ok") is b

    def test_list_names(self):
        reg = ToolRegistry()
        reg.register(StubSuccess())
        reg.register(StubFail())
        names = reg.list_names()
        assert set(names) == {"stub_ok", "stub_fail"}

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register(StubSuccess())
        tools = reg.list_tools()
        assert len(tools) == 1
        # 每个 tool dict 应包含 LLM 需要的字段
        t = tools[0]
        assert t["name"] == "stub_ok"
        assert "description" in t
        assert "parameters" in t
        assert "risk_level" in t


# ── Executor 测试 ──


class TestToolExecutor:
    """ToolExecutor 的分发/容错/历史功能。"""

    @pytest.fixture
    def executor(self):
        reg = ToolRegistry()
        reg.register(StubSuccess())
        reg.register(StubFail())
        reg.register(StubExplode())
        return ToolExecutor(reg)

    def test_execute_known_tool(self, executor):
        result = asyncio.run(executor.execute("stub_ok", {"key": "v"}))
        assert result.success
        assert "OK" in result.output

    def test_execute_unknown_tool(self, executor):
        result = asyncio.run(executor.execute("ghost", {}))
        assert not result.success
        assert "未注册" in result.error or "找不到" in result.error or "未知" in result.error

    def test_execute_failing_tool(self, executor):
        result = asyncio.run(executor.execute("stub_fail", {}))
        assert not result.success
        assert result.error == "stub error"

    def test_execute_exploding_tool(self, executor):
        result = asyncio.run(executor.execute("stub_bomb", {}))
        assert not result.success
        assert "BANG" in result.error

    def test_call_history(self, executor):
        asyncio.run(executor.execute("stub_ok", {"a": 1}))
        asyncio.run(executor.execute("stub_fail", {}))
        assert executor.call_count == 2
        assert len(executor.call_history) == 2
        assert executor.call_history[0]["tool"] == "stub_ok"
        assert executor.call_history[1]["tool"] == "stub_fail"

    def test_executes_preserve_params_in_history(self, executor):
        params = {"path": "src/main.py", "pattern": "TODO"}
        asyncio.run(executor.execute("stub_ok", params))
        assert executor.call_history[-1]["params"] == params
