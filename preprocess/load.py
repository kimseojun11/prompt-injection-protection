"""파일 → 원문 문자열. 결정 ②(txt/md/html)만 받는다.

원문 좌표의 기준은 '디코딩한 문자열'이다. 여기서는 문자셋 해석과 맨 앞 BOM 제거만 하고,
줄바꿈(\\r\\n) 통일 같은 나머지 변환은 위치를 추적하는 정규화 단계에서 한다.
"""

import codecs
import re
from pathlib import Path

from common.config import SUPPORTED_EXTENSIONS

_EXT_FORMAT = {".txt": "txt", ".md": "md", ".html": "html", ".htm": "html"}

_BOMS = (
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)
# BOM 이 없을 때 차례로 시도. 한국어 문서는 CP949(EUC-KR 포함)가 흔하다
_FALLBACK_ENCODINGS = ("utf-8", "cp949")

_HTML_HINT = re.compile(r"<(?:!doctype|html|head|body|div|span|p|br|img|a)\b|<!--", re.IGNORECASE)
_MD_HINT = re.compile(r"^(?:#{1,6} |[-*+] |\d+\. |```|>)|!?\[[^\]\n]*\]\([^)\n]*\)", re.MULTILINE)


def format_of(path: Path) -> str:
    """확장자 → "txt" | "md" | "html". 지원하지 않는 확장자면 에러"""
    suffix = Path(path).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"지원하지 않는 형식입니다: {suffix} (지원: {', '.join(SUPPORTED_EXTENSIONS)})"
        )
    return _EXT_FORMAT[suffix]


def guess_format(text: str) -> str:
    """확장자를 모를 때 내용으로 판별"""
    if _HTML_HINT.search(text):
        return "html"
    if _MD_HINT.search(text):
        return "md"
    return "txt"


def decode_bytes(data: bytes) -> str:
    for bom, encoding in _BOMS:
        if data.startswith(bom):
            return data[len(bom) :].decode(encoding)
    for encoding in _FALLBACK_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("문자셋을 알 수 없습니다 (지원: UTF-8, UTF-16(BOM), CP949)")


def load_document(path: Path) -> str:
    path = Path(path)
    format_of(path)  # 지원 형식 검사
    # read_text() 는 \r\n 을 몰래 \n 으로 바꾸므로 바이트로 읽어 직접 디코딩한다
    return decode_bytes(path.read_bytes())
