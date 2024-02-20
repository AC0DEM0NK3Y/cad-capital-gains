from datetime import date, timedelta
from click.testing import CliRunner
import tempfile
import csv
import json
import os

from capgains.cli import capgains
from capgains.commands.capgains_maxcost import (
    _get_max_cost, _get_year_end_cost, calculate_costs
)
from capgains.transaction import Transaction
from capgains.transactions import Transactions
from capgains.exchange_rate import ExchangeRate


def create_csv_file(transactions):
    """Helper function to create a temporary CSV file with transactions."""
    fd, path = tempfile.mkstemp()
    with os.fdopen(fd, 'w', newline='') as f:
        writer = csv.writer(f)
        for t in transactions:
            writer.writerow(
                [
                    t.date.strftime('%Y-%m-%d'),
                    t.description,
                    t.ticker,
                    t.action,
                    t.qty,
                    t.price,
                    t.commission,
                    t.currency
                ]
            )
    return path


def setup_exchange_rates_mock(requests_mock, transactions):
    """Helper function to set up exchange rate mocking for a list of
    transactions."""
    # Get the earliest and latest dates
    dates = [t.date for t in transactions]
    if not dates:
        return

    # For noon rates (before 2017-01-03)
    noon_observations = []
    min_date = min(dates)
    if min_date < date(2017, 1, 3):
        # Add noon rates from min_date to 2017-01-02
        # Account for double 7-day lookback
        current_date = min_date - timedelta(days=14)
        end_date = min(max(dates), date(2017, 1, 2))
        while current_date <= end_date:
            noon_observations.append(
                {
                    'd': current_date.isoformat(), 'IEXE0101': {
                        'v': '2.0'
                    }
                }
            )
            current_date += timedelta(days=1)
        requests_mock.get(
            f"{ExchangeRate.valet_obs_url}/IEXE0101/json",
            json={"observations": noon_observations}
        )

    # For indicative rates (after 2017-01-03)
    indicative_observations = []
    if max(dates) >= date(2017, 1, 3):
        # Add indicative rates from 2017-01-03 to max_date
        current_date = max(date(2017, 1, 3), min_date - timedelta(days=14))
        while current_date <= max(dates):
            indicative_observations.append(
                {
                    'd': current_date.isoformat(), 'FXUSDCAD': {
                        'v': '2.0'
                    }
                }
            )
            current_date += timedelta(days=1)
        requests_mock.get(
            f"{ExchangeRate.valet_obs_url}/FXUSDCAD/json",
            json={"observations": indicative_observations}
        )


def test_basic_max_cost(requests_mock):
    """Test basic max cost calculation within a single year."""
    transactions = [
        Transaction(
            date(2018, 1, 1),
            'Buy',
            'AAPL',
            'BUY',
            100,
            150.00,  # Total cost: 15,000 USD = 30,000 CAD
            0.00,
            'USD'
        ),
        Transaction(
            date(2018, 6, 1),
            'Buy More',
            'AAPL',
            'BUY',
            50,
            200.00,  # Additional 10,000 USD = 20,000 CAD, Total: 50,000 CAD
            0.00,
            'USD'
        ),
        Transaction(
            date(2018, 12, 1),
            'Sell Half',
            'AAPL',
            'SELL',
            75,
            # Reduces by 25,000 CAD (75 shares * 333.33 ACB/share), End: 25,000
            # CAD
            180.00,
            0.00,
            'USD'
        )
    ]
    setup_exchange_rates_mock(requests_mock, transactions)
    csv_path = create_csv_file(transactions)

    runner = CliRunner()
    result = runner.invoke(capgains, ['maxcost', csv_path, '2018'])

    os.unlink(csv_path)

    assert result.exit_code == 0
    assert "Max cost = 50,000.00" in result.output
    # Updated to match actual ACB calculation
    assert "Year end = 25,000.00" in result.output


def test_multi_year_max_cost(requests_mock):
    """Test max cost calculation across multiple years with previous year
    consideration."""
    transactions = [
        Transaction(
            date(2017, 6, 1),
            'Initial Buy',
            'GOOGL',
            'BUY',
            100,
            100.00,  # 10,000 USD = 20,000 CAD
            0.00,
            'USD'
        ),
        Transaction(
            date(2018, 1, 1),
            'Buy More',
            'GOOGL',
            'BUY',
            50,
            150.00,  # Additional 7,500 USD = 15,000 CAD, Total: 35,000 CAD
            0.00,
            'USD'
        ),
        Transaction(
            date(2018, 12, 31),
            'Sell Some',
            'GOOGL',
            'SELL',
            75,
            200.00,  # Reduces by 26,250 CAD, End: 8,750 CAD
            0.00,
            'USD'
        )
    ]
    setup_exchange_rates_mock(requests_mock, transactions)
    transactions = Transactions(transactions)

    # Calculate costs first
    transactions_with_costs = calculate_costs(transactions, 2018, 'GOOGL')

    # Test 2017
    result = _get_max_cost(transactions_with_costs, 2017, 2017)
    assert result == 20000.00

    # Test 2018 (should consider 2017 year-end)
    result = _get_max_cost(transactions_with_costs, 2018, 2017)
    assert result == 35000.00


