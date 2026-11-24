import asyncio
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

from app.embedding_usage import (
    SOURCE_PROVIDER_USAGE,
    note_request,
    record_usage,
    start_capture,
    take_capture,
    to_report_fields,
)
from app.evaluation import CaseResult, EvalDataset, _build_report, _render_markdown
from app.providers_setup import _UsageCapturingEmbeddingsResource


class _FakeResource:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    async def create(self, *args, **kwargs):
        self.calls += 1
        return self.response


class CaptureTests(unittest.TestCase):
    def setUp(self):
        take_capture()

    def tearDown(self):
        take_capture()

    def test_provider_usage_is_recorded(self):
        start_capture()
        note_request()
        record_usage(17, 17)
        self.assertEqual(
            to_report_fields(take_capture()), (17, 1, SOURCE_PROVIDER_USAGE)
        )

    def test_no_capture_yields_none(self):
        self.assertEqual(to_report_fields(take_capture()), (None, 0, None))

    def test_zero_requests_differs_from_missing_usage(self):
        start_capture()
        zero_requests = to_report_fields(take_capture())
        start_capture()
        note_request()
        missing_usage = to_report_fields(take_capture())
        self.assertEqual(zero_requests, (None, 0, None))
        self.assertEqual(missing_usage, (None, 1, None))

    def test_malformed_usage_is_ignored(self):
        start_capture()
        note_request()
        record_usage("bukan angka")
        record_usage(None)
        record_usage(-1)
        self.assertEqual(to_report_fields(take_capture()), (None, 1, None))

    def test_concurrent_captures_do_not_mix(self):
        async def work(prompt, label):
            start_capture()
            await asyncio.sleep(0)
            note_request()
            record_usage(prompt, prompt)
            await asyncio.sleep(0)
            return label, to_report_fields(take_capture())

        async def main():
            return await asyncio.gather(work(3, "a"), work(11, "b"))

        results = dict(asyncio.run(main()))
        self.assertEqual(results["a"], (3, 1, SOURCE_PROVIDER_USAGE))
        self.assertEqual(results["b"], (11, 1, SOURCE_PROVIDER_USAGE))


class ProviderHookTests(unittest.TestCase):
    def setUp(self):
        take_capture()

    def tearDown(self):
        take_capture()

    def _run(self, response):
        resource = _UsageCapturingEmbeddingsResource(_FakeResource(response))
        start_capture()
        returned = asyncio.run(resource.create(input=["teks"]))
        return returned, to_report_fields(take_capture())

    def test_object_usage_is_recorded(self):
        response = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=9, total_tokens=9)
        )
        returned, fields = self._run(response)
        self.assertIs(returned, response)
        self.assertEqual(fields, (9, 1, SOURCE_PROVIDER_USAGE))

    def test_dict_usage_is_recorded(self):
        _, fields = self._run(
            SimpleNamespace(usage={"prompt_tokens": 5, "total_tokens": 5})
        )
        self.assertEqual(fields, (5, 1, SOURCE_PROVIDER_USAGE))

    def test_missing_usage_is_not_reported_as_zero(self):
        _, fields = self._run(SimpleNamespace())
        self.assertEqual(fields, (None, 1, None))

    def test_malformed_usage_is_ignored(self):
        _, fields = self._run(SimpleNamespace(usage="rusak"))
        self.assertEqual(fields, (None, 1, None))


class ReportTests(unittest.TestCase):
    @staticmethod
    def _case(case_id, baseline, **kwargs):
        return CaseResult(
            case_id=case_id,
            baseline=baseline,
            question="Apa isi dokumen?",
            expected_refusal=False,
            reference_answer=None,
            **kwargs,
        )

    @staticmethod
    def _report(results, baselines=("A", "B")):
        dataset = EvalDataset(cases=(), owner_authored=True)
        return _build_report(
            dataset, baselines, results, None, datetime.now(UTC), False
        )

    def test_report_uses_real_tokens_and_marks_baseline_a_empty(self):
        results = [
            self._case("q1", "A"),
            self._case(
                "q1",
                "B",
                embedding_tokens=17,
                embedding_requests=2,
                embedding_tokens_source=SOURCE_PROVIDER_USAGE,
            ),
        ]
        report = self._report(results)
        self.assertEqual(report["run"]["embedding_tokens"], 17)
        self.assertEqual(report["run"]["embedding_tokens_source"], SOURCE_PROVIDER_USAGE)
        self.assertIsNone(report["summaries"]["A"]["embedding_tokens"])
        self.assertEqual(report["summaries"]["B"]["embedding_tokens"], 17)
        self.assertEqual(report["summaries"]["B"]["embedding_requests"], 2)
        self.assertIn("bukan estimasi", report["run"]["embedding_tokens_note"])
        markdown = _render_markdown(report)
        self.assertIn("Token embedding (aktual): 17", markdown)
        self.assertIn("Token embedding |", markdown)

    def test_unavailable_usage_is_null_not_zero(self):
        results = [self._case("q1", "B", embedding_requests=2)]
        report = self._report(results, ("B",))
        self.assertIsNone(report["run"]["embedding_tokens"])
        self.assertIsNone(report["summaries"]["B"]["embedding_tokens"])
        markdown = _render_markdown(report)
        self.assertIn("Token embedding (aktual): tidak tersedia", markdown)
        self.assertNotIn("Token embedding (aktual): 0", markdown)


if __name__ == "__main__":
    unittest.main()
