import pytest

from common import examples, logdb
from pipeline.run import main, run
from preprocess.load import load_document


def test_pipeline_end_to_end(tmp_path):
    conn = logdb.connect(tmp_path / "log.db")
    verdicts = run(examples.RAW_DOC, doc_id="example", conn=conn, request_id="r1")

    assert len(verdicts) == 1
    v = verdicts[0]
    # 스텁 stage1 점수(0.3)는 회색지대라 stage2 까지 간다
    assert v.path == ["preprocess", "stage1", "stage2"]
    assert v.action == "block"

    rows = conn.execute("SELECT * FROM inspection_log WHERE request_id = 'r1' ORDER BY id")
    rows = rows.fetchall()
    assert [r["stage"] for r in rows] == ["preprocess", "stage1", "stage2"]
    assert rows[-1]["action"] == "block"
    assert {r["policy"] for r in rows} == {"default-v0"}


def test_defense_off_logs_but_allows(tmp_path):
    conn = logdb.connect(tmp_path / "log.db")
    (v,) = run("hello", conn=conn, request_id="r2", defense_enabled=False)

    assert v.final_label == "injection"
    assert v.action == "allow"
    flags = {r[0] for r in conn.execute("SELECT defense_enabled FROM inspection_log")}
    assert flags == {0}


def test_cli_runs_and_writes_db(tmp_path, capsys):
    db = tmp_path / "log.db"
    main(["--db", str(db)])

    assert "로그 3줄 저장" in capsys.readouterr().out
    assert logdb.connect(db).execute("SELECT COUNT(*) FROM inspection_log").fetchone()[0] == 3


def test_load_document_rejects_pdf(tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    with pytest.raises(ValueError, match="지원하지 않는"):
        load_document(pdf)
