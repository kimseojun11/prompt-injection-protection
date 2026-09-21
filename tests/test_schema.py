import pytest
from pydantic import ValidationError

from common import examples
from common.config import set_seed
from common.schema import Chunk, Span, StageResult, Verdict


def _stage_result(**overrides):
    fields = {
        "stage": "stage1",
        "label": "benign",
        "risk_score": 0.3,
        "confidence": 0.5,
        "latency_ms": 1.0,
        "model_ver": "test",
    }
    return StageResult(**{**fields, **overrides})


@pytest.mark.parametrize("name", list(examples.ALL))
def test_examples_roundtrip(name):
    obj = examples.ALL[name]
    assert type(obj).model_validate_json(obj.model_dump_json()) == obj


@pytest.mark.parametrize("score", [1.5, -0.1])
def test_risk_score_out_of_range_rejected(score):
    with pytest.raises(ValidationError):
        _stage_result(risk_score=score)


def test_unknown_label_rejected():
    with pytest.raises(ValidationError):
        _stage_result(label="suspicious")


def test_typo_field_rejected():
    with pytest.raises(ValidationError):
        _stage_result(risk_scor=0.3)


def test_span_end_before_start_rejected():
    with pytest.raises(ValidationError):
        Span(start=5, end=3)


def _chunk(**overrides):
    fields = {
        "chunk_id": "c",
        "doc_id": "d",
        "raw_text": "abc",
        "text": "abc",
        "span": Span(start=0, end=3),
        "offset_map": [0, 1, 2],
    }
    return Chunk(**{**fields, **overrides})


def test_offset_map_required_for_text():
    with pytest.raises(ValidationError, match="offset_map"):
        _chunk(offset_map=[])


def test_offset_map_values_must_point_inside_raw_text():
    with pytest.raises(ValidationError, match="offset_map"):
        _chunk(offset_map=[0, 1, 3])


def test_span_length_must_match_raw_text():
    with pytest.raises(ValidationError, match="span"):
        _chunk(span=Span(start=0, end=10))


def test_raw_span_points_at_original_text():
    chunk = examples.CHUNK
    start = chunk.text.index(examples.ATTACK_PHRASE)
    raw = chunk.raw_span(start, start + len(examples.ATTACK_PHRASE))

    # 제로폭 문자 때문에 정리본과 원문 위치가 다르다
    assert raw.start != start
    original = chunk.raw_text[raw.start : raw.end]
    assert original.replace(examples.ZWSP, "") == examples.ATTACK_PHRASE


def test_verdict_stage_must_be_in_path():
    with pytest.raises(ValidationError, match="path"):
        Verdict(
            chunk_id="c",
            final_label="benign",
            final_score=0.3,
            action="allow",
            path=["preprocess"],
            stage_results=[_stage_result()],
            total_latency_ms=1.0,
        )


def test_set_seed_is_reproducible():
    import numpy as np

    set_seed()
    a = np.random.rand(3)
    set_seed()
    assert (np.random.rand(3) == a).all()