def test_multi_currency_max_cost(requests_mock):
    """Test max cost calculation with mixed CAD and USD transactions."""
    transactions = [
        Transaction(
            date(2018, 1, 1),
            'Buy CAD',
            'TD',
            'BUY',
            100,
            50.00,  # 5,000 CAD
            0.00,
            'CAD'
        ),
        Transaction(
            date(2018, 6, 1),
            'Buy USD',
            'TD',
            'BUY',
            100,
            75.00,  # 7,500 USD = 15,000 CAD, Total: 20,000 CAD
            0.00,
            'USD'
        )
    ]
    setup_exchange_rates_mock(requests_mock, transactions)
    csv_path = create_csv_file(transactions)

    runner = CliRunner()
    result = runner.invoke(capgains, ['maxcost', csv_path, '2018'])

    os.unlink(csv_path)

    assert result.exit_code == 0
    assert "Max cost = 20,000.00" in result.output
    assert "Year end = 20,000.00" in result.output


def test_year_end_cost_fallback(requests_mock):
    """Test year-end cost calculation with fallback to previous years."""
    transactions = [
        Transaction(
            date(2017, 1, 1),
            'Buy',
            'MSFT',
            'BUY',
            100,
            50.00,  # 5,000 USD = 10,000 CAD
            0.00,
            'USD'
        ),
        # No transactions in 2018
        Transaction(
            date(2019, 1, 1),
            'Buy More',
            'MSFT',
            'BUY',
            50,
            100.00,  # Additional 5,000 USD = 10,000 CAD, Total: 20,000 CAD
            0.00,
            'USD'
        )
    ]
    setup_exchange_rates_mock(requests_mock, transactions)
    transactions = Transactions(transactions)

    # Calculate costs first
    transactions_with_costs = calculate_costs(transactions, 2019, 'MSFT')

    # 2018 should fall back to 2017 year-end cost
    result = _get_year_end_cost(transactions_with_costs, 2018, 2017)
    assert result == 10000.00


def test_t1135_threshold_warning_exceeded(requests_mock):
    """Test T1135 warning is displayed when threshold ($100,000 CAD) is
    exceeded."""
    transactions = [
        Transaction(
            date(2018, 1, 1),
            'Large Buy',
            'SPY',
            'BUY',
            1000,
            90.00,  # 90,000 USD = 180,000 CAD
            0.00,
            'USD'
        ),
        Transaction(
            date(2018, 6, 1),
            'Sell Most',
            'SPY',
            'SELL',
            900,
            95.00,  # Reduces by 162,000 CAD, End: 18,000 CAD
            0.00,
            'USD'
        )
    ]
    setup_exchange_rates_mock(requests_mock, transactions)
    csv_path = create_csv_file(transactions)

    runner = CliRunner()
    result = runner.invoke(capgains, ['maxcost', csv_path, '2018'])

    os.unlink(csv_path)

    assert result.exit_code == 0
    assert "Max cost = 180,000.00" in result.output  # Above T1135 threshold
    assert "Year end = 18,000.00" in result.output  # Below T1135 threshold
    assert "[FOREIGN]" in result.output  # USD stock marked as foreign
    assert "T1135 Summary" in result.output
    assert "$180,000.00 CAD" in result.output
    assert "WARNING" in result.output
    assert "exceeds $100,000 CAD" in result.output


def test_t1135_threshold_not_exceeded(requests_mock):
    """Test no T1135 warning when threshold is not exceeded."""
    transactions = [
        Transaction(
            date(2018, 1, 1),
            'Small Buy',
            'AAPL',
            'BUY',
            100,
            50.00,  # 5,000 USD = 10,000 CAD (below threshold)
            0.00,
            'USD'
        )
    ]
    setup_exchange_rates_mock(requests_mock, transactions)
    csv_path = create_csv_file(transactions)

    runner = CliRunner()
    result = runner.invoke(capgains, ['maxcost', csv_path, '2018'])

    os.unlink(csv_path)

    assert result.exit_code == 0
    assert "T1135 Summary" in result.output
    assert "[FOREIGN]" in result.output
    assert "$10,000.00 CAD" in result.output
    assert "WARNING" not in result.output


