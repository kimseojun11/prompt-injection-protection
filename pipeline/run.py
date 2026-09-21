"""전처리 → 1차 → (조건부) 2차 → 최종 판정 → 로그 저장.

  uv run python -m pipeline.run                        # common/examples.py 의 예제 문서
  uv run python -m pipeline.run "검사할 텍스트"
  uv run python -m pipeline.run --file doc.md --no-defense

각 단계 파일(preprocess/, stage1/, stage2/)의 스텁을 진짜 구현으로 갈아끼우면
이 파일은 그대로 두고도 전체가 돌아가야 한다.
"""

import argparse
import json
import sqlite3
import time
import uuid
from pathlib import Path

from common import examples, logdb
from common.config import DB_PATH, set_seed
from common.schema import Chunk, Verdict
from pipeline.policy import POLICY_NAME, decide_action, should_escalate
from preprocess import normalize as preprocess_module
from preprocess.chunk import split_document
from preprocess.load import load_document
from stage1.classify import classify
from stage2.judge import judge


def inspect_chunk(
    chunk: Chunk, *, preprocess_latency_ms: float = 0.0, defense_enabled: bool = True
) -> Verdict:
    results = [classify(chunk)]
    if should_escalate(results[-1]):
        results.append(judge(chunk))

    final = results[-1]
    # 방어 OFF: 판정은 그대로 하되 조치는 하지 않는다 (RAG 데모 비교용)
    action = decide_action(final.risk_score) if defense_enabled else "allow"
    return Verdict(
        chunk_id=chunk.chunk_id,
        final_label=final.label,
        final_score=final.risk_score,
        action=action,
        path=["preprocess", *(r.stage for r in results)],
        stage_results=results,
        total_latency_ms=preprocess_latency_ms + sum(r.latency_ms for r in results),
    )


def run(
    raw: str,
    *,
    doc_id: str = "d1",
    conn: sqlite3.Connection | None = None,
    request_id: str | None = None,
    defense_enabled: bool = True,
) -> list[Verdict]:
    request_id = request_id or uuid.uuid4().hex
    own_conn = conn is None
    conn = conn or logdb.connect()

    t0 = time.perf_counter()
    chunks = split_document(doc_id, raw)
    # 전처리는 문서 단위로 돌기 때문에 청크별 소요시간은 균등 분배한 근사값
    pre_ms = (time.perf_counter() - t0) * 1000 / max(len(chunks), 1)

    verdicts = []
    try:
        for chunk in chunks:
            verdict = inspect_chunk(
                chunk, preprocess_latency_ms=pre_ms, defense_enabled=defense_enabled
            )
            logdb.log_verdict(
                conn,
                verdict,
                request_id=request_id,
                doc_id=doc_id,
                policy=POLICY_NAME,
                defense_enabled=defense_enabled,
                preprocess_latency_ms=pre_ms,
                preprocess_ver=preprocess_module.VERSION,
                preprocess_note=json.dumps(
                    chunk.transform_log.model_dump(exclude_defaults=True), ensure_ascii=False
                ),
            )
            verdicts.append(verdict)
    finally:
        if own_conn:
            conn.close()
    return verdicts


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="프롬프트 인젝션 검사 파이프라인")
    parser.add_argument("text", nargs="?", help="검사할 텍스트 (생략 시 예제 문서)")
    parser.add_argument("--file", type=Path, help="검사할 파일 (.txt/.md/.html)")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=f"로그 DB 경로 (기본: {DB_PATH})")
    parser.add_argument("--no-defense", action="store_true", help="방어 OFF (판정만, 조치 안 함)")
    args = parser.parse_args(argv)

    set_seed()
    if args.file:
        raw, doc_id = load_document(args.file), args.file.stem
    elif args.text:
        raw, doc_id = args.text, "cli"
    else:
        raw, doc_id = examples.RAW_DOC, "example"

    request_id = uuid.uuid4().hex
    conn = logdb.connect(args.db)
    try:
        verdicts = run(
            raw,
            doc_id=doc_id,
            conn=conn,
            request_id=request_id,
            defense_enabled=not args.no_defense,
        )
        for v in verdicts:
            print(
                f"[{v.chunk_id}] {v.final_label} score={v.final_score:.2f} action={v.action} "
                f"path={' → '.join(v.path)} ({v.total_latency_ms:.1f}ms)"
            )

        rows = conn.execute(
            "SELECT stage, label, score, action, model_ver FROM inspection_log "
            "WHERE request_id = ? ORDER BY id",
            (request_id,),
        ).fetchall()
        print(f"\n로그 {len(rows)}줄 저장 → {args.db} (request_id={request_id})")
        for r in rows:
            score = "-" if r["score"] is None else f"{r['score']:.2f}"
            print(
                f"  {r['stage']:<10} label={r['label'] or '-':<9} score={score:<5} "
                f"action={r['action'] or '-':<6} model_ver={r['model_ver']}"
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
