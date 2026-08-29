from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.orchestrator import Orchestrator
from app.agents.registry import build_default_registry
from app.evaluation import (
    RedTeamEvaluationRunner,
    RedTeamRunRequest,
    build_evaluation_summary,
    save_evaluation_artifacts,
)
from app.ablation import AblationConfig
from app.model_gateway import ModelGateway


DEFAULT_ABLATION_CONFIG = PROJECT_ROOT / "config" / "ablation_switches.json"


def _load_ablation_config(path: Path) -> dict[str, bool]:
    """Load editable offline experiment switches, defaulting safely to all enabled."""
    if not path.exists():
        raise FileNotFoundError(f"Ablation config not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Ablation config must be a JSON object.")
    return AblationConfig.from_mapping(raw).model_dump()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MoodApp red-team evaluation.")
    parser.add_argument("--category", action="append", default=[], help="Filter category. Can be used multiple times.")
    parser.add_argument("--tag", action="append", default=[], help="Filter tag. Can be used multiple times.")
    parser.add_argument("--case-id", action="append", default=[], help="Filter case id. Can be used multiple times.")
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--include-raw-outputs", action="store_true")
    parser.add_argument("--timeout-seconds-per-case", type=float, default=45.0)
    parser.add_argument("--output", default=None, help="JSON report output path.")
    parser.add_argument("--summary-output", default=None, help="Summary JSON output path.")
    parser.add_argument("--markdown-output", default=None, help="Markdown report output path.")
    parser.add_argument("--final-report", action="store_true", help="Write redteam_full.json, redteam_summary.json and redteam_report.md.")
    parser.add_argument(
        "--ablation-config",
        default=str(DEFAULT_ABLATION_CONFIG),
        help="Offline switch JSON. All switches are true by default.",
    )
    parser.add_argument(
        "--disable", action="append", default=[],
        choices=("safety_gate", "hierarchical_rag", "reranker", "evaluator", "follow_up_loop", "risk_router"),
        help="Offline ablation only. May be repeated; public API requests always keep all modules enabled.",
    )
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    gateway = ModelGateway()
    registry = build_default_registry(gateway)
    runner = RedTeamEvaluationRunner(Orchestrator(registry))
    ablation = _load_ablation_config(Path(args.ablation_config))
    for name in args.disable:
        ablation[f"enable_{name}"] = False
    report = await runner.run(
        RedTeamRunRequest(
            categories=args.category,
            tags=args.tag,
            case_ids=args.case_id,
            max_cases=args.max_cases,
            include_raw_outputs=args.include_raw_outputs,
            timeout_seconds_per_case=args.timeout_seconds_per_case,
            ablation=ablation,
        )
    )

    payload = report.model_dump(mode="json")
    output = args.output
    if not output:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = str(Path("reports") / "evaluation" / f"redteam_{stamp}.json")
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary = build_evaluation_summary(report)
    if args.summary_output:
        summary_path = Path(args.summary_output)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"summary_path={summary_path}")
    if args.markdown_output:
        from app.evaluation.reporter import render_markdown_report

        markdown_path = Path(args.markdown_output)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            render_markdown_report(report, summary),
            encoding="utf-8",
        )
        print(f"markdown_path={markdown_path}")
    if args.final_report:
        artifacts = save_evaluation_artifacts(report)
        print(json.dumps({"artifacts": artifacts}, ensure_ascii=False, indent=2))
    disabled_components = [
        name.removeprefix("enable_")
        for name, enabled in ablation.items()
        if not enabled
    ]
    metric_names = (
        "rag_expectation_pass_rate",
        "rag_category_recall",
        "rag_document_recall_at_5",
        "rag_mrr_at_5",
        "rag_citation_precision",
        "rag_groundedness",
    )
    core_rag_metrics = {
        name: payload["metrics"].get(name)
        for name in metric_names
    }
    experiment_result = {
        "experiment": "完整系统基线" if not disabled_components else "消融实验",
        "disabled_components": disabled_components,
        "switches": ablation,
        "rag_metrics": core_rag_metrics,
    }
    print("\n===== 消融实验结果 =====")
    print(json.dumps(experiment_result, ensure_ascii=False, indent=2))
    print(f"report_path={output_path}")


if __name__ == "__main__":
    asyncio.run(_main())
