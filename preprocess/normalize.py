"""1단계: 정규화. 지금은 스텁 — 아무것도 바꾸지 않고 그대로 돌려준다.

정규화는 반드시 '문서 전체'에 한 번 돌리고, 그 결과를 preprocess/chunk.py 가 자른다.
원문을 먼저 자르고 조각마다 정규화하면 경계에 걸린 Base64·HTML 숨김 태그를 놓친다.

진짜 구현에서 글자를 지우거나 바꿀 때는 offset_map 을 같이 갱신해야 한다.
(완성된 코드에 나중에 덧붙일 수 없음. common/examples.py 의 CHUNK 참고)
"""

from dataclasses import dataclass, field

from common.schema import DecodedSegment, HiddenSpan
from preprocess.load import guess_format

VERSION = "stub-1"


@dataclass
class NormalizedDoc:
    """문서 하나를 정규화한 결과. 위치는 전부 문서 원문(raw) 기준"""

    raw: str
    text: str
    offset_map: list[int]  # text[i] → raw 의 몇 번째 글자였나 (감소하지 않음)
    fmt: str  # "txt" | "md" | "html"
    # (TransformLog 칸 이름, 원문 위치). 청크별 변환 기록은 이걸 청크 구간으로 걸러서 센다
    events: list[tuple[str, int]] = field(default_factory=list)
    decoded_segments: list[DecodedSegment] = field(default_factory=list)
    hidden_spans: list[HiddenSpan] = field(default_factory=list)


def normalize_document(raw: str, fmt: str | None = None) -> NormalizedDoc:
    """fmt 생략 시 내용으로 판별한다"""
    return NormalizedDoc(
        raw=raw,
        text=raw,
        offset_map=list(range(len(raw))),
        fmt=fmt or guess_format(raw),
    )
