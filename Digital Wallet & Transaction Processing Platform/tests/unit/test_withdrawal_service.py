from app.models import OperationStatus


def test_withdrawal_terminal_statuses_are_explicit():
    assert {OperationStatus.COMPLETED, OperationStatus.FAILED, OperationStatus.CANCELLED} <= set(OperationStatus)
