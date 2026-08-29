import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .model_gateway import ModelGateway, ModelGatewayError
from .agents.chat_agent import ChatAgent
from .agents.assessment_report_agent import AssessmentReportAgent
from .agents.emotion_agent import EmotionAgent
from .agents.crisis_agent import CrisisAgent
from .agents.orchestrator import Orchestrator
from .agents.trend_agent import EmotionPoint, TrendAgent
from .agents.crisis_agent import CrisisAnalysis
from .agents.emotion_agent import EmotionAnalysis
from .agents.risk_agent import RiskAgent
from .agents.rag_agent import RAGAgent, RAGAnalysis
from .agents.safety_gate import SafetyGateAgent
from .agents.registry import build_default_registry
from .agents.trend_agent import TrendAnalysis
from .config import (
    EMBEDDING_MODEL,
    PGVECTOR_SCHEMA,
    PGVECTOR_TABLE,
    POSTGRES_CONNECT_TIMEOUT_SECONDS,
    VECTOR_STORE_BACKEND,
)
from .rag.contracts import KNOWLEDGE_CATEGORIES
from .rag.vector_store import PgVectorKnowledgeStore
from .evaluation import (
    RedTeamEvaluationRunner,
    RedTeamRunRequest,
    build_evaluation_summary,
    load_redteam_cases,
    save_evaluation_artifacts,
)
from .schemas import (
    ChatAgentRequest,
    ChatAgentResponse,
    EmotionAgentRequest,
    CrisisAgentRequest,
    OrchestrationRequest,
    TrendAgentRequest,
    RiskAgentRequest,
    RAGSearchRequest,
    SafetyGateEndpointRequest,
    ModelChatRequest,
    ModelChatResponse,
    AssessmentReportRequest,
    AssessmentReportResponse,
)

