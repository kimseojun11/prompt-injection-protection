"""파일 → 원문 문자열. 결정 ②(txt/md/html)만 받는다."""

from pathlib import Path

from common.config import SUPPORTED_EXTENSIONS


def load_document(path: Path) -> str:
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"지원하지 않는 형식입니다: {path.suffix} (지원: {', '.join(SUPPORTED_EXTENSIONS)})"
        )
    # 스텁: HTML 도 태그째 그대로 읽는다. 숨김 텍스트 추출은 1단계에서 구현
    return path.read_text(encoding="utf-8")
