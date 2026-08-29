from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.orchestrator import Orchestrator
from app.agents.registry import build_default_registry
from app.evaluation.performance import run_performance_benchmark
from app.model_gateway import ModelGateway
from app.schemas import OrchestrationRequest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MoodApp orchestration performance benchmark.")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument("--output", default="reports/evaluation/performance.json")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.requests < 1:
        raise SystemExit("--requests must be >= 1")
    gateway = ModelGateway()
    orchestrator = Orchestrator(build_default_registry(gateway))
    requests = [
        OrchestrationRequest(message=f"性能测试样本 {index}：最近学习压力较大。")
        for index in range(args.requests)
    ]
    report = await run_performance_benchmark(
        orchestrator,
        requests,
        concurrency=args.concurrency,
        timeout_seconds=args.timeout_seconds,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    print(f"report_path={output}")


if __name__ == "__main__":
    asyncio.run(main())
