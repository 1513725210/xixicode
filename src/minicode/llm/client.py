"""LLM Client — 支持 DeepSeek API 和 Mock 两种后端。

DeepSeekLLMClient: 通过 httpx 调用 api.deepseek.com/v1 (OpenAI-compatible)
MockLLMClient: 返回固定响应用于测试
"""

import json
import os
from dataclasses import dataclass

import httpx


@dataclass
class LLMResponse:
    """LLM 返回结果。"""
    content: str
    model: str = "mock"
    prompt_tokens: int = 0
    completion_tokens: int = 0


# ── DeepSeek Client ──


class DeepSeekLLMClient:
    """DeepSeek API 客户端 (OpenAI-compatible 协议)。

    API key 从环境变量 `deepseek` 读取。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.deepseek.com/v1",
    ):
        self.api_key = api_key or os.environ.get("deepseek", "")
        self.base_url = base_url.rstrip("/")
        # 分层超时：连接 10s，读取 30s，总计不超 60s
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
            LLMResponse: 解析后的响应（错误时返回包含错误信息的 LLMResponse）
        """
        if not self.api_key:
            return LLMResponse(
                content="[DeepSeek] 未设置 API key (环境变量 deepseek)",
                model="deepseek-chat",
            )

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

            if "choices" not in data or not data["choices"]:
                return LLMResponse(
                    content=f"[DeepSeek] API 返回无 choices: {json.dumps(data)[:200]}",
                    model=model,
                )

            choice = data["choices"][0]
            usage = data.get("usage", {})

            return LLMResponse(
                content=choice["message"]["content"],
                model=data.get("model", model),
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            )

        except httpx.TimeoutException:
            return LLMResponse(
                content="[DeepSeek] 请求超时，请检查网络或稍后重试",
                model=model,
            )
        except httpx.HTTPStatusError as e:
            return LLMResponse(
                content=f"[DeepSeek] API 错误 {e.response.status_code}: {e.response.text[:200]}",
                model=model,
            )
        except (httpx.RequestError, json.JSONDecodeError, KeyError) as e:
            return LLMResponse(
                content=f"[DeepSeek] 请求失败: {type(e).__name__}: {str(e)[:200]}",
                model=model,
            )

    async def chat_stream(
        self,
        messages: list[dict],
        model: str = "deepseek-chat",
    ):
        """流式 chat completion。

        Yields:
            str: 每个 token
        """
        if not self.api_key:
            yield "[DeepSeek] 未设置 API key"
            return

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
        except httpx.TimeoutException:
            yield "[DeepSeek] 流式请求超时"
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            yield f"[DeepSeek] 流式请求失败: {e}"

    async def close(self):
        """关闭 HTTP 客户端。"""
        await self._client.aclose()


# ── Mock Client (保留用于测试) ──


class MockLLMClient:
    """Mock LLM 客户端 — 测试和离线模式使用。"""

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        return LLMResponse(
            content="[Mock LLM] 分析完成，建议继续执行。",
            model=model or "mock-model",
            prompt_tokens=len(str(messages)) // 4,
            completion_tokens=20,
        )

    async def chat_stream(
        self,
        messages: list[dict],
        model: str | None = None,
    ):
        yield "[Mock LLM stream] 分析中..."
