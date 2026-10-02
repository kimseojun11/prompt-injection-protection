"""1단계: 문서 → 청크 목록.

순서: 문서 전체를 정규화 → 정리본(text)을 토큰 기준 384/50 으로 자름 → 각 조각의 원문 구간을 offset_map 으로 역산.
원문을 먼저 자르면 경계에 걸린 Base64·HTML 숨김 태그를 놓치고, 토큰 수도 모델이 보는 정리본과 어긋난다.
"""

from collections import Counter
from typing import Protocol

from common.config import CHUNK_OVERLAP_TOKENS, CHUNK_SIZE_TOKENS
from common.schema import Chunk, Span, TransformLog, raw_end
from preprocess.normalize import NormalizedDoc, normalize_document


class Tokenizer(Protocol):
    def offsets(self, text: str) -> list[tuple[int, int]]:
        """토큰마다 text 기준 [start, end)"""
        ...


class CharTokenizer:
    """임시: 글자 1개 = 토큰 1개. 토크나이저가 확정되면(decisions.md 미결) 기본값을 바꾸고,
    단위 테스트에서는 계속 이걸 쓴다 (CI 에서 모델 파일을 내려받지 않도록)"""

    def offsets(self, text: str) -> list[tuple[int, int]]:
        return [(i, i + 1) for i in range(len(text))]


def token_windows(
    text: str,
    tokenizer: Tokenizer,
    size: int = CHUNK_SIZE_TOKENS,
    overlap: int = CHUNK_OVERLAP_TOKENS,
) -> list[tuple[int, int]]:
    """정리본을 size 토큰씩, overlap 토큰 겹치게 자른 text 기준 구간 목록.
    첫 구간은 0 부터, 마지막 구간은 text 끝까지 (토큰 앞뒤 공백도 빠지지 않게)"""
    if not 0 <= overlap < size:
        raise ValueError(f"overlap({overlap}) 은 0 이상 size({size}) 미만이어야 합니다")
    if not text:
        return []
    tokens = tokenizer.offsets(text)
    if not tokens:  # 공백만 있는 문서 등
        return [(0, len(text))]

    windows = []
    for i in range(0, len(tokens), size - overlap):
        j = min(i + size, len(tokens))
        start = 0 if i == 0 else tokens[i][0]
        end = len(text) if j == len(tokens) else tokens[j - 1][1]
        windows.append((start, end))
        if j == len(tokens):
            break
    return windows


def chunk_document(
    doc: NormalizedDoc,
    doc_id: str,
    tokenizer: Tokenizer | None = None,
    size: int = CHUNK_SIZE_TOKENS,
    overlap: int = CHUNK_OVERLAP_TOKENS,
) -> list[Chunk]:
    windows = token_windows(doc.text, tokenizer or CharTokenizer(), size, overlap)
    if not windows:
        # 정규화하고 나니 빈 문서(전부 보이지 않는 문자 등). 그 자체가 증거라 빈 청크 하나로 내보낸다
        windows = [(0, 0)]
    return [_make_chunk(doc, doc_id, k, s, e) for k, (s, e) in enumerate(windows)]


def split_document(
    doc_id: str, raw: str, fmt: str | None = None, tokenizer: Tokenizer | None = None
) -> list[Chunk]:
    """fmt: "txt" | "md" | "html". 생략 시 내용으로 판별 (파일이면 load.format_of(path) 를 넘긴다)"""
    return chunk_document(normalize_document(raw, fmt), doc_id, tokenizer)


def _make_chunk(doc: NormalizedDoc, doc_id: str, k: int, s: int, e: int) -> Chunk:
    # 첫 청크는 문서 맨 앞부터(앞쪽 제로폭 등 포함), 마지막 청크는 문서 끝까지
    r0 = 0 if k == 0 else doc.offset_map[s]
    r1 = raw_end(doc.offset_map, e, len(doc.raw)) if e > s else len(doc.raw)

    def clip(span: Span) -> Span | None:
        """문서 기준 → 청크 기준. 청크 경계에 걸치면 잘라서 양쪽 청크에 모두 넣는다"""
        start, end = max(span.start, r0), min(span.end, r1)
        if start >= end:
            return None
        return Span(start=start - r0, end=end - r0)

    def inside(items):
        return [
            item.model_copy(update={"span": span})
            for item in items
            if (span := clip(item.span)) is not None
        ]

    counts = Counter(name for name, pos in doc.events if r0 <= pos < r1)
    return Chunk(
        chunk_id=f"{doc_id}-c{k}",
        doc_id=doc_id,
        raw_text=doc.raw[r0:r1],
        text=doc.text[s:e],
        span=Span(start=r0, end=r1),
        offset_map=[m - r0 for m in doc.offset_map[s:e]],
        decoded_segments=inside(doc.decoded_segments),
        hidden_spans=inside(doc.hidden_spans),
        transform_log=TransformLog(**counts),
        meta={"fmt": doc.fmt, "chunk_index": k},
    )
