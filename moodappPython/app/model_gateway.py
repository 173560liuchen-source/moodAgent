import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import httpx

from .config import (
    MODEL_API_BASE_URL,
    MODEL_API_KEY,
    MODEL_CIRCUIT_FAILURE_THRESHOLD,
    MODEL_CIRCUIT_RESET_SECONDS,
    HTTP_KEEPALIVE_EXPIRY_SECONDS,
    HTTP_MAX_CONNECTIONS,
    HTTP_MAX_KEEPALIVE_CONNECTIONS,
    MODEL_MAX_RETRIES,
    MODEL_NAME,
    MODEL_TIMEOUT_SECONDS,
)
from .schemas import ModelChatRequest, ModelChatResponse


logger = logging.getLogger(__name__)


class ModelGatewayError(RuntimeError):
    pass


class CircuitOpenError(ModelGatewayError):
    pass


class ModelGateway:
    """统一模型调用层，提供超时、重试和熔断。"""

    def __init__(self) -> None:
        self._failure_count = 0
        self._opened_at: float | None = None
        self._state_lock = asyncio.Lock()  #熔断状态的互斥锁
        self._metrics_lock = asyncio.Lock()  #指标的互斥锁
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._retry_count = 0
        self._circuit_rejections = 0
        self._total_latency_ms = 0.0
        self._last_success_at: str | None = None
        self._last_failure_at: str | None = None
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    #请求来了
    async def _record_request_started(self) -> None:
        async with self._metrics_lock:
            self._total_requests += 1

    #请求重试了
    async def _record_retry(self) -> None:
        async with self._metrics_lock:
            self._retry_count += 1

    #请求被熔断了
    async def _record_circuit_rejection(self) -> None:
        async with self._metrics_lock:
            self._circuit_rejections += 1

    #请求结束了
    async def _record_request_finished(self, *, success: bool, started_at: float) -> None:
        #  算这次请求花了多少毫秒
        latency_ms = (time.perf_counter() - started_at) * 1000

        async with self._metrics_lock:
            self._total_latency_ms += latency_ms  # 累加总延迟（后面算平均值）
            if success:
                self._successful_requests += 1
                self._last_success_at = self._utc_now()  # 记录最后一次成功的时间
            else:
                self._failed_requests += 1
                self._last_failure_at = self._utc_now()  # 记录最后一次失败的时间

    #获取指标
    async def snapshot(self) -> dict[str, Any]:
        async with self._state_lock:
            opened_at = self._opened_at
            failure_count = self._failure_count
            if opened_at is None:
                circuit_state = "closed"
                reset_remaining_seconds = 0.0
            else:
                elapsed = time.monotonic() - opened_at  #从熔断到现在过了多少秒
                reset_remaining_seconds = max(
                    0.0,
                    MODEL_CIRCUIT_RESET_SECONDS - elapsed,
                )
                circuit_state = (
                    "open" if reset_remaining_seconds > 0 else "half_open"
                )

        async with self._metrics_lock:
            total_requests = self._total_requests
            average_latency_ms = (
                self._total_latency_ms / total_requests
                if total_requests
                else 0.0
            )
            return {
                "configured": bool(MODEL_API_KEY),
                "model": MODEL_NAME,
                "circuit": {
                    "state": circuit_state,
                    "consecutive_failures": failure_count,
                    "failure_threshold": MODEL_CIRCUIT_FAILURE_THRESHOLD,
                    "reset_seconds": MODEL_CIRCUIT_RESET_SECONDS,
                    "reset_remaining_seconds": round(
                        reset_remaining_seconds,
                        3,
                    ),
                },
                "requests": {
                    "total": total_requests,
                    "successful": self._successful_requests,
                    "failed": self._failed_requests,
                    "retries": self._retry_count,
                    "circuit_rejections": self._circuit_rejections,
                    "average_latency_ms": round(average_latency_ms, 3),
                    "last_success_at": self._last_success_at,
                    "last_failure_at": self._last_failure_at,
                },
            }

    #确保熔断器
    async def _ensure_circuit(self) -> None:
        async with self._state_lock:
            if self._opened_at is None:
                return
            if time.monotonic() - self._opened_at >= MODEL_CIRCUIT_RESET_SECONDS:
                self._opened_at = None
                self._failure_count = 0
                return
            raise CircuitOpenError("模型服务熔断中，请稍后重试")

    #记录成功
    async def _record_success(self) -> None:
        async with self._state_lock:
            self._failure_count = 0
            self._opened_at = None

    #记录失败
    async def _record_failure(self) -> None:
        async with self._state_lock:
            self._failure_count += 1
            if self._failure_count >= MODEL_CIRCUIT_FAILURE_THRESHOLD:
                self._opened_at = time.monotonic()

    #获取客户端
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None and not self._client.is_closed:
            return self._client
        async with self._client_lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    timeout=httpx.Timeout(MODEL_TIMEOUT_SECONDS),
                    limits=httpx.Limits(
                        max_connections=HTTP_MAX_CONNECTIONS,
                        max_keepalive_connections=HTTP_MAX_KEEPALIVE_CONNECTIONS,
                        keepalive_expiry=HTTP_KEEPALIVE_EXPIRY_SECONDS,
                    ),
                )
            return self._client

    #关闭客户端
    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    #获取模型名称
    @property
    def model_name(self) -> str:
        return MODEL_NAME

    #发送POST请求
    async def _post(self, url: str, headers: dict[str, str], payload: dict) -> dict:
        client = await self._get_client()
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            response.raise_for_status()
        response.encoding = "utf-8"
        return response.json()

    #流式聊天
    async def stream_chat(self, request: ModelChatRequest) -> AsyncIterator[str]:
        """Yield model deltas from an OpenAI-compatible SSE response."""
        started_at = time.perf_counter()
        await self._record_request_started()
        success = False
        if not MODEL_API_KEY:
            await self._record_request_finished(success=False, started_at=started_at)
            raise ModelGatewayError("MODEL_API_KEY is not configured")

        emitted = False
        try:
            await self._ensure_circuit()
            client = await self._get_client()
            url = f"{MODEL_API_BASE_URL.rstrip('/')}/chat/completions"
            headers = {
                "Authorization": f"Bearer {MODEL_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            }
            payload = {
                "model": MODEL_NAME,
                "messages": [message.model_dump() for message in request.messages],
                "temperature": request.temperature,
                "stream": True,
            }
            if request.max_tokens is not None:
                payload["max_tokens"] = request.max_tokens
            for attempt in range(MODEL_MAX_RETRIES + 1):
                try:
                    async with client.stream("POST", url, headers=headers, json=payload) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if not data or data == "[DONE]":
                                continue
                            event = json.loads(data)
                            delta = event.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                emitted = True
                                yield str(content)
                    success = True
                    await self._record_success()
                    return
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                    status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                    retryable = not emitted and (not isinstance(exc, httpx.HTTPStatusError) or status == 429 or status >= 500)
                    if retryable and attempt < MODEL_MAX_RETRIES:
                        await self._record_retry()
                        logger.warning("model_stream_retry attempt=%s error=%s status=%s", attempt + 1, type(exc).__name__, status)
                        await asyncio.sleep(min(1.0, 0.25 * (2 ** attempt)))
                        continue
                    raise
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            await self._record_failure()
            logger.warning("model_stream_failed error=%s detail=%s", type(exc).__name__, str(exc)[:300])
            raise ModelGatewayError(f"Model streaming API request failed: {exc}") from exc
        finally:
            await self._record_request_finished(success=success, started_at=started_at)

    #普通聊天
    async def chat(self, request: ModelChatRequest) -> ModelChatResponse:
        started_at = time.perf_counter()
        await self._record_request_started()
        if not MODEL_API_KEY:
            await self._record_request_finished(
                success=False,
                started_at=started_at,
            )
            raise ModelGatewayError("MODEL_API_KEY 未配置")
        try:
            await self._ensure_circuit()
        except CircuitOpenError:
            await self._record_circuit_rejection()
            await self._record_request_finished(
                success=False,
                started_at=started_at,
            )
            raise

        url = f"{MODEL_API_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {MODEL_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": MODEL_NAME,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": request.temperature,
            "stream": False,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        last_error: Exception | None = None
        for attempt in range(MODEL_MAX_RETRIES + 1):
            try:
                data = await self._post(url, headers, payload)
                content = data["choices"][0]["message"]["content"]
                usage = dict(data.get("usage") or {})
                usage["finish_reason"] = data.get("choices", [{}])[0].get("finish_reason")
                result = ModelChatResponse(
                    content=content,
                    model=data.get("model", MODEL_NAME),
                    usage=usage,
                )
                await self._record_success()
                await self._record_request_finished(
                    success=True,
                    started_at=started_at,
                )
                return result
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, KeyError,
                    IndexError, TypeError, ValueError) as exc:
                last_error = exc
                retryable = isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))
                if isinstance(exc, httpx.HTTPStatusError):
                    status = exc.response.status_code
                    retryable = status == 429 or status >= 500
                if not retryable or attempt >= MODEL_MAX_RETRIES:
                    break
                await self._record_retry()
                await asyncio.sleep(min(2.0, 0.25 * (2**attempt)))

        await self._record_failure()
        await self._record_request_finished(
            success=False,
            started_at=started_at,
        )
        raise ModelGatewayError(f"模型API调用失败: {last_error}") from last_error
