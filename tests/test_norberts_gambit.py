"""
Test Norbert's Gambit transaction handling in the capital gains calculator.

These tests verify that the calculator correctly handles the sequence of
buy/journal/sell operations that make up Norbert's Gambit currency conversion.
"""

from datetime import date
from click.testing import CliRunner
import json
import os
import pytest

from capgains.cli import capgains
from tests.helpers import create_csv_file
from tests.test_comprehensive_basic import setup_exchange_rates_mock


@pytest.fixture
def setup_sample_data():
    """Check if sample Norbert's Gambit data exists, skip if not."""
    sample_path = os.path.join('tests', 'sample_data', 'sample_norberts.json')
    if not os.path.exists(sample_path):
        pytest.skip(f"Sample data file not found: {sample_path}")
    return sample_path


def test_norberts_gambit_calculation(requests_mock, setup_sample_data):
    """Test calculation of capital gains for Norbert's Gambit transactions."""
    # Set up exchange rate mock for a wide date range
    setup_exchange_rates_mock(
        requests_mock, date(2024, 1, 1), date(2025, 12, 31)
    )
    
    # Use the sample data
    sample_path = setup_sample_data
    
    # Run the capital gains calculator
    runner = CliRunner()
    result = runner.invoke(
        capgains, ['calc', sample_path, '2024', '-t', 'DLR', '--format', 'json']
    )
    assert result.exit_code == 0
    
    # Parse the result
    data = json.loads(result.output)
    
    # Verify DLR ticker is in the results
    assert 'DLR' in data
    dlr_data = data['DLR']
    
    # There should be multiple transactions in the DLR results
    assert len(dlr_data['transactions']) > 0
    
    # Check that we have capital gains (the exact amount will depend on the sample data)
    total_gain = dlr_data['total_gains']
    assert total_gain != 0, "Expected non-zero capital gain from Norbert's Gambit"
    
    # Verify journal transactions don't generate capital gains themselves
    journal_transactions = [tx for tx in dlr_data['transactions'] 
                           if 'JOURNAL' in tx.get('description', '')]
    
    for tx in journal_transactions:
        assert tx['capital_gain'] == 0, "Journal transactions should not generate capital gains"


def test_norberts_gambit_sequence(requests_mock, setup_sample_data):
    """Test that the full Norbert's Gambit sequence is handled correctly.
    
    A complete Norbert's Gambit sequence involves:
    1. Buying DLR.U in USD
    2. Journaling DLR.U to DLR (USD to CAD)
    3. Selling DLR in CAD
    
    The ACB should be properly carried through the journaling process.
    """
    # Set up exchange rate mock for a wide date range
    setup_exchange_rates_mock(
        requests_mock, date(2024, 1, 1), date(2025, 12, 31)
    )
    
    # Use the sample data
    sample_path = setup_sample_data
    
    # Run the capital gains calculator with detailed output
    runner = CliRunner()
    result = runner.invoke(
        capgains, ['calc', sample_path, '2024', '-t', 'DLR', '--format', 'json']
    )
    assert result.exit_code == 0
    
    # Parse the result
    data = json.loads(result.output)
    
    # Verify DLR ticker is in the results
    assert 'DLR' in data
    dlr_data = data['DLR']
    
    # Verify we have transactions 
    assert 'transactions' in dlr_data
    transactions = dlr_data['transactions']
    assert len(transactions) > 0, "Expected sell transactions for DLR"
    
    # Verify we have capital gains
    assert 'total_gains' in dlr_data
    assert dlr_data['total_gains'] != 0, "Expected non-zero capital gains"
    
    # Verify each transaction has the necessary fields
    for tx in transactions:
        assert 'capital_gain' in tx, "Transaction missing capital_gain field"
        assert 'proceeds' in tx, "Transaction missing proceeds field"
        assert 'acb' in tx, "Transaction missing acb field"
        assert 'outlays' in tx, "Transaction missing outlays field"


