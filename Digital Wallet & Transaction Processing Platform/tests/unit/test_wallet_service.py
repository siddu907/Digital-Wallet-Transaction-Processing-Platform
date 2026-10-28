from app.models import WalletStatus


def test_closed_wallet_has_no_valid_outgoing_state():
    transitions = {
        WalletStatus.ACTIVE: {WalletStatus.FROZEN, WalletStatus.CLOSED, WalletStatus.SUSPENDED},
        WalletStatus.FROZEN: {WalletStatus.ACTIVE, WalletStatus.SUSPENDED},
        WalletStatus.SUSPENDED: {WalletStatus.ACTIVE, WalletStatus.CLOSED},
        WalletStatus.CLOSED: set(),
    }
    assert not transitions[WalletStatus.CLOSED]
