from common import examples, logdb


def test_connect_creates_table_and_indexes(tmp_path):
    conn = logdb.connect(tmp_path / "sub" / "log.db")
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert {"inspection_log", "idx_req", "idx_chunk"} <= names


def test_log_verdict_writes_one_row_per_stage(tmp_path):
    conn = logdb.connect(tmp_path / "log.db")
    n = logdb.log_verdict(
        conn,
        examples.VERDICT,
        request_id="r1",
        doc_id="example",
        policy="test",
        preprocess_latency_ms=0.5,
    )
    rows = conn.execute("SELECT * FROM inspection_log ORDER BY id").fetchall()

    assert n == len(rows) == 3
    assert [r["stage"] for r in rows] == ["preprocess", "stage1", "stage2"]
    # action 은 최종 판정을 낸 마지막 줄에만
    assert [r["action"] for r in rows] == [None, None, "block"]
    assert rows[2]["evidence_start"] == examples.EVIDENCE_SPAN.start
    assert rows[2]["model_ver"] == "stage2-example"
    assert all(r["defense_enabled"] == 1 for r in rows)


def test_escalation_rate(tmp_path):
    conn = logdb.connect(tmp_path / "log.db")
    assert logdb.escalation_rate(conn) is None

    escalated = examples.VERDICT
    stopped = escalated.model_copy(
        update={
            "chunk_id": "other",
            "path": ["preprocess", "stage1"],
            "stage_results": [examples.STAGE1_RESULT],
        }
    )
    for v in (escalated, stopped):
        logdb.log_verdict(conn, v, request_id="r1", doc_id="d", policy="test")

    assert logdb.escalation_rate(conn) == 0.5