def test_t1135_json_output_with_summary(requests_mock):
    """Test JSON output includes T1135 summary."""
    transactions = [
        Transaction(
            date(2018, 1, 1),
            'Large Buy',
            'SPY',
            'BUY',
            1000,
            90.00,  # 90,000 USD = 180,000 CAD
            0.00,
            'USD'
        )
    ]
    setup_exchange_rates_mock(requests_mock, transactions)
    csv_path = create_csv_file(transactions)

    runner = CliRunner()
    result = runner.invoke(
        capgains, ['maxcost', csv_path, '2018', '--format', 'json']
    )

    os.unlink(csv_path)

    assert result.exit_code == 0
    output = json.loads(result.output)

    # Check ticker data includes is_foreign_security flag
    assert 'SPY' in output
    assert output['SPY']['is_foreign_security'] is True
    assert output['SPY']['counts_for_t1135'] is True

    # Check T1135 summary
    assert '_t1135_summary' in output
    assert output['_t1135_summary']['total_max_cost'] == 180000.00
    assert output['_t1135_summary']['threshold'] == 100000.00
    assert output['_t1135_summary']['exceeds_threshold'] is True
    assert output['_t1135_summary']['foreign_broker'] is False


def test_empty_transactions():
    """Test handling of empty transaction list."""
    csv_path = create_csv_file([])

    runner = CliRunner()
    result = runner.invoke(capgains, ['maxcost', csv_path, '2018'])

    os.unlink(csv_path)

    assert result.exit_code == 0
    assert "No transactions available" in result.output


def test_year_min_boundary(requests_mock):
    """Test handling of year_min boundary in cost calculations."""
    transactions = [
        Transaction(
            date(2017, 1, 1),
            'Buy',
            'NVDA',
            'BUY',
            100,
            50.00,  # 5,000 USD = 10,000 CAD
            0.00,
            'USD'
        )
    ]
    setup_exchange_rates_mock(requests_mock, transactions)
    transactions = Transactions(transactions)

    # Calculate costs first
    transactions_with_costs = calculate_costs(transactions, 2017, 'NVDA')

    # Testing at year_min boundary
    result = _get_year_end_cost(transactions_with_costs, 2017, 2017)
    assert result == 10000.00

    # Testing before year_min (should return 0)
    result = _get_year_end_cost(transactions_with_costs, 2016, 2017)
    assert result == 0


def test_no_transactions_in_year(transactions):
    """Test handling of a year with no transactions."""
    # Get the earliest year in the transactions
    min_year = min(t.date.year for t in transactions)

    # Test with a year before any transactions
    result = _get_year_end_cost(transactions, min_year - 1, min_year)
    assert result == 0

    # Test max cost for a year with no transactions
    result = _get_max_cost(transactions, min_year - 1, min_year)
    assert result == 0


def test_t1135_exactly_at_threshold(requests_mock):
    """Test no warning when exactly at $100,000 threshold (> not >=)."""
    transactions = [
        Transaction(
            date(2018, 1, 1),
            'Buy Exactly 100k',
            'SPY',
            'BUY',
            1000,
            50.00,  # 50,000 USD = 100,000 CAD (exactly at threshold)
            0.00,
            'USD'
        )
    ]
    setup_exchange_rates_mock(requests_mock, transactions)
    csv_path = create_csv_file(transactions)

    runner = CliRunner()
    result = runner.invoke(capgains, ['maxcost', csv_path, '2018'])

    os.unlink(csv_path)

    assert result.exit_code == 0
    assert "T1135 Summary" in result.output
    assert "$100,000.00 CAD" in result.output
    # Should NOT show warning - threshold is > not >=
    assert "WARNING" not in result.output


def test_t1135_multiple_tickers_sum_exceeds(requests_mock):
    """Test T1135 warning when multiple foreign tickers sum to exceed
    threshold."""
    transactions = [
        Transaction(
            date(2018, 1, 1),
            'Buy AAPL',
            'AAPL',
            'BUY',
            500,
            60.00,  # 30,000 USD = 60,000 CAD
            0.00,
            'USD'
        ),
        Transaction(
            date(2018, 1, 1),
            'Buy GOOGL',
            'GOOGL',
            'BUY',
            500,
            50.00,  # 25,000 USD = 50,000 CAD
            0.00,
            'USD'
        )
    ]
    setup_exchange_rates_mock(requests_mock, transactions)
    csv_path = create_csv_file(transactions)

    runner = CliRunner()
    result = runner.invoke(capgains, ['maxcost', csv_path, '2018'])

    os.unlink(csv_path)

    assert result.exit_code == 0
    # Each ticker individually below threshold, but sum exceeds
    assert "Max cost = 60,000.00" in result.output  # AAPL
    assert "Max cost = 50,000.00" in result.output  # GOOGL
    assert "$110,000.00 CAD" in result.output  # Total
    assert "WARNING" in result.output


