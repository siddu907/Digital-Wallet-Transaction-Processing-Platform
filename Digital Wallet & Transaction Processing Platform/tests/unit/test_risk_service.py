from app.models import RiskStatus


def test_risk_review_states_are_represented():
    assert {RiskStatus.NORMAL, RiskStatus.REVIEW_REQUIRED, RiskStatus.BLOCKED} == set(RiskStatus)
