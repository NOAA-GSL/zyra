from datetime import datetime

import pytest
from datavizhub.utils.date_manager import DateManager
from dateutil.relativedelta import relativedelta


@pytest.fixture()
def date_manager():
    """Fixture to create a DateManager instance."""
    return DateManager(["%Y%m%d"])


def test_get_date_range_for_years(date_manager):
    """Test get_date_range method for year-based periods."""
    today = datetime.now().replace(second=0, microsecond=0)
    one_year_ago = today - relativedelta(years=1)

    start_date, end_date = date_manager.get_date_range("1Y")

    assert start_date == one_year_ago
    assert end_date == today


def test_get_date_range_for_months(date_manager):
    """Test get_date_range method for month-based periods."""
    # Placeholder for future logic; ensures fixture wiring works
    start_date, end_date = date_manager.get_date_range("1M")
    assert isinstance(start_date, datetime) and isinstance(end_date, datetime)