app = FastAPI(
    title="MoodApp Agent Service",
    version="0.1.0",
    description="Java 后端调用的自主多智能体服务。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

model_gateway = ModelGateway()
agent_registry = build_default_registry(model_gateway)
chat_agent = ChatAgent(model_gateway)
assessment_report_agent = AssessmentReportAgent(model_gateway)
emotion_agent = EmotionAgent(model_gateway)
crisis_agent = CrisisAgent(model_gateway)
orchestrator = Orchestrator(agent_registry)
trend_agent = TrendAgent()
risk_agent = RiskAgent()
rag_agent = RAGAgent()
safety_gate_agent = SafetyGateAgent()
redteam_runner = RedTeamEvaluationRunner(orchestrator)
EVALUATION_REPORT_DIR = Path(__file__).resolve().parents[1] / "reports" / "evaluation"


@app.on_event("shutdown")
async def close_http_clients() -> None:
    await model_gateway.aclose()
    await rag_agent.aclose()
    await orchestrator.rag_agent.aclose()


@app.get("/health")
async def health() -> dict:
    """服务健康检查；第一步不连接模型或数据库。"""
    # 获取模型网关当前状态
    model_status = await model_gateway.snapshot()
    return {
        "status": "ok",
        "service": "moodapp-agent",
        "version": app.version,
        "time": datetime.now(timezone.utc).isoformat(),
        "model_gateway": {
            "configured": model_status["configured"],     # API Key 是否配置了
            "circuit_state": model_status["circuit"]["state"],  # 熔断器状态
        },
    }


@app.get("/health/live")
async def liveness() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "moodapp-agent",
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health/ready")
async def readiness() -> JSONResponse:
    model_status = await model_gateway.snapshot()
    ready = (
        model_status["configured"]
        and model_status["circuit"]["state"] != "open"
    )
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "not_ready",
            "service": "moodapp-agent",
            "checks": {
                "model_api_key_configured": model_status["configured"],
                "model_circuit_state": model_status["circuit"]["state"],
            },
            "time": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.get("/v1/metrics/model")
async def model_metrics() -> dict:
    return await model_gateway.snapshot()


@app.post("/v1/model/chat", response_model=ModelChatResponse)
async def model_chat(request: ModelChatRequest) -> ModelChatResponse:
    try:
        return await model_gateway.chat(request)
    except ModelGatewayError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/agents/chat", response_model=ChatAgentResponse)
async def agent_chat(request: ChatAgentRequest) -> ChatAgentResponse:
    try:
        result = await chat_agent.respond(request.message, request.history)
        return ChatAgentResponse(content=result.content, model=result.model, usage=result.usage)
    except ModelGatewayError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/agents/assessment-report", response_model=AssessmentReportResponse)
async def assessment_report(request: AssessmentReportRequest) -> AssessmentReportResponse:
    """供 Java 测评模块调用；生成和模型调用统一收口在 Python。"""
    try:
        report, model_response = await assessment_report_agent.generate(
            score=request.score,
            level=request.level,
            answers=request.answers,
        )
        return AssessmentReportResponse(
            **report,
            model=model_response.model,
            usage=model_response.usage,
        )
    except (ModelGatewayError, ValueError, json.JSONDecodeError) as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/agents/emotion", response_model=dict)
async def agent_emotion(request: EmotionAgentRequest) -> dict:
    try:
        result = await emotion_agent.analyze(request.message, request.history)
        return {"agent": "emotion", **result.model_dump()}
    except ModelGatewayError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/agents/crisis", response_model=dict)
async def agent_crisis(request: CrisisAgentRequest) -> dict:
    try:
        result = await crisis_agent.assess(request.message, request.history)
        return {"agent": "crisis", **result.model_dump()}
    except ModelGatewayError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _orchestration_payload(request: OrchestrationRequest, result) -> dict:
    return {
            "agent": "orchestrator",
            "request_id": request.context.request_id,
            "session_id": request.context.session_id,
            "safety": result.safety.model_dump(),
            "reply": result.reply,
            "model": result.model,
            "crisis": result.crisis.model_dump(),
            "emotion": result.emotion.model_dump() if result.emotion else None,
            "rag": result.rag.model_dump() if result.rag else None,
            "trend": result.trend.model_dump() if result.trend else None,
            "risk": result.risk.model_dump() if result.risk else None,
            "profile": result.profile.model_dump() if result.profile else None,
            "intervention": result.intervention.model_dump() if result.intervention else None,
            "follow_up": result.follow_up.model_dump() if result.follow_up else None,
            "evaluator": result.evaluator.model_dump() if result.evaluator else None,
            "audit": result.audit.model_dump() if result.audit else None,
            "trace": result.trace,
            "trace_events": [event.model_dump(mode="json") for event in result.trace_events],
        }


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


@app.post("/v1/agents/orchestrate", response_model=dict)
async def orchestrate(request: OrchestrationRequest) -> dict:
    try:
        result = await orchestrator.run(request)
        return _orchestration_payload(request, result)
    except ModelGatewayError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/agents/orchestrate/stream")
async def orchestrate_stream(request: OrchestrationRequest) -> StreamingResponse:
    queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

    async def on_chunk(content: str) -> None:
        await queue.put(("delta", {"content": content}))

    async def produce() -> None:
        try:
            result = await orchestrator.run_stream(request, on_chunk)
            await queue.put(("result", _orchestration_payload(request, result)))
            await queue.put(("done", {"status": "completed"}))
        except Exception as exc:
            await queue.put(("error", {"message": str(exc)}))
        finally:
            await queue.put(None)

    async def events():
        task = asyncio.create_task(produce())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield _sse(item[0], item[1])
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/v1/agents/greeting/stream")
async def greeting_stream(request: OrchestrationRequest) -> StreamingResponse:
    """Fast proactive greeting path: safety gate plus dialogue only."""
    queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

    async def on_chunk(content: str) -> None:
        await queue.put(("delta", {"content": content}))

    async def produce() -> None:
        try:
            safety = await safety_gate_agent.assess(request.message, request.context)
            if safety.decision in {"block", "escalate"}:
                reply = "我在这里陪着你。如果你此刻有伤害自己或他人的危险，请立即联系身边可信任的人或当地急救服务。"
                await on_chunk(reply)
                model = "safety_fallback"
            else:
                response = await chat_agent.respond_stream(
                    safety.redacted_message,
                    request.history[-6:],
                    on_chunk=on_chunk,
                )
                reply = response.content
                model = response.model
            payload = {
                "agent": "orchestrator",
                "request_id": request.context.request_id,
                "session_id": request.context.session_id,
                "safety": safety.model_dump(),
                "reply": reply,
                "model": model,
                "trace": ["safety_gate", "chat_agent"],
                "trace_events": [],
            }
            await queue.put(("result", payload))
            await queue.put(("done", {"status": "completed"}))
        except Exception as exc:
            await queue.put(("error", {"message": str(exc)}))
        finally:
            await queue.put(None)

    async def events():
        task = asyncio.create_task(produce())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield _sse(item[0], item[1])
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/v1/agents/trend", response_model=dict)
async def agent_trend(request: TrendAgentRequest) -> dict:
    points = [EmotionPoint.model_validate(point) for point in request.points]
    return {"agent": "trend", **trend_agent.analyze(points).model_dump()}


@app.post("/v1/agents/risk", response_model=dict)
async def agent_risk(request: RiskAgentRequest) -> dict:
    crisis = CrisisAnalysis.model_validate(request.crisis)
    emotion = EmotionAnalysis.model_validate(request.emotion)
    trend = TrendAnalysis.model_validate(request.trend) if request.trend else None
    rag = RAGAnalysis.model_validate(request.rag) if request.rag else None
    return {"agent": "risk", **risk_agent.assess(crisis, emotion, trend, rag).model_dump()}


def _rag_status_snapshot() -> dict:
    store = PgVectorKnowledgeStore()
    chunk_count = store.count()
    document_count = 0
    category_counts: dict[str, dict[str, int]] = {
        category: {"document_count": 0, "chunk_count": 0}
        for category in KNOWLEDGE_CATEGORIES
    }
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(DISTINCT document_id) FROM {store.config.full_table_name}")
            document_count = int(cur.fetchone()[0])
            cur.execute(
                f"""
                SELECT category, COUNT(DISTINCT document_id), COUNT(*)
                FROM {store.config.full_table_name}
                GROUP BY category
                """
            )
            for category, docs, chunks in cur.fetchall():
                category_counts[str(category)] = {
                    "document_count": int(docs),
                    "chunk_count": int(chunks),
                }
    return {
        "status": "ready" if chunk_count > 0 else "empty",
        "vector_store": VECTOR_STORE_BACKEND,
        "collection": f"{PGVECTOR_SCHEMA}.{PGVECTOR_TABLE}",
        "embedding_model": EMBEDDING_MODEL,
        "document_count": document_count,
        "chunk_count": chunk_count,
        "categories": list(KNOWLEDGE_CATEGORIES),
        "category_counts": category_counts,
        "evidence_policy": "only_return_real_retrieved_citations",
    }


@app.get("/v1/rag/status", response_model=dict)
async def rag_status() -> dict:
    """快速返回知识库状态，不能让不可用的向量库拖住整个页面。"""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_rag_status_snapshot),
            timeout=POSTGRES_CONNECT_TIMEOUT_SECONDS + 1,
        )
    except Exception as exc:  # noqa: BLE001 - database driver exceptions vary by deployment.
        return {
            "status": "unavailable",
            "vector_store": VECTOR_STORE_BACKEND,
            "collection": f"{PGVECTOR_SCHEMA}.{PGVECTOR_TABLE}",
            "embedding_model": EMBEDDING_MODEL,
            "document_count": 0,
            "chunk_count": 0,
            "categories": list(KNOWLEDGE_CATEGORIES),
            "category_counts": {},
            "evidence_policy": "only_return_real_retrieved_citations",
            "message": "知识库暂时不可用，请检查向量数据库连接。",
            "error_code": exc.__class__.__name__,
        }


