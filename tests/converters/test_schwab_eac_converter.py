"""
Test Schwab Equity Awards Center (EAC) converter functionality.

These tests verify that the Schwab EAC converter correctly parses
and converts transaction data from Schwab's JSON export format.
"""

import json
import os
import pytest
from click.testing import CliRunner
from decimal import Decimal

from capgains.cli import capgains
from capgains.converters.schwab_eac import (
    convert_schwab_date,
    convert_schwab_amount,
    convert_schwab_transaction,
    group_and_sort_transactions,
    convert_schwab_file
)


class TestConvertSchwabDate:
    """Tests for date conversion from Schwab format."""

    def test_convert_standard_date(self):
        """Test conversion of standard MM/DD/YYYY format."""
        assert convert_schwab_date('01/15/2024') == '2024-01-15'
        assert convert_schwab_date('12/31/2023') == '2023-12-31'

    def test_convert_single_digit_month_day(self):
        """Test conversion with single digit month and day."""
        assert convert_schwab_date('1/5/2024') == '2024-01-05'
        assert convert_schwab_date('9/1/2024') == '2024-09-01'


class TestConvertSchwabAmount:
    """Tests for amount conversion from Schwab format."""

    def test_convert_positive_amount(self):
        """Test conversion of positive dollar amounts."""
        assert convert_schwab_amount('$123.45') == Decimal('123.45')
        assert convert_schwab_amount('$1,234.56') == Decimal('1234.56')

    def test_convert_negative_amount(self):
        """Test conversion of negative dollar amounts."""
        assert convert_schwab_amount('-$123.45') == Decimal('-123.45')
        assert convert_schwab_amount('-$1,234.56') == Decimal('-1234.56')

    def test_convert_empty_amount(self):
        """Test conversion of empty or None amounts."""
        assert convert_schwab_amount('') == Decimal('0')
        assert convert_schwab_amount(None) == Decimal('0')

    def test_convert_large_amount(self):
        """Test conversion of large amounts with multiple commas."""
        assert convert_schwab_amount('$1,234,567.89') == Decimal('1234567.89')


class TestConvertSchwabTransaction:
    """Tests for single transaction conversion."""

    def test_convert_espp_deposit(self):
        """Test conversion of ESPP deposit transaction."""
        tx = {
            'Date': '01/15/2024',
            'Action': 'Deposit',
            'Symbol': 'AAPL',
            'Description': 'ESPP',
            'Quantity': '10',
            'TransactionDetails': [
                {
                    'Details': {
                        'PurchaseFairMarketValue': '$150.00'
                    }
                }
            ]
        }

        result = convert_schwab_transaction(tx)

        assert result is not None
        assert result['date'] == '2024-01-15'
        assert result['ticker'] == 'AAPL'
        assert result['action'] == 'BUY'
        assert result['qty'] == 10.0
        assert result['price'] == 150.0
        assert result['commission'] == 0.0
        assert result['currency'] == 'USD'
        assert result['description'] == 'ESPP'

    def test_convert_rsu_deposit(self):
        """Test conversion of RSU deposit transaction."""
        tx = {
            'Date': '02/20/2024',
            'Action': 'Deposit',
            'Symbol': 'GOOGL',
            'Description': 'RS',
            'Quantity': '5',
            'TransactionDetails': [
                {
                    'Details': {
                        'VestFairMarketValue': '$175.50'
                    }
                }
            ]
        }

        result = convert_schwab_transaction(tx)

        assert result is not None
        assert result['date'] == '2024-02-20'
        assert result['ticker'] == 'GOOGL'
        assert result['action'] == 'BUY'
        assert result['qty'] == 5.0
        assert result['price'] == 175.50
        assert result['description'] == 'RS'

    def test_convert_share_sale(self):
        """Test conversion of share sale transaction."""
        tx = {
            'Date': '03/10/2024',
            'Action': 'Sale',
            'Symbol': 'MSFT',
            'Description': 'Share Sale',
            'Quantity': '20',
            'TransactionDetails': [{
                'Details': {
                    'SalePrice': '$420.00'
                }
            }]
        }

        result = convert_schwab_transaction(tx)

        assert result is not None
        assert result['date'] == '2024-03-10'
        assert result['ticker'] == 'MSFT'
        assert result['action'] == 'SELL'
        assert result['qty'] == 20.0
        assert result['price'] == 420.0
        assert result['description'] == 'Share Sale'

    def test_skip_tax_withholding(self):
        """Test that tax withholding transactions are skipped."""
        tx = {
            'Date': '01/15/2024',
            'Action': 'Tax Withholding',
            'Symbol': 'AAPL',
            'Description': 'Tax',
            'Quantity': '2',
            'TransactionDetails': []
        }

        result = convert_schwab_transaction(tx)
        assert result is None

    def test_skip_dividend(self):
        """Test that dividend transactions are skipped."""
        tx = {
            'Date': '01/15/2024',
            'Action': 'Dividend',
            'Symbol': 'AAPL',
            'Description': 'Dividend',
            'Quantity': '',
            'TransactionDetails': []
        }

        result = convert_schwab_transaction(tx)
        assert result is None

    def test_skip_transfer(self):
        """Test that transfer transactions are skipped."""
        tx = {
            'Date': '01/15/2024',
            'Action': 'Transfer',
            'Symbol': 'AAPL',
            'Description': 'Transfer',
            'Quantity': '10',
            'TransactionDetails': []
        }

        result = convert_schwab_transaction(tx)
        assert result is None

    def test_ticker_filter_includes(self):
        """Test that ticker filter includes matching tickers."""
        tx = {
            'Date': '01/15/2024',
            'Action': 'Deposit',
            'Symbol': 'AAPL',
            'Description': 'ESPP',
            'Quantity': '10',
            'TransactionDetails': [
                {
                    'Details': {
                        'PurchaseFairMarketValue': '$150.00'
                    }
                }
            ]
        }

        result = convert_schwab_transaction(tx, tickers=['AAPL', 'GOOGL'])
        assert result is not None

    def test_ticker_filter_excludes(self):
        """Test that ticker filter excludes non-matching tickers."""
        tx = {
            'Date': '01/15/2024',
            'Action': 'Deposit',
            'Symbol': 'MSFT',
            'Description': 'ESPP',
            'Quantity': '10',
            'TransactionDetails': [
                {
                    'Details': {
                        'PurchaseFairMarketValue': '$150.00'
                    }
                }
            ]
        }

        result = convert_schwab_transaction(tx, tickers=['AAPL', 'GOOGL'])
        assert result is None


