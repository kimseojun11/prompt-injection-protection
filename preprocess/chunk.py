"""1단계: 문서 → 청크 목록. 지금은 스텁 — 문서 전체를 청크 하나로 만든다.

진짜 구현: config.CHUNK_SIZE_TOKENS / CHUNK_OVERLAP_TOKENS 로 자르고
각 조각을 normalize(piece, doc_id, chunk_id, start=문서 안 시작 위치) 한다.
"""

from common.schema import Chunk
from preprocess.normalize import normalize


def split_document(doc_id: str, raw: str) -> list[Chunk]:
    return [normalize(raw, doc_id=doc_id, chunk_id=f"{doc_id}-c0", start=0)]
