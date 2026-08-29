import unittest
from unittest.mock import AsyncMock, patch

from app import main
from app.evaluation.schemas import RedTeamEvaluationReport, RedTeamMetricReport


class EvaluationApiPersistenceTest(unittest.IsolatedAsyncioTestCase):
    async def test_run_endpoint_saves_latest_report_artifacts(self):
        report = RedTeamEvaluationReport(
            metrics=RedTeamMetricReport(
                total_cases=1,
                passed_cases=1,
                failed_cases=0,
                pass_rate=1.0,
            ),
            cases=[],
        )

        with (
            patch.object(main.redteam_runner, "run", AsyncMock(return_value=report)),
            patch("app.main.save_evaluation_artifacts") as save_artifacts,
        ):
            response = await main.run_redteam_evaluation()

        save_artifacts.assert_called_once_with(
            report,
            output_dir=main.EVALUATION_REPORT_DIR,
        )
        self.assertEqual(response["metrics"]["pass_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