def test_t1135_json_output_not_exceeded(requests_mock):
    """Test JSON output when threshold is NOT exceeded."""
    transactions = [
        Transaction(
            date(2018, 1, 1),
            'Small Buy',
            'AAPL',
            'BUY',
            100,
            25.00,  # 2,500 USD = 5,000 CAD
            0.00,
            'USD'
        )
    ]
    setup_exchange_rates_mock(requests_mock, transactions)
    csv_path = create_csv_file(transactions)

    runner = CliRunner()
    result = runner.invoke(
        capgains, ['maxcost', csv_path, '2018', '--format', 'json']
    )

    os.unlink(csv_path)

    assert result.exit_code == 0
    output = json.loads(result.output)

    assert '_t1135_summary' in output
    assert output['_t1135_summary']['total_max_cost'] == 5000.00
    assert output['_t1135_summary']['exceeds_threshold'] is False


def test_t1135_cad_stocks_excluded_by_default():
    """Test that CAD stocks are NOT counted by default (Canadian broker)."""
    transactions = [
        Transaction(
            date(2018, 1, 1),
            'Buy Canadian Stock',
            'TD.TO',
            'BUY',
            1000,
            100.00,  # 100,000 CAD - not counted (Canadian broker default)
            0.00,
            'CAD'
        ),
        Transaction(
            date(2018, 1, 1),
            'Buy Another Canadian',
            'RY.TO',
            'BUY',
            500,
            100.00,  # 50,000 CAD - not counted
            0.00,
            'CAD'
        )
    ]
    csv_path = create_csv_file(transactions)

    runner = CliRunner()
    result = runner.invoke(capgains, ['maxcost', csv_path, '2018'])

    os.unlink(csv_path)

    assert result.exit_code == 0
    # Total should be $0 (CAD stocks not counted by default)
    assert "$0.00 CAD" in result.output
    # No warning since $0
    assert "WARNING" not in result.output
    assert "Canadian broker" in result.output


def test_t1135_foreign_broker_includes_cad():
    """Test --foreign-broker flag includes CAD stocks in T1135."""
    transactions = [
        Transaction(
            date(2018, 1, 1),
            'Buy Canadian Stock',
            'TD.TO',
            'BUY',
            1000,
            100.00,  # 100,000 CAD - included with --foreign-broker
            0.00,
            'CAD'
        ),
        Transaction(
            date(2018, 1, 1),
            'Buy Another Canadian',
            'RY.TO',
            'BUY',
            500,
            100.00,  # 50,000 CAD - included
            0.00,
            'CAD'
        )
    ]
    csv_path = create_csv_file(transactions)

    runner = CliRunner()
    result = runner.invoke(
        capgains, ['maxcost', csv_path, '2018', '--foreign-broker']
    )

    os.unlink(csv_path)

    assert result.exit_code == 0
    # CAD stocks marked as included via --foreign-broker flag
    assert "[CAD - included via --foreign-broker]" in result.output
    # Total should be $150,000 (all counted)
    assert "$150,000.00 CAD" in result.output
    # Warning should appear
    assert "WARNING" in result.output
    assert "foreign broker" in result.output


def test_t1135_mixed_default_only_usd_counted(requests_mock):
    """Test default behavior only counts USD stocks (Canadian broker)."""
    transactions = [
        Transaction(
            date(2018, 1, 1),
            'Buy Canadian Stock',
            'TD.TO',
            'BUY',
            1000,
            100.00,  # 100,000 CAD - not counted
            0.00,
            'CAD'
        ),
        Transaction(
            date(2018, 1, 1),
            'Buy US Stock',
            'AAPL',
            'BUY',
            500,
            60.00,  # 30,000 USD = 60,000 CAD - counted
            0.00,
            'USD'
        )
    ]
    setup_exchange_rates_mock(requests_mock, transactions)
    csv_path = create_csv_file(transactions)

    runner = CliRunner()
    result = runner.invoke(capgains, ['maxcost', csv_path, '2018'])

    os.unlink(csv_path)

    assert result.exit_code == 0
    # AAPL marked as foreign
    assert "[FOREIGN]" in result.output
    # Only AAPL counted - $60,000 total
    assert "$60,000.00 CAD" in result.output
    # No warning since < $100,000
    assert "WARNING" not in result.output


