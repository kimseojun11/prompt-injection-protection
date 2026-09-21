"""라우팅·조치 정책. 0단계 임시값이며 5단계에서 평가 결과를 보고 조정한다.

정책을 바꾸면 POLICY_NAME 도 올린다. 로그의 policy 칸으로 어떤 정책의 결과인지 구분한다.
"""

from common.schema import Action, StageResult

POLICY_NAME = "default-v0"

# stage1 risk_score 가 이 구간(회색지대)이면 stage2 로 보낸다
ESCALATE_LOW = 0.2
ESCALATE_HIGH = 0.8

# final_score 가 임계값 이상이면 해당 조치. 위에서부터 검사, 모두 미만이면 allow
ACTION_THRESHOLDS: list[tuple[float, Action]] = [
    (0.9, "block"),
    (0.7, "mask"),
    (0.5, "warn"),
]


def should_escalate(result: StageResult) -> bool:
    return ESCALATE_LOW <= result.risk_score <= ESCALATE_HIGH


def decide_action(score: float) -> Action:
    for threshold, action in ACTION_THRESHOLDS:
        if score >= threshold:
            return action
    return "allow"
