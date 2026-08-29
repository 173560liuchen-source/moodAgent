from __future__ import annotations

import asyncio
from typing import Any

import httpx

from ..config import (
    EMBEDDING_API_BASE_URL,
    EMBEDDING_API_KEY,
    EMBEDDING_MAX_RETRIES,
    EMBEDDING_MODEL,
    EMBEDDING_TIMEOUT_SECONDS,
    HTTP_KEEPALIVE_EXPIRY_SECONDS,
    HTTP_MAX_CONNECTIONS,
    HTTP_MAX_KEEPALIVE_CONNECTIONS,
)


class EmbeddingGatewayError(RuntimeError):
    pass


class EmbeddingConfigurationError(EmbeddingGatewayError):
    pass


class EmbeddingGateway:
    def __init__(
        self,
        *,
        api_base_url: str = EMBEDDING_API_BASE_URL,
        api_key: str = EMBEDDING_API_KEY,
        model: str = EMBEDDING_MODEL,
        timeout_seconds: float = EMBEDDING_TIMEOUT_SECONDS,
        max_retries: int = EMBEDDING_MAX_RETRIES,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    def ensure_configured(self) -> None:
        if not self.api_base_url:
            raise EmbeddingConfigurationError("EMBEDDING_API_BASE_URL is not configured")
        if not self.api_key:
            raise EmbeddingConfigurationError("EMBEDDING_API_KEY is not configured")
        if not self.model:
            raise EmbeddingConfigurationError("EMBEDDING_MODEL is not configured")

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.ensure_configured()
        clean_texts = [text.strip() for text in texts]
        if not clean_texts:
            return []
        if any(not text for text in clean_texts):
            raise EmbeddingGatewayError("Embedding input contains empty text")

        payload = {
            "model": self.model,
            "input": clean_texts,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.api_base_url}/embeddings"

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                data = await self._post(url, headers, payload)
                return self._extract_embeddings(data, expected_count=len(clean_texts))
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, KeyError, TypeError, ValueError) as exc:
                last_error = exc
                retryable = isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))
                if isinstance(exc, httpx.HTTPStatusError):
                    status_code = exc.response.status_code
                    retryable = status_code == 429 or status_code >= 500
                if not retryable or attempt >= self.max_retries:
                    break
                await asyncio.sleep(min(2.0, 0.25 * (2**attempt)))

        raise EmbeddingGatewayError(f"Embedding API call failed: {last_error}") from last_error

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None and not self._client.is_closed:
            return self._client
        async with self._client_lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    timeout=httpx.Timeout(self.timeout_seconds),
                    limits=httpx.Limits(
                        max_connections=HTTP_MAX_CONNECTIONS,
                        max_keepalive_connections=HTTP_MAX_KEEPALIVE_CONNECTIONS,
                        keepalive_expiry=HTTP_KEEPALIVE_EXPIRY_SECONDS,
                    ),
                )
            return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def _post(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
        client = await self._get_client()
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            response.raise_for_status()
        response.encoding = "utf-8"
        return response.json()

    @staticmethod
    def _extract_embeddings(data: dict[str, Any], *, expected_count: int) -> list[list[float]]:
        rows = data["data"]
        if not isinstance(rows, list):
            raise ValueError("Embedding response data must be a list")
        if len(rows) != expected_count:
            raise ValueError(
                f"Embedding response count mismatch: expected {expected_count}, got {len(rows)}"
            )

        rows = sorted(rows, key=lambda row: row.get("index", 0))
        embeddings: list[list[float]] = []
        dimensions: int | None = None

        for row in rows:
            vector = row["embedding"]
            if not isinstance(vector, list) or not vector:
                raise ValueError("Embedding vector must be a non-empty list")
            numeric_vector = [float(value) for value in vector]
            if dimensions is None:
                dimensions = len(numeric_vector)
            elif len(numeric_vector) != dimensions:
                raise ValueError("Embedding dimensions are inconsistent in one response")
            embeddings.append(numeric_vector)

        return embeddings
