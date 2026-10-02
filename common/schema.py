"""5명이 공유하는 데이터 양식. 이 파일을 고치는 PR 은 전원 리뷰 필수.

좌표 규칙 (전원 동일하게 이해해야 함)
- Span 은 [start, end) 반열린 구간, 글자(파이썬 str 인덱스) 단위.
- Chunk.span                     : 원본 '문서' 안에서 이 청크의 위치
- Chunk.offset_map[i]            : text[i] 가 chunk.raw_text 의 몇 번째 글자였나
  (전처리는 글자 순서를 바꾸지 않으므로 감소하지 않는다)
- DecodedSegment.span,
  HiddenSpan.span,
  StageResult.evidence_span      : chunk.raw_text 기준
  → 문서 기준 위치가 필요하면 chunk.span.start 를 더한다.
- 정리본(text) 에서 찾은 위치는 반드시 Chunk.raw_span() 으로 원문 위치로 바꿔서 내보낸다.
  끝 위치는 여러 글자가 합쳐진 경우(NFD 한글 등)도 끝까지, 그리고 바로 뒤에서 지워진
  글자(제로폭 등)까지 포함한다.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.2.0"

Label = Literal["benign", "injection"]
Stage = Literal["preprocess", "rule", "stage1", "stage2"]
Action = Literal["allow", "mask", "warn", "block"]
DecodeMethod = Literal[
    "base64", "hex", "url", "rot13",
    "tag_char",  # 태그 문자 U+E0000~E007F → ASCII (ASCII 스머글링)
    "html_entity",  # &#105; &lt;
    "unicode_escape",  # \u0069 \x69
]


class _Model(BaseModel):
    # 오타 난 필드(risk_scor=...)가 조용히 무시되지 않도록 모르는 필드는 에러
    model_config = ConfigDict(extra="forbid")


class Span(_Model):
    """원문(raw_text) 기준 글자 위치 [start, end)"""

    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def _check_order(self):
        if self.end < self.start:
            raise ValueError(f"end({self.end}) 가 start({self.start}) 보다 작습니다")
        return self


class DecodedSegment(_Model):
    """Base64 등을 복원한 결과. 본문에 섞지 않고 여기 따로 담는다"""

    method: DecodeMethod
    span: Span  # 원문에서 인코딩된 문자열이 있던 위치
    decoded: str  # 복원된 내용
    depth: int = Field(default=1, ge=1)  # 몇 겹으로 감싸져 있었나


class HiddenSpan(_Model):
    """화면에는 안 보이지만 AI 는 읽는 구간. 지우지 않고 text 에 남긴 채 위치만 표시한다"""

    span: Span  # raw_text 기준
    reason: str  # 예: "display:none", "font-size:0", "same_color", "html_comment", "md_comment", "alt"


class TransformLog(_Model):
    """정규화 과정에서 무엇을 몇 개 처리했나.
    이 숫자 자체가 1차 분류기의 추가 단서가 된다"""

    zero_width_removed: int = Field(default=0, ge=0)  # 제로폭 문자 (이모지 안 ZWJ 는 제외)
    emoji_zwj_removed: int = Field(default=0, ge=0)  # 가족 이모지처럼 여러 이모지를 잇는 ZWJ (정상 문서에도 흔함)
    bidi_removed: int = Field(default=0, ge=0)  # 방향 제어문자
    hangul_filler_removed: int = Field(default=0, ge=0)  # 한글 채움 문자 U+3164 등 (Cf 가 아님)
    variation_selector_removed: int = Field(default=0, ge=0)  # 변형 선택자
    tag_char_decoded: int = Field(default=0, ge=0)  # 태그 문자. 해독 결과는 decoded_segments
    homoglyph_replaced: int = Field(default=0, ge=0)  # 닮은꼴 글자
    nfkc_changed: int = Field(default=0, ge=0)  # NFKC 로 바뀐 글자 수
    hidden_text_marked: int = Field(default=0, ge=0)  # 숨김 구간 수 (HTML 숨김·주석, MD 주석 등)
    decoded_count: int = Field(default=0, ge=0)


class Chunk(_Model):
    chunk_id: str
    doc_id: str
    raw_text: str  # 손대지 않은 원문
    text: str  # 정규화 후
    span: Span  # 원본 문서에서 이 청크의 위치
    offset_map: list[int] = Field(default_factory=list)  # ★ text 의 i번째 글자 → raw_text 몇 번째 글자
    decoded_segments: list[DecodedSegment] = Field(default_factory=list)
    hidden_spans: list[HiddenSpan] = Field(default_factory=list)
    transform_log: TransformLog = Field(default_factory=TransformLog)
    meta: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_offsets(self):
        n_raw = len(self.raw_text)
        if self.span.end - self.span.start != n_raw:
            raise ValueError(
                f"span 길이({self.span.end - self.span.start})와 raw_text 길이({n_raw})가 다릅니다"
            )
        # offset_map 은 '나중에' 채울 수 없다. text 글자 수만큼 반드시 있어야 한다
        if len(self.offset_map) != len(self.text):
            raise ValueError(
                f"offset_map 길이({len(self.offset_map)})가 text 길이({len(self.text)})와 다릅니다"
            )
        if self.offset_map and (min(self.offset_map) < 0 or max(self.offset_map) >= n_raw):
            raise ValueError(f"offset_map 값은 0 이상 {n_raw} 미만이어야 합니다")
        if any(b < a for a, b in zip(self.offset_map, self.offset_map[1:])):
            raise ValueError("offset_map 은 감소하면 안 됩니다 (전처리는 글자 순서를 바꾸지 않음)")
        for name in ("decoded_segments", "hidden_spans"):
            for item in getattr(self, name):
                if item.span.end > n_raw:
                    raise ValueError(f"{name}.span({item.span.end})이 raw_text 밖입니다")
        return self

    def raw_span(self, start: int, end: int) -> Span:
        """text 기준 [start, end) → raw_text 기준 Span.
        판정 근거를 원문에 표시할 때 반드시 이걸 거친다."""
        if not 0 <= start < end <= len(self.text):
            raise ValueError(f"text 범위를 벗어난 구간입니다: [{start}, {end})")
        return Span(
            start=self.offset_map[start],
            end=raw_end(self.offset_map, end, len(self.raw_text)),
        )


def raw_end(offset_map: list[int], end: int, raw_len: int) -> int:
    """정리본 text[:end] 가 원문에서 끝나는 위치 (end >= 1).
    offset_map[end-1]+1 만 쓰면 여러 글자가 한 글자로 합쳐진 경우 끝이 잘리므로,
    다음 글자의 시작 위치(없으면 원문 끝)까지 늘린다. 청크를 자를 때도 같은 계산을 쓴다."""
    nxt = offset_map[end] if end < len(offset_map) else raw_len
    return max(offset_map[end - 1] + 1, nxt)


class StageResult(_Model):
    stage: Stage
    label: Label
    risk_score: float = Field(ge=0.0, le=1.0)  # 높을수록 위험
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""
    attack_type: str | None = None
    evidence_span: Span | None = None  # raw_text 기준
    latency_ms: float = Field(ge=0.0)
    model_ver: str


class Verdict(_Model):
    chunk_id: str
    final_label: Label
    final_score: float = Field(ge=0.0, le=1.0)
    action: Action
    path: list[Stage]  # 예: ["preprocess","stage1"] ← 2차 안 감
    stage_results: list[StageResult]
    total_latency_ms: float = Field(ge=0.0)

    @model_validator(mode="after")
    def _check_path(self):
        missing = [r.stage for r in self.stage_results if r.stage not in self.path]
        if missing:
            raise ValueError(f"stage_results 의 단계 {missing} 가 path 에 없습니다")
        return self
