"""LLM Client — 支持 DeepSeek API 和 Mock 两种后端。

DeepSeekLLMClient: 通过 httpx 调用 api.deepseek.com/v1 (OpenAI-compatible)
MockLLMClient: 返回固定响应用于测试

异常体系:
- LLMError: 所有 LLM 调用失败的基类（超时/HTTP错误/JSON解析失败）
- 调用方必须捕获 LLMError 并降级处理
"""

import json
import os
from dataclasses import dataclass

import httpx


# ── 异常 ──


class LLMError(Exception):
    """LLM 调用失败。

    Attributes:
        message: 人类可读错误描述
        cause: 原始异常（如有）
    """

    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message)
        self.message = message
        self.cause = cause


# ── 响应 ──


@dataclass
class LLMResponse:
    """LLM 成功返回结果。"""
    content: str
    model: str = "unknown"
    prompt_tokens: int = 0
    completion_tokens: int = 0


# ── DeepSeek Client ──


class DeepSeekLLMClient:
    """DeepSeek API 客户端 (OpenAI-compatible 协议)。

    API key 从环境变量 `deepseek` 读取。
    所有网络/API/解析异常均抛出 LLMError。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.deepseek.com/v1",
    ):
        self.api_key = api_key or os.environ.get("deepseek", "")
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
        )

    async def chat(
        self,
        messages: list[dict],
        model: str = "deepseek-chat",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """发送 chat completion 请求到 DeepSeek API。

        Args:
            messages: OpenAI 格式的消息列表
            model: 模型名
            temperature: 温度参数
            max_tokens: 最大输出 token

        Returns:
            LLMResponse: 解析后的响应

        Raises:
            LLMError: 任何调用失败（超时/HTTP错误/JSON异常）
        """
        if not self.api_key:
            raise LLMError("未设置 API key (环境变量 deepseek)")

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            resp = await self._client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException as e:
            raise LLMError("请求超时，请检查网络或稍后重试", cause=e) from e
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:300] if e.response is not None else "无详情"
            raise LLMError(f"API 错误 {e.response.status_code}: {detail}", cause=e) from e
        except httpx.RequestError as e:
            raise LLMError(f"网络请求失败: {e}", cause=e) from e
        except json.JSONDecodeError as e:
            raise LLMError("API 返回非 JSON 响应", cause=e) from e

        # 校验响应结构
        if "choices" not in data or not data["choices"]:
            raise LLMError(f"API 返回无 choices: {json.dumps(data)[:200]}")

        try:
            choice = data["choices"][0]
            usage = data.get("usage", {})
            return LLMResponse(
                content=choice["message"]["content"],
                model=data.get("model", model),
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            )
        except (KeyError, TypeError) as e:
            raise LLMError(f"API 响应结构异常: {e}", cause=e) from e

    async def chat_stream(
        self,
        messages: list[dict],
        model: str = "deepseek-chat",
    ):
        """流式 chat completion。

        Yields:
            str: 每个 token

        Raises:
            LLMError: 调用失败
        """
        if not self.api_key:
            raise LLMError("未设置 API key (环境变量 deepseek)")

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 4096,
            "stream": True,
        }

        try:
            async with self._client.stream("POST", url, headers=headers, json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except httpx.TimeoutException as e:
            raise LLMError("流式请求超时", cause=e) from e
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:300] if e.response is not None else "无详情"
            raise LLMError(f"流式 API 错误 {e.response.status_code}: {detail}", cause=e) from e
        except httpx.RequestError as e:
            raise LLMError(f"流式网络请求失败: {e}", cause=e) from e

    async def close(self):
        """关闭 HTTP 客户端。"""
        await self._client.aclose()


# ── Mock Client (保留用于测试) ──


class MockLLMClient:
    """Mock LLM 客户端 — 测试和离线模式使用。

    Mock 不会抛 LLMError，总是返回固定成功响应。
    """

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        return LLMResponse(
            content='{"done": true, "reasoning": "Mock: 任务完成"}',
            model=model or "mock-model",
            prompt_tokens=len(str(messages)) // 4,
            completion_tokens=20,
        )

    async def chat_stream(
        self,
        messages: list[dict],
        model: str | None = None,
    ):
        yield '{"done": true, "reasoning": "Mock: 任务完成"}'

    async def close(self):
        """Mock 无需清理。"""
        pass
