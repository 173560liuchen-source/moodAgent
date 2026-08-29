from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

from ..core.contracts import AgentContext
from ..schemas import OrchestrationRequest
from ..ablation import AblationConfig, offline_ablation
from .cases import load_redteam_cases
from .fault_injection import build_fault_injected_orchestrator
from .metrics import build_metric_report, evaluate_case_output
from .schemas import (
    RedTeamCase,
    RedTeamCaseResult,
    RedTeamEvaluationReport,
    RedTeamRunRequest,
)


class RedTeamEvaluationRunner:
    """自动化红队评测运行器。

    只消费合成测试样本，不保存真实用户聊天记录。所有原始输出默认不返回，避免把过长对话内容写入报告。
    """

    def __init__(self, orchestrator: Any) -> None:
        self.orchestrator = orchestrator

    @staticmethod
    def _filter_cases(
        cases: list[RedTeamCase],
        request: RedTeamRunRequest,
    ) -> list[RedTeamCase]:
        selected = cases
        if request.case_ids:
            case_ids = set(request.case_ids)
            selected = [case for case in selected if case.case_id in case_ids]
        if request.categories:
            categories = set(request.categories)
            selected = [case for case in selected if case.category in categories]
        if request.tags:
            tags = set(request.tags)
            selected = [case for case in selected if tags.intersection(case.tags)]
        if request.max_cases is not None:
            selected = selected[: request.max_cases]
        return selected

    async def run(self, request: RedTeamRunRequest | None = None) -> RedTeamEvaluationReport:
        request = request or RedTeamRunRequest()
        cases = self._filter_cases(load_redteam_cases(), request)
        results: list[RedTeamCaseResult] = []

        for case in cases:
            results.append(await self._run_one(case, request))

        metrics = build_metric_report(cases, results)
        notes = [
            "红队样本均为本地合成数据，不包含真实用户聊天记录。",
            "model_failure_fallback_success_rate 只有在加入故障注入样本后才会计算；当前无样本时返回 null。",
            "RAG 引用准确率按引用字段完整性和预期有无依据计算，不让模型伪造引用。",
            "默认不返回 raw_output，避免把过长模型输出写入评测报告。",
        ]
        return RedTeamEvaluationReport(
            metrics=metrics,
            cases=results,
            ablation=AblationConfig.from_mapping(request.ablation).model_dump(),
            notes=notes,
        )

    async def _run_one(
        self,
        case: RedTeamCase,
        request: RedTeamRunRequest,
    ) -> RedTeamCaseResult:
        started = perf_counter()
        output: dict[str, Any] | None = None
        error: str | None = None
        try:
            case_orchestrator = (
                build_fault_injected_orchestrator(case.expectation.inject_fault)
                if case.expectation.inject_fault != "none"
                else self.orchestrator
            )
            orchestration_request = OrchestrationRequest(
                message=case.message,
                history=case.history,
                context=AgentContext(
                    metadata={
                        **case.context_metadata,
                        "evaluation": {
                            "case_id": case.case_id,
                            "category": case.category,
                            "tags": case.tags,
                            "inject_fault": case.expectation.inject_fault,
                            "ablation": request.ablation,
                        }
                    }
                ),
            )
            with offline_ablation(AblationConfig.from_mapping(request.ablation)):
                result = await asyncio.wait_for(
                    case_orchestrator.run(orchestration_request),
                    timeout=request.timeout_seconds_per_case,
                )
            output = {
                "agent": "orchestrator",
                "request_id": orchestration_request.context.request_id,
                "session_id": orchestration_request.context.session_id,
                "safety": result.safety.model_dump(),
                "reply": result.reply,
                "model": result.model,
                "crisis": result.crisis.model_dump(),
                "emotion": result.emotion.model_dump() if result.emotion else None,
                "rag": result.rag.model_dump() if result.rag else None,
                "profile": result.profile.model_dump() if result.profile else None,
                "intervention": result.intervention.model_dump() if result.intervention else None,
                "evaluator": result.evaluator.model_dump() if result.evaluator else None,
                "audit": result.audit.model_dump() if result.audit else None,
                "trace": result.trace,
                "trace_events": [
                    event.model_dump(mode="json") for event in result.trace_events
                ],
            }
        except Exception as exc:  # noqa: BLE001 - 评测报告需要记录任意失败类型。
            error = f"{type(exc).__name__}: {exc}"

        latency_ms = round((perf_counter() - started) * 1000)
        return evaluate_case_output(
            case,
            output,
            latency_ms=latency_ms,
            error=error,
            include_raw_output=request.include_raw_outputs,
        )
