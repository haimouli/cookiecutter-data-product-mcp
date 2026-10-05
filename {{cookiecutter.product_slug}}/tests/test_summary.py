import pytest

from src.domain_logic.summary import get_summary
from src.settings import get_settings


def test_get_summary_returns_product_data() -> None:
    summary = get_summary("  abc-1  ")
    assert summary == f"Data for abc-1 from {get_settings().product_name}"


def test_get_summary_requires_id() -> None:
    with pytest.raises(ValueError, match="id is required"):
        get_summary("   ")