@app.post("/v1/rag/search", response_model=dict)
async def rag_search(request: RAGSearchRequest) -> dict:
    result = await rag_agent.retrieve(
        request.query,
        request.history,
        top_k=request.top_k,
        min_score=request.min_score,
    )
    return result.model_dump(mode="json")


@app.post("/v1/agents/safety", response_model=dict)
async def agent_safety(request: SafetyGateEndpointRequest) -> dict:
    result = await safety_gate_agent.assess(request.message)
    return {"agent": "safety_gate", **result.model_dump()}


@app.get("/v1/agents/registry", response_model=list[dict])
async def list_agents() -> list[dict]:
    return [
        {
            "name": item.name,
            "version": item.version,
            "capabilities": item.capabilities,
            "criticality": item.criticality,
        }
        for item in agent_registry.list()
    ]


@app.get("/v1/evaluation/redteam/cases", response_model=list[dict])
async def list_redteam_cases() -> list[dict]:
    return [
        case.model_dump(mode="json", exclude={"message", "history"})
        for case in load_redteam_cases()
    ]


@app.get("/v1/evaluation/redteam/latest-summary", response_model=dict)
async def latest_redteam_summary() -> JSONResponse:
    path = EVALUATION_REPORT_DIR / "redteam_summary.json"
    if not path.exists():
        return JSONResponse(
            status_code=404,
            content={"status": "missing", "message": "暂无评测摘要，请先运行红队评测。"},
        )
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))


@app.get("/v1/evaluation/redteam/latest-report", response_model=dict)
async def latest_redteam_report() -> JSONResponse:
    path = EVALUATION_REPORT_DIR / "redteam_full.json"
    if not path.exists():
        return JSONResponse(
            status_code=404,
            content={"status": "missing", "message": "暂无完整评测报告，请先运行红队评测。"},
        )
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))


@app.get("/v1/evaluation/performance/latest", response_model=dict)
async def latest_performance_report() -> JSONResponse:
    path = EVALUATION_REPORT_DIR / "performance.json"
    if not path.exists():
        return JSONResponse(
            status_code=404,
            content={"status": "missing", "message": "暂无性能测试报告，请先运行性能测试。"},
        )
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))


@app.post("/v1/evaluation/redteam/run", response_model=dict)
async def run_redteam_evaluation(request: RedTeamRunRequest | None = None) -> dict:
    report = await redteam_runner.run(request or RedTeamRunRequest())
    # “运行全部测试”完成后立即覆盖 latest-report/latest-summary 所读取的文件，
    # 确保页面退出再进入时仍显示本轮结果。
    save_evaluation_artifacts(report, output_dir=EVALUATION_REPORT_DIR)
    return report.model_dump(mode="json")


@app.post("/v1/evaluation/redteam/summary", response_model=dict)
async def summarize_redteam_evaluation(request: RedTeamRunRequest | None = None) -> dict:
    report = await redteam_runner.run(request or RedTeamRunRequest())
    return build_evaluation_summary(report)


@app.post("/v1/evaluation/redteam/final-report", response_model=dict)
async def generate_redteam_final_report(request: RedTeamRunRequest | None = None) -> dict:
    report = await redteam_runner.run(request or RedTeamRunRequest())
    artifacts = save_evaluation_artifacts(report)
    return {
        "status": "generated",
        "artifacts": artifacts,
        "summary": build_evaluation_summary(report),
    }