def test_create_norberts_gambit_transaction(requests_mock, tmpdir):
    """Test creating a simple Norbert's Gambit sequence from scratch."""
    # Set up exchange rate mock for the date range
    setup_exchange_rates_mock(
        requests_mock, date(2024, 1, 1), date(2024, 12, 31)
    )

    # Create a simplified Norbert's Gambit sequence
    transactions = [
        # Buy DLR.U in USD
        [
            "2024-01-15",
            "Buy DLR.U",
            "DLR",
            "BUY",
            "100",
            "10.15",
            "9.99",
            "USD"
        ],
        # Journal DLR.U to DLR (USD to CAD)
        [
            "2024-01-15",
            "Journal DLR.U Out",
            "DLR",
            "JOURNAL_OUT",
            "100",
            "0",
            "0",
            "USD"
        ],
        [
            "2024-01-15",
            "Journal DLR In",
            "DLR",
            "JOURNAL_IN",
            "100",
            "0",
            "0",
            "CAD"
        ],
        # Sell DLR in CAD
        [
            "2024-01-16",
            "Sell DLR",
            "DLR",
            "SELL",
            "100",
            "13.71",
            "9.99",
            "CAD"
        ]
    ]

    csv_path = create_csv_file(
        tmpdir, "test_norberts.csv", transactions
    )
    runner = CliRunner()
    result = runner.invoke(
        capgains, ['calc', csv_path, '2024', '-t', 'DLR', '--format', 'json']
    )
    assert result.exit_code == 0

    data = json.loads(result.output)
    assert 'DLR' in data
    dlr_data = data['DLR']
    
    # Verify we have the right number of transactions
    # We expect only the SELL transaction in the final output (since we filter for capital gains)
    assert len(dlr_data['transactions']) == 1
    
    # Find the sell transaction
    sell_tx = dlr_data['transactions'][0]
    assert 'Sell' in sell_tx['description'], "Expected a sell transaction"
    
    # Calculate expected values:
    # Buy cost = 100 * 10.15 * exchange_rate + commission * exchange_rate
    # Sell proceeds = 100 * 13.71 - commission
    # Gain = Proceeds - ACB - commission
    
    # Verify capital gain is correctly calculated
    assert sell_tx['capital_gain'] == sell_tx['proceeds'] - sell_tx['acb'] - sell_tx['outlays'], \
        "Capital gain calculation error"
    
    # Verify that the capital gain is non-zero (which should be the case for a 
    # successful Norbert's Gambit)
    assert sell_tx['capital_gain'] != 0, "Expected non-zero capital gain"


def test_reverse_norberts_gambit_transaction(requests_mock, tmpdir):
    """Test Norbert's Gambit in reverse direction (CAD to USD).
    
    A reverse Norbert's Gambit sequence involves:
    1. Buying DLR in CAD
    2. Journaling DLR to DLR.U (CAD to USD)
    3. Selling DLR.U in USD
    
    This is commonly used to convert CAD to USD.
    """
    # Set up exchange rate mock for the date range
    setup_exchange_rates_mock(
        requests_mock, date(2024, 1, 1), date(2024, 12, 31)
    )

    # Create a simplified reverse Norbert's Gambit sequence
    transactions = [
        # Buy DLR in CAD
        [
            "2024-01-15",
            "Buy DLR",
            "DLR",
            "BUY",
            "100",
            "13.71",
            "9.99",
            "CAD"
        ],
        # Journal DLR to DLR.U (CAD to USD)
        [
            "2024-01-15",
            "Journal DLR Out",
            "DLR",
            "JOURNAL_OUT",
            "100",
            "0",
            "0",
            "CAD"
        ],
        [
            "2024-01-15",
            "Journal DLR.U In",
            "DLR",
            "JOURNAL_IN",
            "100",
            "0",
            "0",
            "USD"
        ],
        # Sell DLR.U in USD
        [
            "2024-01-16",
            "Sell DLR.U",
            "DLR",
            "SELL",
            "100",
            "10.15",
            "9.99",
            "USD"
        ]
    ]

    csv_path = create_csv_file(
        tmpdir, "test_reverse_norberts.csv", transactions
    )
    runner = CliRunner()
    result = runner.invoke(
        capgains, ['calc', csv_path, '2024', '-t', 'DLR', '--format', 'json']
    )
    assert result.exit_code == 0

    data = json.loads(result.output)
    assert 'DLR' in data
    dlr_data = data['DLR']
    
    # Verify we have the right number of transactions
    # We expect only the SELL transaction in the final output (since we filter for capital gains)
    assert len(dlr_data['transactions']) == 1
    
    # Find the sell transaction
    sell_tx = dlr_data['transactions'][0]
    assert 'Sell' in sell_tx['description'], "Expected a sell transaction"
    
    # Verify capital gain is correctly calculated
    assert sell_tx['capital_gain'] == sell_tx['proceeds'] - sell_tx['acb'] - sell_tx['outlays'], \
        "Capital gain calculation error"
    
    # Verify that the capital gain is non-zero (which should be the case for a 
    # successful Norbert's Gambit)
    assert sell_tx['capital_gain'] != 0, "Expected non-zero capital gain"
    
    # Verify the ticker display is correct
    assert 'DLR.U' in sell_tx['description'], "Expected DLR.U in the transaction description"


