"""1단계: 정규화. 지금은 스텁 — 아무것도 바꾸지 않고 그대로 돌려준다.

진짜 구현에서 글자를 지우거나 바꿀 때는 offset_map 을 같이 갱신해야 한다.
(완성된 코드에 나중에 덧붙일 수 없음. common/examples.py 의 CHUNK 참고)
"""

from common.schema import Chunk, Span

VERSION = "stub-0"


def normalize(raw: str, doc_id: str = "d1", chunk_id: str = "c1", start: int = 0) -> Chunk:
    """raw: 청크 원문, start: 문서 안에서 이 청크가 시작하는 위치"""
    return Chunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        raw_text=raw,
        text=raw,
        span=Span(start=start, end=start + len(raw)),
        offset_map=list(range(len(raw))),
    )
