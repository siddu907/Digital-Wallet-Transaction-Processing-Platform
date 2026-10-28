from app.models import RefundStatus


def test_refund_has_distinct_review_and_completion_states():
    assert RefundStatus.REQUESTED != RefundStatus.APPROVED
    assert RefundStatus.APPROVED != RefundStatus.COMPLETED
