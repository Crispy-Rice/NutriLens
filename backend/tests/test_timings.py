"""Timing instrumentation tests.

The value of the breakdown is that it distinguishes the three very different
causes of "it's slow": image preprocessing, request/prefill, and generation.
These tests cover the log line, the response header, and the thinking-mode
warning that names the most common cause outright.
"""

from __future__ import annotations

import logging

from app.services.analysis_service import Timings, _collect_timings, log_timings
from app.services.llm.base import CallMetrics, TokenUsage


def test_header_is_machine_parseable():
    timings = Timings(
        prep_ms=132,
        request_ms=3100,
        first_token_ms=3400,
        generation_ms=18400,
        total_ms=21832,
        output_chars=980,
        prompt_tokens=1500,
        completion_tokens=812,
    )
    header = timings.as_header()

    parsed = dict(
        part.split("=", 1) for part in header.split(";")
    )
    assert parsed["prep"] == "132"
    assert parsed["request"] == "3100"
    assert parsed["first_token"] == "3400"
    assert parsed["gen"] == "18400"
    assert parsed["total"] == "21832"
    assert parsed["out_chars"] == "980"
    assert parsed["completion_tokens"] == "812"


def test_header_marks_missing_values_as_na():
    header = Timings(prep_ms=10, total_ms=10).as_header()
    assert "first_token=n/a" in header
    assert "prompt_tokens=n/a" in header
    assert "completion_tokens=n/a" in header


def test_collect_timings_reads_from_call_metrics():
    metrics = CallMetrics(
        request_ms=300,
        first_token_ms=350,
        generation_ms=900,
        usage=TokenUsage(prompt_tokens=1200, completion_tokens=400, total_tokens=1600),
        reasoning_chars=12,
    )

    timings = _collect_timings(metrics, prep_ms=100, model_ms=1200, output_chars=500)

    assert timings.prep_ms == 100
    assert timings.request_ms == 300
    assert timings.first_token_ms == 350
    assert timings.generation_ms == 900
    # total is server-side wall clock: preprocessing plus the model call.
    assert timings.total_ms == 1300
    assert timings.output_chars == 500
    assert timings.prompt_tokens == 1200
    assert timings.completion_tokens == 400
    assert timings.reasoning_chars == 12


def test_collect_timings_tolerates_a_vendor_without_usage():
    timings = _collect_timings(CallMetrics(), prep_ms=50, model_ms=800, output_chars=100)

    assert timings.prompt_tokens is None
    assert timings.completion_tokens is None
    assert timings.first_token_ms is None
    assert timings.reasoning_chars == 0
    assert timings.total_ms == 850


def test_log_line_carries_the_breakdown(caplog):
    with caplog.at_level(logging.INFO):
        log_timings(
            Timings(
                prep_ms=120,
                request_ms=3000,
                first_token_ms=3300,
                generation_ms=12000,
                total_ms=15120,
                output_chars=900,
                completion_tokens=700,
            ),
            provider="openai_compat",
            mode="detailed",
        )

    text = caplog.text
    assert "prep=120ms" in text
    assert "request=3000ms" in text
    assert "first_token=3300ms" in text
    assert "gen=12000ms" in text
    assert "total=15120ms" in text
    assert "completion_tokens=700" in text


def test_explicit_reasoning_output_raises_a_warning(caplog):
    """Definitive proof thinking is on: the vendor sent reasoning text."""
    with caplog.at_level(logging.INFO):
        log_timings(
            Timings(
                prep_ms=100,
                total_ms=45000,
                output_chars=900,
                completion_tokens=4000,
                reasoning_chars=5200,
            ),
            provider="openai_compat",
            mode="detailed",
        )

    assert "思考内容" in caplog.text
    assert "LLM_ENABLE_THINKING" in caplog.text
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_suspicious_token_ratio_raises_a_warning(caplog):
    """Indirect evidence: far more generated tokens than visible characters."""
    with caplog.at_level(logging.INFO):
        log_timings(
            Timings(
                prep_ms=100,
                total_ms=30000,
                output_chars=800,
                completion_tokens=3600,  # 4.5x the visible length
            ),
            provider="openai_compat",
            mode="detailed",
        )

    assert "远高于可见输出" in caplog.text


def test_normal_run_logs_information_only(caplog):
    """No crying wolf: a healthy ratio must not warn."""
    with caplog.at_level(logging.INFO):
        log_timings(
            Timings(
                prep_ms=100,
                total_ms=9000,
                output_chars=1000,
                completion_tokens=900,  # 0.9x — entirely normal
            ),
            provider="openai_compat",
            mode="detailed",
        )

    assert not any(record.levelno >= logging.WARNING for record in caplog.records)
    assert "识别耗时" in caplog.text


def test_missing_token_counts_do_not_warn(caplog):
    """A vendor that reports no usage must not be reported as suspicious."""
    with caplog.at_level(logging.INFO):
        log_timings(
            Timings(prep_ms=100, total_ms=9000, output_chars=1000),
            provider="openai_compat",
            mode="quick",
        )

    assert not any(record.levelno >= logging.WARNING for record in caplog.records)
