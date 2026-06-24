"""LLM Router — 多后端路由 + 自动降级。

参考 MiniCode anthropic-adapter.ts 和 spec Section 20.4 的设计：
- 按任务复杂度选择模型
- 主力失败自动降级到 fallback
- 支持 DeepSeek 和 OpenAI-compatible 后端

路由策略：
  simple   → 便宜模型 (deepseek-chat / gpt-4o-mini)
  medium   → 默认模型 (deepseek-chat)
  complex  → 强推理模型 (deepseek-reasoner / claude-sonnet-4)
"""

import asyncio
from dataclasses import dataclass

from minicode.llm.client import DeepSeekLLMClient, LLMError, LLMResponse


@dataclass
class RouteDecision:
    """路由决策结果。

    Attributes:
        model: 选择的模型名
        backend: 选择的模型后端名称（deepseek/openai/claude）
        complexity: 评估的任务复杂度 (simple/medium/complex)
        reasoning: 路由决策原因
    """

    model: str
    backend: str = ""
    complexity: str = "medium"
    reasoning: str = ""


class LLMRouter:
    """多后端 LLM 路由器。

    职责：
    1. 按任务复杂度选择模型
    2. 主力模型失败时自动降级
    3. 管理多个 LLMClient 后端实例

    Usage:
        router = LLMRouter()
        router.register("deepseek", DeepSeekLLMClient(api_key="..."))
        response = await router.route_and_call(messages, task_complexity="medium")
    """

    # 复杂度 → 模型映射（按后端）
    COMPLEXITY_MODEL_MAP = {
        "simple": {
            "deepseek": "deepseek-chat",
            "openai": "gpt-4o-mini",
        },
        "medium": {
            "deepseek": "deepseek-chat",
            "openai": "gpt-4o",
        },
        "complex": {
            "deepseek": "deepseek-reasoner",
            "openai": "gpt-4o",
            "claude": "claude-sonnet-4-20250514",
        },
    }

    def __init__(self):
        self._clients: dict[str, object] = {}     # backend_name → LLM client
        self._default_backend: str = ""
        self._fallback_chain: list[str] = []      # 降级链 [primary, fallback1, ...]

    def register(self, name: str, client, default: bool = False) -> None:
        """注册一个 LLM 后端。

        Args:
            name: 后端名称 (如 "deepseek", "openai", "claude")
            client: LLMClient 实例 (需有 chat 方法)
            default: 是否设为默认后端
        """
        self._clients[name] = client
        if default or not self._default_backend:
            self._default_backend = name
        if name not in self._fallback_chain:
            self._fallback_chain.append(name)

    def set_fallback_chain(self, backend_names: list[str]) -> None:
        """设置降级链（按优先级排列）。

        Args:
            backend_names: 后端名称列表，如 ["deepseek", "openai"]
        """
        self._fallback_chain = [n for n in backend_names if n in self._clients]

    def route(self, task_complexity: str = "medium") -> RouteDecision:
        """根据任务复杂度选择模型。

        Args:
            task_complexity: 任务复杂度 (simple/medium/complex)

        Returns:
            RouteDecision: 路由决策
        """
        complexity = task_complexity.lower()
        if complexity not in ("simple", "medium", "complex"):
            complexity = "medium"

        # 找到第一个可用的后端
        for backend in self._fallback_chain:
            if backend in self._clients:
                model_map = self.COMPLEXITY_MODEL_MAP.get(complexity, {})
                model = model_map.get(backend, "deepseek-chat")
                return RouteDecision(
                    model=model,
                    backend=backend,
                    complexity=complexity,
                    reasoning=f"按复杂度 '{complexity}' 选择 {backend}/{model}",
                )

        # 完全没有后端
        return RouteDecision(
            model="deepseek-chat",
            backend="",
            complexity=complexity,
            reasoning="无可用后端，使用默认模型名",
        )

    async def route_and_call(
        self,
        messages: list[dict],
        task_complexity: str = "medium",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """路由 + 调用 + 自动降级。

        按降级链尝试每个后端，直到成功。

        Args:
            messages: OpenAI 格式消息列表
            task_complexity: 任务复杂度
            temperature: 温度参数
            max_tokens: 最大输出 token

        Returns:
            LLMResponse

        Raises:
            LLMError: 所有后端都失败时抛出
        """
        decision = self.route(task_complexity)
        errors: list[str] = []

        # 优先使用 route() 选择的模型，沿降级链尝试
        model_map = self.COMPLEXITY_MODEL_MAP.get(decision.complexity, {})
        primary_model = model_map.get(decision.backend, decision.model)

        for backend in self._fallback_chain:
            client = self._clients.get(backend)
            if client is None:
                continue

            # 使用 route() 决定的模型（如果是当前尝试的后端），否则查表
            model = primary_model if backend == decision.backend else (
                model_map.get(backend, "deepseek-chat")
            )

            try:
                chat_fn = getattr(client, "chat", None)
                if chat_fn is None:
                    errors.append(f"{backend}: 缺少 chat 方法")
                    continue

                return await chat_fn(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except LLMError as e:
                errors.append(f"{backend}/{model}: {e.message}")
                continue

        raise LLMError(f"所有后端调用失败: {'; '.join(errors)}")

    async def close(self) -> None:
        """关闭所有后端连接。"""
        for client in self._clients.values():
            close_fn = getattr(client, "close", None)
            if close_fn and asyncio.iscoroutinefunction(close_fn):
                await close_fn()

    @property
    def available_backends(self) -> list[str]:
        """列出所有已注册的后端名称。"""
        return list(self._clients.keys())
