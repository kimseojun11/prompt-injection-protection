import unicodedata

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from common import examples
from common.config import set_seed
from common.schema import Chunk, HiddenSpan, Span, StageResult, Verdict


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


def test_offset_map_must_not_decrease():
    with pytest.raises(ValidationError, match="감소"):
        _chunk(offset_map=[2, 0, 1])


def test_hidden_span_must_be_inside_raw_text():
    with pytest.raises(ValidationError, match="hidden_spans"):
        _chunk(hidden_spans=[HiddenSpan(span=Span(start=1, end=9), reason="display:none")])


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


def _chunk_from(raw, text, offset_map):
    return _chunk(raw_text=raw, text=text, span=Span(start=0, end=len(raw)), offset_map=offset_map)


def test_raw_span_covers_merged_characters():
    # macOS 에서 온 NFD 한글: 자모 6개 → 음절 3개
    raw = unicodedata.normalize("NFD", "무시해")
    chunk = _chunk_from(raw, "무시해", [0, 2, 4])

    whole = chunk.raw_span(0, 3)
    assert (whole.start, whole.end) == (0, 6)
    assert unicodedata.normalize("NFC", raw[whole.start : whole.end]) == "무시해"
    assert chunk.raw_span(0, 2).end == 4  # '무시' 까지만


def test_raw_span_with_expanded_character():
    # ㈜ 1글자 → (주) 3글자
    chunk = _chunk_from("㈜x", "(주)x", [0, 0, 0, 1])
    assert chunk.raw_span(0, 3) == Span(start=0, end=1)
    assert chunk.raw_span(1, 2) == Span(start=0, end=1)
    assert chunk.raw_span(3, 4) == Span(start=1, end=2)


def test_raw_span_includes_removed_characters_right_after():
    zw = examples.ZWSP
    chunk = _chunk_from(f"a{zw}b", "ab", [0, 2])
    assert chunk.raw_span(0, 1) == Span(start=0, end=2)  # 'a' + 뒤의 제로폭


# 정규화를 '원문 글자 묶음 → 정리본 글자 묶음' 의 나열로 흉내 낸다.
# (원문 몇 글자, 정리본 몇 글자): 유지 (1,1) · 삭제 (1,0) · 늘어남 (1,2~3) · 합쳐짐 (2~3,1)
# 묶음 번호를 글자 자체에 새겨 두면 어느 글자가 어디서 왔는지 바로 알 수 있다
_GROUPS = st.lists(
    st.sampled_from([(1, 1), (1, 1), (1, 0), (1, 2), (1, 3), (2, 1), (3, 1)]),
    min_size=1,
    max_size=40,
).filter(lambda gs: any(t for _, t in gs))


def _build(groups):
    raw, text, offset_map = [], [], []
    for g, (n_raw, n_text) in enumerate(groups):
        offset_map += [len(raw)] * n_text
        raw += [chr(0xAC00 + g)] * n_raw
        text += [chr(0x4E00 + g)] * n_text
    return "".join(raw), "".join(text), offset_map


@given(groups=_GROUPS, data=st.data())
def test_raw_span_property(groups, data):
    raw, text, offset_map = _build(groups)
    chunk = _chunk_from(raw, text, offset_map)
    start = data.draw(st.integers(0, len(text) - 1))
    end = data.draw(st.integers(start + 1, len(text)))
    span = chunk.raw_span(start, end)

    def raw_positions(g):
        return [i for i, ch in enumerate(raw) if ord(ch) - 0xAC00 == g]

    first, last = ord(text[start]) - 0x4E00, ord(text[end - 1]) - 0x4E00
    # 시작은 첫 글자의 원문 시작, 끝은 마지막 글자의 원문을 끝까지 덮는다
    assert span.start == raw_positions(first)[0]
    assert span.end >= raw_positions(last)[-1] + 1
    # 구간 뒤의 글자를 만든 원문은 포함하지 않는다
    for g in range(last + 1, len(groups)):
        if groups[g][1]:
            assert raw_positions(g)[0] >= span.end


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
