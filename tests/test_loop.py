"""Agent Loop 状态流转测试。

覆盖 QueryLoop 的完整事件序列：
1. 事件类型检查
2. 事件顺序保证
3. 边界情况（空任务、中断）
4. 事件元数据完整性
"""

import asyncio
import pytest

from minicode.events import AgentEvent


# ── Fixture ──


@pytest.fixture
def events(mock_loop):
    """运行一次完整 Loop，返回所有事件列表。"""
    return asyncio.run(mock_loop.run_all("修复订单 NPE"))


# ── 事件类型检查 ──


class TestEventTypePresence:
    """验证必要的事件类型都出现在事件流中。"""

    def test_yields_thinking_event(self, events):
        """循环启动时应产生 thinking 事件。"""
        thinking_events = [e for e in events if e.type == "thinking"]
        assert len(thinking_events) > 0, "Loop 必须产生至少一个 thinking 事件"

    def test_yields_tool_call_events(self, events):
        """循环应产生 tool_call 事件。"""
        tool_calls = [e for e in events if e.type == "tool_call"]
        assert len(tool_calls) > 0, "Loop 必须产生至少一个 tool_call 事件"
        # 每个 tool_call 应有 tool 名称
        for tc in tool_calls:
            assert tc.detail is not None
            assert "tool" in tc.detail

    def test_yields_tool_result_events(self, events):
        """循环应产生 tool_result 事件。"""
        results = [e for e in events if e.type == "tool_result"]
        assert len(results) > 0, "Loop 必须产生至少一个 tool_result 事件"
        # 每个 result 应报告成功或失败
        for r in results:
            assert r.detail is not None
            assert "success" in r.detail

    def test_yields_done_event(self, events):
        """循环结束时必须产生 done 事件。"""
        done_events = [e for e in events if e.type == "done"]
        assert len(done_events) == 1, "Loop 必须恰好产生一个 done 事件"


# ── 事件顺序 ──


class TestEventOrdering:
    """验证事件按正确的顺序出现。"""

    def test_starts_with_thinking(self, events):
        """第一个事件应为 thinking。"""
        assert events[0].type == "thinking", f"第一个事件应为 thinking，实际为 {events[0].type}"

    def test_ends_with_done(self, events):
        """最后一个事件应为 done。"""
        assert events[-1].type == "done", f"最后一个事件应为 done，实际为 {events[-1].type}"

    def test_tool_result_follows_tool_call(self, events):
        """每个 tool_call 后应紧跟 tool_result。"""
        for i, event in enumerate(events[:-1]):
            if event.type == "tool_call":
                next_type = events[i + 1].type
                assert next_type == "tool_result", (
                    f"tool_call 后应为 tool_result，"
                    f"实际为 {next_type} (事件 #{i})"
                )

    def test_thinking_before_tool_call(self, events):
        """每个步骤应在 tool_call 前有 thinking 事件。"""
        tool_call_indices = [
            i for i, e in enumerate(events) if e.type == "tool_call"
        ]
        for idx in tool_call_indices:
            # 检查前面最近的 thinking 或 progress 事件
            preceding = events[idx - 1]
            assert preceding.type in ("thinking", "tool_result", "need_approval"), (
                f"tool_call 前一个事件应为 thinking/tool_result/need_approval，"
                f"实际为 {preceding.type} (事件 #{idx})"
            )


# ── 事件元数据 ──


class TestEventMetadata:
    """验证事件携带了必要的元数据。"""

    def test_all_events_have_timestamp(self, events):
        """所有事件必须带时间戳。"""
        for i, e in enumerate(events):
            assert e.timestamp > 0, f"事件 #{i} ({e.type}) 缺少时间戳"
            assert isinstance(e.timestamp, float)

    def test_all_events_have_message(self, events):
        """所有事件必须有非空 message。"""
        for i, e in enumerate(events):
            assert e.message, f"事件 #{i} ({e.type}) message 为空"
            assert isinstance(e.message, str)

    def test_done_event_has_step_count(self, events):
        """done 事件的 detail 应包含步数和 Tool 计数。"""
        done = events[-1]
        assert done.detail is not None
        assert "steps" in done.detail
        assert "tools" in done.detail
        assert done.detail["steps"] > 0
        assert done.detail["tools"] > 0


# ── 边界情况 ──


class TestEdgeCases:
    """边界情况测试。"""

    def test_empty_task(self, mock_loop):
        """空任务应能正常完成（使用默认计划）。"""
        events = asyncio.run(mock_loop.run_all(""))
        assert len(events) > 0
        assert events[-1].type == "done"

    def test_loop_updates_step_counter(self, mock_loop):
        """验证 step_count 和 tool_count 正确更新。"""
        events = asyncio.run(mock_loop.run_all("修复 NPE"))
        done = events[-1]
        assert done.detail["steps"] == mock_loop.step_count
        assert done.detail["tools"] == mock_loop.tool_count

    def test_memory_stores_episodic(self, mock_loop, mock_memory_store):
        """验证执行完成后 Memory 中有记录。"""
        # 使用独立的 memory_store 方便断言
        mock_loop.memory_store = mock_memory_store
        asyncio.run(mock_loop.run_all("修复 NPE"))
        assert mock_memory_store.count > 0, "执行后应有 episodic memory 记录"
        # 所有记录应为 episodic 类型
        for entry in mock_memory_store._memories:
            assert entry.type == "episodic"


# ── 中断测试 ──


class TestInterruption:
    """验证循环可以被安全取消。"""

    @pytest.mark.asyncio
    async def test_loop_can_be_cancelled(self, mock_loop):
        """在循环中途取消不应抛出异常外泄。"""
        gen = mock_loop.run("修复 NPE")

        # 读取前两个事件后取消
        await gen.__anext__()  # thinking
        await gen.__anext__()  # progress (plan)

        # 取消 generator
        await gen.aclose()

        # 不应抛出异常
