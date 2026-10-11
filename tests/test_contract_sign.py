import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.contract_sign import payment_action


def test_high_value_payment_requires_manual_review():
    assert payment_action(100_000) == "manual_review"
    assert payment_action(99_999) == "auto_approve"
