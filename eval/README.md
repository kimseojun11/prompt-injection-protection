# eval/ — 6단계: 평가

`inspection_log` 테이블에서 지표(정확도·재현율·에스컬레이션율·지연시간)를 계산하는 스크립트를 둡니다.
모든 스크립트는 맨 위에서 `common.config.set_seed()` 를 호출합니다.
