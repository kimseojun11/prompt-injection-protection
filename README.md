# rag-guard — RAG 프롬프트 인젝션 방어

RAG 로 들어오는 문서 청크에 숨은 프롬프트 인젝션을 탐지하는 다단계 파이프라인입니다.

```
문서 → 전처리(정규화·청크) → 1차 경량 분류기 → (애매하면) 2차 소형 LLM → 최종 판정 → 로그(SQLite)
```

현재는 **0단계**: 각 단계가 정해진 값만 돌려주는 스텁이지만, 처음부터 끝까지 연결돼 있고 DB 에 로그가 쌓입니다.
각자 자기 폴더의 스텁을 진짜 구현으로 갈아끼우면 됩니다.

## 빠른 시작

[uv](https://docs.astral.sh/uv/) 가 필요합니다. Python 3.11 은 uv 가 알아서 받아옵니다.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```bash
uv sync
```

```bash
uv run python -m pipeline.run
```

```bash
uv run pytest
```

출력 예시:

```
[example-c0] injection score=0.90 action=block path=preprocess → stage1 → stage2 (101.0ms)

로그 3줄 저장 → .../data/inspection_log.db (request_id=...)
  preprocess label=-         score=-     action=-      model_ver=stub-0
  stage1     label=benign    score=0.30  action=-      model_ver=stub-0
  stage2     label=injection score=0.90  action=block  model_ver=stub-0
```

그 밖의 실행 방법:

| 명령 | 설명 |
|---|---|
| `uv run python -m pipeline.run "검사할 텍스트"` | 직접 입력한 텍스트 검사 |
| `uv run python -m pipeline.run --file doc.md` | 파일 검사 (txt/md/html) |
| `uv run python -m pipeline.run --no-defense` | 방어 OFF: 판정·기록만 하고 조치는 `allow` |
| `uv run python -m common.examples` | 모든 데이터 양식의 채워진 예시 출력 |
| `uv sync --group tracking` | W&B 까지 설치 (학습·평가 담당) |

## 폴더 구조

```
common/        ← 5명이 공유. 여기를 고치는 PR 은 전원 리뷰
  schema.py      데이터 양식 (Chunk, StageResult, Verdict …)
  examples.py    양식별 채워진 샘플 — 코드보다 이걸 먼저 보세요
  logdb.py       로그 테이블 정의 + 저장 함수
  config.py      시드, 경로, 청크 크기 등 공통 상수
preprocess/    ← 1단계: load.py(파일 읽기) · chunk.py(청크 분할) · normalize.py(정규화)
stage1/        ← 3단계: classify.py (경량 분류기)
stage2/        ← 4단계: judge.py (소형 LLM)
pipeline/      ← 5단계(팀장): run.py(연결) · policy.py(라우팅·조치 정책)
eval/          ← 6단계
web/           ← 7단계
data/          ← 데이터셋·로그 DB (Git 제외)
tests/
docs/decisions.md  ← 0단계 결정 사항
```

## 규칙

1. **브랜치** — `main` 은 항상 돌아가는 상태만. 작업은 `feat/<영역>-<내용>` 브랜치(예: `feat/preprocess-normalize`)에서 하고 PR 로 합칩니다.
2. **`common/` 을 수정하는 PR 은 반드시 전원 리뷰.** 유일한 강제 규칙입니다. 양식을 바꾸면 `docs/decisions.md` 도 같이 고칩니다.
3. **시드** — 모든 학습·평가 스크립트 맨 위에서 `from common.config import set_seed; set_seed()`.
4. **데이터·모델 파일은 Git 에 올리지 않습니다** (`data/`, `*.ckpt`, `*.onnx`, `*.db`, `wandb/`). 공유는 Google Drive / Hugging Face 비공개 저장소로.
5. **비밀값** — `.env.example` 을 `.env` 로 복사해서 씁니다. `.env` 는 커밋 금지.
6. **위치 표시** — 판정 근거 위치(`evidence_span`)는 원문 기준입니다. 정리본에서 찾은 위치는 `chunk.raw_span(start, end)` 로 변환하세요.

PR 마다 GitHub Actions 가 lint · 테스트 · 파이프라인 실행을 확인합니다.

## 0단계 완료 체크리스트

- [ ] 팀원 전원이 clone → `uv sync` → `uv run python -m pipeline.run` 성공
- [ ] 실행 후 DB 에 단계별 줄이 쌓였는지 확인: `sqlite3 data/inspection_log.db "SELECT stage, label, score, action FROM inspection_log"`
- [ ] 잘못된 값이 에러 나는지 확인: `uv run python -c "from common.examples import STAGE1_RESULT as r; r.model_validate({**r.model_dump(), 'risk_score': 1.5})"`
- [ ] `docs/decisions.md` 의 📝 항목(W&B 계정, 역할, 회의 시간) 기입
