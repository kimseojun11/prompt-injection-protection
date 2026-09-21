"""4단계: 2차 소형 LLM 판정. 지금은 스텁 — 항상 같은 값을 돌려준다.

evidence_span 을 채울 때는 chunk.raw_span() 으로 원문 기준 위치로 바꿔서 넣는다.
"""

from common.schema import Chunk, StageResult


def judge(chunk: Chunk) -> StageResult:
    return StageResult(
        stage="stage2",
        label="injection",
        risk_score=0.9,
        confidence=0.8,
        reason="스텁",
        latency_ms=100.0,
        model_ver="stub-0",
    )