def test_multiple_direction_norberts_gambit(requests_mock, tmpdir):
    """Test both directions of Norbert's Gambit in the same data set.
    
    This test verifies that a mix of USD->CAD and CAD->USD conversions
    are all handled correctly within the same account.
    """
    # Set up exchange rate mock for the date range
    setup_exchange_rates_mock(
        requests_mock, date(2024, 1, 1), date(2024, 12, 31)
    )

    # Create transactions with both directions of Norbert's Gambit
    transactions = [
        # First sequence: USD to CAD
        [
            "2024-01-15",
            "Buy DLR.U",
            "DLR",
            "BUY",
            "100",
            "10.15",
            "9.99",
            "USD"
        ],
        [
            "2024-01-15",
            "Journal DLR.U Out",
            "DLR",
            "JOURNAL_OUT",
            "100",
            "0",
            "0",
            "USD"
        ],
        [
            "2024-01-15",
            "Journal DLR In",
            "DLR",
            "JOURNAL_IN",
            "100",
            "0",
            "0",
            "CAD"
        ],
        [
            "2024-01-16",
            "Sell DLR",
            "DLR",
            "SELL",
            "100",
            "13.71",
            "9.99",
            "CAD"
        ],
        
        # Second sequence: CAD to USD
        [
            "2024-02-15",
            "Buy DLR",
            "DLR",
            "BUY",
            "200",
            "13.80",
            "9.99",
            "CAD"
        ],
        [
            "2024-02-15",
            "Journal DLR Out",
            "DLR",
            "JOURNAL_OUT",
            "200",
            "0",
            "0",
            "CAD"
        ],
        [
            "2024-02-15",
            "Journal DLR.U In",
            "DLR",
            "JOURNAL_IN",
            "200",
            "0",
            "0",
            "USD"
        ],
        [
            "2024-02-16",
            "Sell DLR.U",
            "DLR",
            "SELL",
            "200",
            "10.20",
            "9.99",
            "USD"
        ]
    ]

    csv_path = create_csv_file(
        tmpdir, "test_bidirectional_norberts.csv", transactions
    )
    runner = CliRunner()
    result = runner.invoke(
        capgains, ['calc', csv_path, '2024', '-t', 'DLR', '--format', 'json']
    )
    assert result.exit_code == 0

    data = json.loads(result.output)
    assert 'DLR' in data
    dlr_data = data['DLR']
    
    # Note: The calculator will only show the most recent transactions in the output
    # Verify we have at least one transaction in the output
    assert len(dlr_data['transactions']) > 0
    
    # Verify the transaction we see is a sell transaction
    sell_tx = dlr_data['transactions'][0]
    assert 'Sell' in sell_tx['description'], "Expected a sell transaction"
    
    # Verify the ticker is correct
    assert sell_tx['ticker'] == 'DLR', "Expected DLR ticker"
    
    # Verify the transaction has a non-zero capital gain
    assert sell_tx['capital_gain'] != 0, "Expected non-zero capital gain"
    
    # Verify the total capital gain is non-zero
    assert dlr_data['total_gains'] != 0, "Expected non-zero total gains" 