def test_t1135_mixed_foreign_broker_all_counted(requests_mock):
    """Test --foreign-broker counts all stocks."""
    transactions = [
        Transaction(
            date(2018, 1, 1),
            'Buy Canadian Stock',
            'TD.TO',
            'BUY',
            1000,
            100.00,  # 100,000 CAD - counted with --foreign-broker
            0.00,
            'CAD'
        ),
        Transaction(
            date(2018, 1, 1),
            'Buy US Stock',
            'AAPL',
            'BUY',
            500,
            60.00,  # 30,000 USD = 60,000 CAD - counted
            0.00,
            'USD'
        )
    ]
    setup_exchange_rates_mock(requests_mock, transactions)
    csv_path = create_csv_file(transactions)

    runner = CliRunner()
    result = runner.invoke(
        capgains, ['maxcost', csv_path, '2018', '--foreign-broker']
    )

    os.unlink(csv_path)

    assert result.exit_code == 0
    # Both stocks counted - $160,000 total
    assert "$160,000.00 CAD" in result.output
    # Warning since > $100,000
    assert "WARNING" in result.output


def test_t1135_json_default_canadian_broker(requests_mock):
    """Test JSON output with default Canadian broker behavior."""
    transactions = [
        Transaction(
            date(2018, 1, 1),
            'Buy Canadian',
            'TD.TO',
            'BUY',
            100,
            50.00,  # 5,000 CAD
            0.00,
            'CAD'
        ),
        Transaction(
            date(2018, 1, 1),
            'Buy US',
            'AAPL',
            'BUY',
            100,
            50.00,  # 5,000 USD = 10,000 CAD
            0.00,
            'USD'
        )
    ]
    setup_exchange_rates_mock(requests_mock, transactions)
    csv_path = create_csv_file(transactions)

    runner = CliRunner()
    result = runner.invoke(
        capgains, ['maxcost', csv_path, '2018', '--format', 'json']
    )

    os.unlink(csv_path)

    assert result.exit_code == 0
    output = json.loads(result.output)

    # TD.TO should be marked as NOT foreign and NOT counted for T1135
    assert output['TD.TO']['is_foreign_security'] is False
    assert output['TD.TO']['counts_for_t1135'] is False
    assert output['TD.TO']['max_cost'] == 5000.00

    # AAPL should be marked as foreign and counted for T1135
    assert output['AAPL']['is_foreign_security'] is True
    assert output['AAPL']['counts_for_t1135'] is True
    assert output['AAPL']['max_cost'] == 10000.00

    # Only AAPL counted in T1135 total
    assert output['_t1135_summary']['total_max_cost'] == 10000.00
    assert output['_t1135_summary']['foreign_broker'] is False
    assert output['_t1135_summary']['exceeds_threshold'] is False


def test_t1135_json_foreign_broker_all_counted(requests_mock):
    """Test JSON output with --foreign-broker counts all stocks."""
    transactions = [
        Transaction(
            date(2018, 1, 1),
            'Buy Canadian',
            'TD.TO',
            'BUY',
            100,
            50.00,  # 5,000 CAD
            0.00,
            'CAD'
        ),
        Transaction(
            date(2018, 1, 1),
            'Buy US',
            'AAPL',
            'BUY',
            100,
            50.00,  # 5,000 USD = 10,000 CAD
            0.00,
            'USD'
        )
    ]
    setup_exchange_rates_mock(requests_mock, transactions)
    csv_path = create_csv_file(transactions)

    runner = CliRunner()
    result = runner.invoke(
        capgains,
        ['maxcost', csv_path, '2018', '--format', 'json', '--foreign-broker']
    )

    os.unlink(csv_path)

    assert result.exit_code == 0
    output = json.loads(result.output)

    # TD.TO is not foreign but counts with --foreign-broker
    assert output['TD.TO']['is_foreign_security'] is False
    assert output['TD.TO']['counts_for_t1135'] is True

    # AAPL is foreign and counts
    assert output['AAPL']['is_foreign_security'] is True
    assert output['AAPL']['counts_for_t1135'] is True

    # Both counted in T1135 total
    assert output['_t1135_summary']['total_max_cost'] == 15000.00
    assert output['_t1135_summary']['foreign_broker'] is True