class TestGroupAndSortTransactions:
    """Tests for transaction grouping and sorting."""

    def test_sort_by_date(self):
        """Test that transactions are sorted by date."""
        transactions = [
            {
                'date': '2024-03-01', 'description': 'ESPP', 'action': 'BUY'
            },
            {
                'date': '2024-01-01', 'description': 'ESPP', 'action': 'BUY'
            },
            {
                'date': '2024-02-01', 'description': 'ESPP', 'action': 'BUY'
            },
        ]

        result = group_and_sort_transactions(transactions)

        assert result[0]['date'] == '2024-01-01'
        assert result[1]['date'] == '2024-02-01'
        assert result[2]['date'] == '2024-03-01'

    def test_sort_same_date_by_description(self):
        """Test that transactions on same date are sorted by description."""
        transactions = [
            {
                'date': '2024-01-15',
                'description': 'Share Sale',
                'action': 'SELL'
            },
            {
                'date': '2024-01-15', 'description': 'ESPP', 'action': 'BUY'
            },
            {
                'date': '2024-01-15', 'description': 'RS', 'action': 'BUY'
            },
        ]

        result = group_and_sort_transactions(transactions)

        # ESPP (0), RS (1), Share Sale (2)
        assert result[0]['description'] == 'ESPP'
        assert result[1]['description'] == 'RS'
        assert result[2]['description'] == 'Share Sale'

    def test_sort_same_date_description_by_action(self):
        """Test same date/desc sorted by action (BUY before SELL)."""
        transactions = [
            {
                'date': '2024-01-15',
                'description': 'Share Sale',
                'action': 'SELL'
            },
            {
                'date': '2024-01-15',
                'description': 'Share Sale',
                'action': 'BUY'
            },
        ]

        result = group_and_sort_transactions(transactions)

        assert result[0]['action'] == 'BUY'
        assert result[1]['action'] == 'SELL'


