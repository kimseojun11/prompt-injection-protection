"""검사 로그 저장소 (SQLite, 파일 하나).

한 줄 = 한 단계. 청크 하나가 stage1 에서 끝나면 preprocess·stage1 두 줄,
stage2 까지 가면 세 줄이 쌓인다. action 은 최종 판정을 낸 마지막 줄에만 적는다.
칸 구성을 바꾸면 그동안 쌓인 기록과 호환이 깨지므로 이 파일 수정은 전원 리뷰.

자주 쓰는 쿼리
  에스컬레이션율 : escalation_rate(conn)
  조치 분포      : SELECT action, COUNT(*) FROM inspection_log
                   WHERE action IS NOT NULL GROUP BY action;
  요청 1건 전체  : SELECT * FROM inspection_log WHERE request_id = ? ORDER BY id;
"""

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from common.config import DB_PATH
from common.schema import Action, Label, Stage, Verdict

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS inspection_log (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id      TEXT NOT NULL,     -- 요청 1건
  doc_id          TEXT NOT NULL,
  chunk_id        TEXT NOT NULL,
  stage           TEXT NOT NULL,     -- preprocess/rule/stage1/stage2
  label           TEXT,
  score           REAL,
  attack_type     TEXT,
  reason          TEXT,
  evidence_start  INTEGER,
  evidence_end    INTEGER,
  latency_ms      REAL,
  action          TEXT,              -- allow/mask/warn/block
  model_ver       TEXT,
  policy          TEXT,              -- 어떤 정책으로 돌렸나
  defense_enabled INTEGER DEFAULT 1, -- RAG 데모 ON/OFF 비교용
  created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_req   ON inspection_log(request_id);
CREATE INDEX IF NOT EXISTS idx_chunk ON inspection_log(chunk_id);
"""


class LogRow(BaseModel):
    """inspection_log 한 줄. id·created_at 은 DB 가 채운다"""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    doc_id: str
    chunk_id: str
    stage: Stage
    label: Label | None = None
    score: float | None = None
    attack_type: str | None = None
    reason: str | None = None
    evidence_start: int | None = None
    evidence_end: int | None = None
    latency_ms: float | None = None
    action: Action | None = None
    model_ver: str | None = None
    policy: str | None = None
    defense_enabled: bool = True


_COLUMNS = list(LogRow.model_fields)
_INSERT_SQL = (
    f"INSERT INTO inspection_log ({', '.join(_COLUMNS)}) "
    f"VALUES ({', '.join('?' for _ in _COLUMNS)})"
)


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """DB 를 열고, 테이블이 없으면 만든다. db_path 생략 시 config.DB_PATH"""
    path = str(db_path or DB_PATH)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


def insert_rows(conn: sqlite3.Connection, rows: Iterable[LogRow]) -> int:
    values = [tuple(row.model_dump().values()) for row in rows]
    with conn:
        conn.executemany(_INSERT_SQL, values)
    return len(values)


def log_verdict(
    conn: sqlite3.Connection,
    verdict: Verdict,
    *,
    request_id: str,
    doc_id: str,
    policy: str,
    defense_enabled: bool = True,
    preprocess_latency_ms: float | None = None,
    preprocess_ver: str | None = None,
    preprocess_note: str = "",
) -> int:
    """판정 1건을 단계별 줄로 풀어서 저장한다. 저장한 줄 수를 돌려준다"""
    shared = {
        "request_id": request_id,
        "doc_id": doc_id,
        "chunk_id": verdict.chunk_id,
        "policy": policy,
        "defense_enabled": defense_enabled,
    }
    rows = []
    if "preprocess" in verdict.path:
        rows.append(
            LogRow(
                **shared,
                stage="preprocess",
                reason=preprocess_note,
                latency_ms=preprocess_latency_ms,
                model_ver=preprocess_ver,
            )
        )
    for r in verdict.stage_results:
        rows.append(
            LogRow(
                **shared,
                stage=r.stage,
                label=r.label,
                score=r.risk_score,
                attack_type=r.attack_type,
                reason=r.reason,
                evidence_start=r.evidence_span.start if r.evidence_span else None,
                evidence_end=r.evidence_span.end if r.evidence_span else None,
                latency_ms=r.latency_ms,
                model_ver=r.model_ver,
            )
        )
    if rows:
        rows[-1] = rows[-1].model_copy(update={"action": verdict.action})
    return insert_rows(conn, rows)


def escalation_rate(conn: sqlite3.Connection) -> float | None:
    """stage1 을 거친 청크 중 stage2 까지 간 비율. stage1 기록이 없으면 None"""
    stage1, stage2 = conn.execute(
        """
        SELECT
          COUNT(DISTINCT CASE WHEN stage = 'stage1' THEN request_id || '/' || chunk_id END),
          COUNT(DISTINCT CASE WHEN stage = 'stage2' THEN request_id || '/' || chunk_id END)
        FROM inspection_log
        """
    ).fetchone()
    return stage2 / stage1 if stage1 else None
