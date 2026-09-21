"""5명이 공유하는 데이터 양식. 이 파일을 고치는 PR 은 전원 리뷰 필수.

좌표 규칙 (전원 동일하게 이해해야 함)
- Span 은 [start, end) 반열린 구간, 글자(파이썬 str 인덱스) 단위.
- Chunk.span                     : 원본 '문서' 안에서 이 청크의 위치
- Chunk.offset_map[i]            : text[i] 가 chunk.raw_text 의 몇 번째 글자였나
- DecodedSegment.span,
  StageResult.evidence_span      : chunk.raw_text 기준
  → 문서 기준 위치가 필요하면 chunk.span.start 를 더한다.
- 정리본(text) 에서 찾은 위치는 반드시 Chunk.raw_span() 으로 원문 위치로 바꿔서 내보낸다.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.1.0"

Label = Literal["benign", "injection"]
Stage = Literal["preprocess", "rule", "stage1", "stage2"]
Action = Literal["allow", "mask", "warn", "block"]


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

    method: Literal["base64", "hex", "url", "rot13"]
    span: Span  # 원문에서 인코딩된 문자열이 있던 위치
    decoded: str  # 복원된 내용
    depth: int = Field(default=1, ge=1)  # 몇 겹으로 감싸져 있었나


class TransformLog(_Model):
    """정규화 과정에서 무엇을 몇 개 처리했나.
    이 숫자 자체가 1차 분류기의 추가 단서가 된다"""

    zero_width_removed: int = Field(default=0, ge=0)  # 제로폭 문자
    bidi_removed: int = Field(default=0, ge=0)  # 방향 제어문자
    homoglyph_replaced: int = Field(default=0, ge=0)  # 닮은꼴 글자
    hidden_html_extracted: int = Field(default=0, ge=0)  # 흰 글씨·0px·주석
    decoded_count: int = Field(default=0, ge=0)
    nfkc_changed: bool = False


class Chunk(_Model):
    chunk_id: str
    doc_id: str
    raw_text: str  # 손대지 않은 원문
    text: str  # 정규화 후
    span: Span  # 원본 문서에서 이 청크의 위치
    offset_map: list[int] = Field(default_factory=list)  # ★ text 의 i번째 글자 → raw_text 몇 번째 글자
    decoded_segments: list[DecodedSegment] = Field(default_factory=list)
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
        for seg in self.decoded_segments:
            if seg.span.end > n_raw:
                raise ValueError(f"decoded_segments.span({seg.span.end})이 raw_text 밖입니다")
        return self

    def raw_span(self, start: int, end: int) -> Span:
        """text 기준 [start, end) → raw_text 기준 Span.
        판정 근거를 원문에 표시할 때 반드시 이걸 거친다."""
        if not 0 <= start < end <= len(self.text):
            raise ValueError(f"text 범위를 벗어난 구간입니다: [{start}, {end})")
        return Span(start=self.offset_map[start], end=self.offset_map[end - 1] + 1)


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
