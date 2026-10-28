from tests.test_wallet_flow import (
    test_insufficient_transfer_does_not_debit_sender,
    test_transfer_is_replayed_once_and_credits_both_wallets,
)

__test__ = False
__all__ = ["test_insufficient_transfer_does_not_debit_sender", "test_transfer_is_replayed_once_and_credits_both_wallets"]
