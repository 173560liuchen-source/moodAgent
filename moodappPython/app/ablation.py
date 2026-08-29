from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Iterator


@dataclass(frozen=True)
class AblationConfig:
    """Offline-only switches. Production requests never receive this object."""

    enable_safety_gate: bool = True
    enable_hierarchical_rag: bool = True
    enable_reranker: bool = True
    enable_evaluator: bool = True
    enable_follow_up_loop: bool = True
    enable_risk_router: bool = True

    @classmethod
    def from_mapping(cls, raw: dict[str, object] | None) -> "AblationConfig":
        raw = raw or {}
        known = {key: bool(raw[key]) for key in asdict(cls()).keys() if key in raw}
        return cls(**known)

    def model_dump(self) -> dict[str, bool]:
        return asdict(self)


_ACTIVE_ABLATION: ContextVar[AblationConfig | None] = ContextVar(
    "active_offline_ablation",
    default=None,
)


@contextmanager
def offline_ablation(config: AblationConfig) -> Iterator[None]:
    """Temporarily activate switches inside the local evaluation runner only."""
    token = _ACTIVE_ABLATION.set(config)
    try:
        yield
    finally:
        _ACTIVE_ABLATION.reset(token)


def active_ablation() -> AblationConfig:
    """Public traffic never activates this context, so it always uses the full system."""
    return _ACTIVE_ABLATION.get() or AblationConfig()
