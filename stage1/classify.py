"""3단계: 1차 경량 분류기. 지금은 스텁 — 항상 같은 값을 돌려준다."""

from common.schema import Chunk, StageResult


def classify(chunk: Chunk) -> StageResult:
    return StageResult(
        stage="stage1",
        label="benign",
        risk_score=0.3,
        confidence=0.5,
        latency_ms=1.0,
        model_ver="stub-0",
    )