class TestConvertSchwabFile:
    """Tests for full file conversion."""

    def test_convert_file_success(self, tmpdir):
        """Test successful conversion of a Schwab JSON file."""
        # Create sample input data
        input_data = {
            'Transactions': [
                {
                    'Date': '01/15/2024',
                    'Action': 'Deposit',
                    'Symbol': 'AAPL',
                    'Description': 'ESPP',
                    'Quantity': '10',
                    'TransactionDetails': [
                        {
                            'Details': {
                                'PurchaseFairMarketValue': '$150.00'
                            }
                        }
                    ]
                },
                {
                    'Date': '01/20/2024',
                    'Action': 'Sale',
                    'Symbol': 'AAPL',
                    'Description': 'Share Sale',
                    'Quantity': '5',
                    'TransactionDetails': [
                        {
                            'Details': {
                                'SalePrice': '$155.00'
                            }
                        }
                    ]
                }
            ]
        }

        input_file = os.path.join(tmpdir, 'schwab_input.json')
        output_file = os.path.join(tmpdir, 'output.json')

        with open(input_file, 'w') as f:
            json.dump(input_data, f)

        convert_schwab_file(input_file, output_file)

        # Verify output file was created
        assert os.path.exists(output_file)

        # Load and verify output
        with open(output_file, 'r') as f:
            output_data = json.load(f)

        assert len(output_data) == 2
        assert output_data[0]['action'] == 'BUY'
        assert output_data[1]['action'] == 'SELL'

    def test_convert_file_with_ticker_filter(self, tmpdir):
        """Test conversion with ticker filtering."""
        input_data = {
            'Transactions': [
                {
                    'Date': '01/15/2024',
                    'Action': 'Deposit',
                    'Symbol': 'AAPL',
                    'Description': 'ESPP',
                    'Quantity': '10',
                    'TransactionDetails': [
                        {
                            'Details': {
                                'PurchaseFairMarketValue': '$150.00'
                            }
                        }
                    ]
                },
                {
                    'Date': '01/15/2024',
                    'Action': 'Deposit',
                    'Symbol': 'GOOGL',
                    'Description': 'RS',
                    'Quantity': '5',
                    'TransactionDetails': [
                        {
                            'Details': {
                                'VestFairMarketValue': '$175.00'
                            }
                        }
                    ]
                }
            ]
        }

        input_file = os.path.join(tmpdir, 'schwab_input.json')
        output_file = os.path.join(tmpdir, 'output.json')

        with open(input_file, 'w') as f:
            json.dump(input_data, f)

        convert_schwab_file(input_file, output_file, tickers=['AAPL'])

        with open(output_file, 'r') as f:
            output_data = json.load(f)

        assert len(output_data) == 1
        assert output_data[0]['ticker'] == 'AAPL'

    def test_convert_file_not_found(self, tmpdir):
        """Test that FileNotFoundError is raised for missing input file."""
        output_file = os.path.join(tmpdir, 'output.json')

        with pytest.raises(FileNotFoundError):
            convert_schwab_file('/nonexistent/file.json', output_file)

    def test_convert_invalid_json(self, tmpdir):
        """Test that JSONDecodeError is raised for invalid JSON."""
        input_file = os.path.join(tmpdir, 'invalid.json')
        output_file = os.path.join(tmpdir, 'output.json')

        with open(input_file, 'w') as f:
            f.write('not valid json')

        with pytest.raises(json.JSONDecodeError):
            convert_schwab_file(input_file, output_file)


class TestSchwabConverterCLI:
    """Tests for the Schwab converter CLI command."""

    def test_cli_convert_schwab_eac(self, tmpdir):
        """Test the convert schwab-eac CLI command."""
        input_data = {
            'Transactions': [
                {
                    'Date': '01/15/2024',
                    'Action': 'Deposit',
                    'Symbol': 'AAPL',
                    'Description': 'ESPP',
                    'Quantity': '10',
                    'TransactionDetails': [
                        {
                            'Details': {
                                'PurchaseFairMarketValue': '$150.00'
                            }
                        }
                    ]
                }
            ]
        }

        input_file = os.path.join(tmpdir, 'schwab_input.json')
        output_file = os.path.join(tmpdir, 'output.json')

        with open(input_file, 'w') as f:
            json.dump(input_data, f)

        runner = CliRunner()
        result = runner.invoke(
            capgains, ['convert', 'schwab-eac', input_file, output_file]
        )

        assert result.exit_code == 0
        assert os.path.exists(output_file)

    def test_cli_convert_with_ticker_filter(self, tmpdir):
        """Test the convert schwab-eac CLI command with ticker filter."""
        input_data = {
            'Transactions': [
                {
                    'Date': '01/15/2024',
                    'Action': 'Deposit',
                    'Symbol': 'AAPL',
                    'Description': 'ESPP',
                    'Quantity': '10',
                    'TransactionDetails': [
                        {
                            'Details': {
                                'PurchaseFairMarketValue': '$150.00'
                            }
                        }
                    ]
                },
                {
                    'Date': '01/15/2024',
                    'Action': 'Deposit',
                    'Symbol': 'GOOGL',
                    'Description': 'RS',
                    'Quantity': '5',
                    'TransactionDetails': [
                        {
                            'Details': {
                                'VestFairMarketValue': '$175.00'
                            }
                        }
                    ]
                }
            ]
        }

        input_file = os.path.join(tmpdir, 'schwab_input.json')
        output_file = os.path.join(tmpdir, 'output.json')

        with open(input_file, 'w') as f:
            json.dump(input_data, f)

        runner = CliRunner()
        result = runner.invoke(
            capgains,
            ['convert', 'schwab-eac', input_file, output_file, '-t', 'AAPL']
        )

        assert result.exit_code == 0

        with open(output_file, 'r') as f:
            output_data = json.load(f)

        assert len(output_data) == 1
        assert output_data[0]['ticker'] == 'AAPL'
