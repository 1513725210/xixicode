"""共享测试夹具。

为 Agent Loop 测试提供预设的 Mock 依赖。
"""

import pytest

from minicode.agent.loop import QueryLoop
from minicode.agent.planner import KeywordPlanner
from minicode.tool.mock import MockToolExecutor
from minicode.skill.registry import MockSkillRegistry
from minicode.llm.client import MockLLMClient
from minicode.memory.store import MockMemoryStore
from minicode.context.builder import MockContextBuilder
from minicode.security.classifier import MockSecurityClassifier


@pytest.fixture
def mock_loop():
    """构建完整 Mock 依赖的 QueryLoop 实例。"""
    return QueryLoop(
        planner=KeywordPlanner(),
        skill_registry=MockSkillRegistry(),
        tool_executor=MockToolExecutor(),
        memory_store=MockMemoryStore(),
        context_builder=MockContextBuilder(),
        security_classifier=MockSecurityClassifier(),
    )


@pytest.fixture
def mock_tool_executor():
    """独立的 Mock ToolExecutor。"""
    return MockToolExecutor()


@pytest.fixture
def mock_memory_store():
    """独立的 Mock MemoryStore。"""
    return MockMemoryStore()
