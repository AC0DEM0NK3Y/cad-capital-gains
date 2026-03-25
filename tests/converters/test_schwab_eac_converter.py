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

    def test_convert_espp_deposit_with_tax_withholding(self):
        """Test ESPP deposit uses NetSharesDeposited when shares are
        withheld for taxes, matching how RS deposits report net shares."""
        tx = {
            'Date': '03/15/2024',
            'Action': 'Deposit',
            'Symbol': 'ACME',
            'Description': 'ESPP',
            'Quantity': '23',
            'TransactionDetails': [
                {
                    'Details': {
                        'PurchaseDate': '03/15/2024',
                        'PurchasePrice': '$95.00',
                        'SubscriptionDate': '01/15/2024',
                        'SubscriptionFairMarketValue': '$120.00',
                        'PurchaseFairMarketValue': '$200.00',
                        'TaxWithholdingMethod': 'Withhold for Taxes',
                        'NetSharesDeposited': '18',
                        'SharesWithheld': '5',
                        'SharesSold': '',
                        'CashRefund': '',
                        'CarryForward': '$85.00'
                    }
                }
            ]
        }

        result = convert_schwab_transaction(tx)

        assert result is not None
        assert result['date'] == '2024-03-15'
        assert result['ticker'] == 'ACME'
        assert result['action'] == 'BUY'
        # Should use NetSharesDeposited (18), not Quantity (23)
        assert result['qty'] == 18.0
        assert result['price'] == 200.00
        assert result['commission'] == 0.0
        assert result['currency'] == 'USD'
        assert result['description'] == 'ESPP'

    def test_convert_espp_deposit_old_format_null_withholding(self):
        """Test old ESPP format where TaxWithholdingMethod is null and
        NetSharesDeposited has no value. Quantity is already the net
        deposited amount — the user sold shares separately."""
        tx = {
            'Date': '06/01/2023',
            'Action': 'Deposit',
            'Symbol': 'ACME',
            'Description': 'ESPP',
            'Quantity': '15',
            'TransactionDetails': [
                {
                    'Details': {
                        'PurchaseDate': '06/01/2023',
                        'PurchasePrice': '$80.00',
                        'SubscriptionDate': '12/01/2022',
                        'SubscriptionFairMarketValue': '$90.00',
                        'PurchaseFairMarketValue': '$120.00',
                        'TaxWithholdingMethod': None,
                        'NetSharesDeposited': '',
                        'SharesWithheld': '',
                        'SharesSold': '',
                        'CashRefund': '',
                        'CarryForward': ''
                    }
                }
            ]
        }

        result = convert_schwab_transaction(tx)

        assert result is not None
        # Should use Quantity (15) since NetSharesDeposited is empty
        assert result['qty'] == 15.0
        assert result['price'] == 120.0
        assert result['description'] == 'ESPP'

    def test_convert_espp_deposit_without_net_shares_key(self):
        """Test ESPP deposit falls back to Quantity when
        NetSharesDeposited key is not present at all (minimal details)."""
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
        assert result['qty'] == 10.0
        assert result['price'] == 150.0

    def test_convert_espp_error_withhold_missing_net_shares(self):
        """Error when TaxWithholdingMethod is 'Withhold for Taxes' but
        NetSharesDeposited is missing."""
        tx = {
            'Date': '03/15/2024',
            'Action': 'Deposit',
            'Symbol': 'ACME',
            'Description': 'ESPP',
            'Quantity': '23',
            'TransactionDetails': [
                {
                    'Details': {
                        'PurchaseFairMarketValue': '$200.00',
                        'TaxWithholdingMethod': 'Withhold for Taxes',
                        'NetSharesDeposited': '',
                        'SharesWithheld': '5'
                    }
                }
            ]
        }

        with pytest.raises(ValueError, match="NetSharesDeposited is missing"):
            convert_schwab_transaction(tx)

    def test_convert_espp_error_unknown_withholding_method(self):
        """Error when TaxWithholdingMethod is an unexpected value."""
        tx = {
            'Date': '03/15/2024',
            'Action': 'Deposit',
            'Symbol': 'ACME',
            'Description': 'ESPP',
            'Quantity': '23',
            'TransactionDetails': [
                {
                    'Details': {
                        'PurchaseFairMarketValue': '$200.00',
                        'TaxWithholdingMethod': 'Some New Method',
                        'NetSharesDeposited': '18'
                    }
                }
            ]
        }

        with pytest.raises(
            ValueError, match="unexpected TaxWithholdingMethod"
        ):
            convert_schwab_transaction(tx)

    def test_convert_espp_error_null_withhold_mismatched_net_shares(self):
        """Error when TaxWithholdingMethod is null but NetSharesDeposited
        has a value different from Quantity."""
        tx = {
            'Date': '03/15/2024',
            'Action': 'Deposit',
            'Symbol': 'ACME',
            'Description': 'ESPP',
            'Quantity': '15',
            'TransactionDetails': [
                {
                    'Details': {
                        'PurchaseFairMarketValue': '$200.00',
                        'TaxWithholdingMethod': None,
                        'NetSharesDeposited': '10'
                    }
                }
            ]
        }

        with pytest.raises(ValueError, match="differs from Quantity"):
            convert_schwab_transaction(tx)

    def test_convert_espp_null_withhold_matching_net_shares_ok(self):
        """No error when TaxWithholdingMethod is null and
        NetSharesDeposited matches Quantity."""
        tx = {
            'Date': '03/15/2024',
            'Action': 'Deposit',
            'Symbol': 'ACME',
            'Description': 'ESPP',
            'Quantity': '15',
            'TransactionDetails': [
                {
                    'Details': {
                        'PurchaseFairMarketValue': '$200.00',
                        'TaxWithholdingMethod': None,
                        'NetSharesDeposited': '15'
                    }
                }
            ]
        }

        result = convert_schwab_transaction(tx)
        assert result is not None
        assert result['qty'] == 15.0

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

    def test_convert_file_espp_with_tax_withholding(self, tmpdir):
        """Test full file conversion uses net shares for ESPP with
        tax withholding."""
        input_data = {
            'Transactions': [
                {
                    'Date': '03/15/2024',
                    'Action': 'Deposit',
                    'Symbol': 'ACME',
                    'Description': 'ESPP',
                    'Quantity': '23',
                    'TransactionDetails': [
                        {
                            'Details': {
                                'PurchaseDate': '03/15/2024',
                                'PurchasePrice': '$95.00',
                                'SubscriptionDate': '01/15/2024',
                                'SubscriptionFairMarketValue': '$120.00',
                                'PurchaseFairMarketValue': '$200.00',
                                'TaxWithholdingMethod': 'Withhold for Taxes',
                                'NetSharesDeposited': '18',
                                'SharesWithheld': '5',
                                'SharesSold': '',
                                'CashRefund': '',
                                'CarryForward': '$85.00'
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

        with open(output_file, 'r') as f:
            output_data = json.load(f)

        assert len(output_data) == 1
        assert output_data[0]['qty'] == 18.0
        assert output_data[0]['price'] == 200.00
        assert output_data[0]['ticker'] == 'ACME'

    def test_convert_file_mixed_espp_and_rsu_vests(self, tmpdir):
        """Test file with both ESPP (tax withholding) and RS deposits
        correctly uses net shares for each."""
        input_data = {
            'Transactions': [
                {
                    'Date': '03/15/2024',
                    'Action': 'Deposit',
                    'Symbol': 'ACME',
                    'Description': 'ESPP',
                    'Quantity': '23',
                    'TransactionDetails': [
                        {
                            'Details': {
                                'PurchaseFairMarketValue': '$200.00',
                                'TaxWithholdingMethod': 'Withhold for Taxes',
                                'NetSharesDeposited': '18',
                                'SharesWithheld': '5'
                            }
                        }
                    ]
                },
                {
                    'Date': '06/15/2024',
                    'Action': 'Deposit',
                    'Symbol': 'ACME',
                    'Description': 'RS',
                    'Quantity': '16',
                    'TransactionDetails': [
                        {
                            'Details': {
                                'VestFairMarketValue': '$210.50'
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

        with open(output_file, 'r') as f:
            output_data = json.load(f)

        assert len(output_data) == 2
        # ESPP sorted before RS on same date, but these are different dates
        espp = next(t for t in output_data if t['description'] == 'ESPP')
        rsu = next(t for t in output_data if t['description'] == 'RS')
        assert espp['qty'] == 18.0  # net, not 23
        assert rsu['qty'] == 16.0   # already net in Quantity

    def test_convert_file_espp_old_and_new_format(self, tmpdir):
        """Test file with both old ESPP (null withholding, Quantity is net)
        and new ESPP (Withhold for Taxes, NetSharesDeposited is net)."""
        input_data = {
            'Transactions': [
                {
                    'Date': '06/01/2023',
                    'Action': 'Deposit',
                    'Symbol': 'ACME',
                    'Description': 'ESPP',
                    'Quantity': '15',
                    'TransactionDetails': [
                        {
                            'Details': {
                                'PurchaseFairMarketValue': '$120.00',
                                'TaxWithholdingMethod': None,
                                'NetSharesDeposited': '',
                                'SharesWithheld': ''
                            }
                        }
                    ]
                },
                {
                    'Date': '03/15/2024',
                    'Action': 'Deposit',
                    'Symbol': 'ACME',
                    'Description': 'ESPP',
                    'Quantity': '23',
                    'TransactionDetails': [
                        {
                            'Details': {
                                'PurchaseFairMarketValue': '$200.00',
                                'TaxWithholdingMethod': 'Withhold for Taxes',
                                'NetSharesDeposited': '18',
                                'SharesWithheld': '5'
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

        with open(output_file, 'r') as f:
            output_data = json.load(f)

        assert len(output_data) == 2
        # Old format: Quantity (15) used as-is
        assert output_data[0]['qty'] == 15.0
        assert output_data[0]['date'] == '2023-06-01'
        # New format: NetSharesDeposited (18) used instead of Quantity (23)
        assert output_data[1]['qty'] == 18.0
        assert output_data[1]['date'] == '2024-03-15'

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

    def test_cli_convert_espp_with_tax_withholding(self, tmpdir):
        """Test CLI correctly converts ESPP with tax withholding to
        net shares."""
        input_data = {
            'Transactions': [
                {
                    'Date': '03/15/2024',
                    'Action': 'Deposit',
                    'Symbol': 'ACME',
                    'Description': 'ESPP',
                    'Quantity': '23',
                    'TransactionDetails': [
                        {
                            'Details': {
                                'PurchaseFairMarketValue': '$200.00',
                                'TaxWithholdingMethod': 'Withhold for Taxes',
                                'NetSharesDeposited': '18',
                                'SharesWithheld': '5'
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

        with open(output_file, 'r') as f:
            output_data = json.load(f)

        assert len(output_data) == 1
        assert output_data[0]['qty'] == 18.0
        assert output_data[0]['price'] == 200.00

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


class TestEsppAcbExpectations:
    """Tests that converted ESPP transactions produce correct ACB.
    Verifies that using net shares (after tax withholding) results in
    correct cost base for subsequent capital gains calculations."""

    def _convert(self, tmpdir, schwab_transactions):
        """Helper: convert Schwab JSON and return converted list."""
        input_data = {'Transactions': schwab_transactions}
        input_file = os.path.join(tmpdir, 'schwab_input.json')
        converted_file = os.path.join(tmpdir, 'converted.json')

        with open(input_file, 'w') as f:
            json.dump(input_data, f)

        convert_schwab_file(input_file, converted_file)

        with open(converted_file, 'r') as f:
            return json.load(f)

    def test_espp_withholding_acb_uses_net_shares(self, tmpdir):
        """ESPP with tax withholding: ACB = net shares * FMV.
        Buy 23 gross, 5 withheld, 18 net deposited @ $200 FMV.
        ACB should be 18 * $200 = $3,600 USD, not 23 * $200."""
        converted = self._convert(tmpdir, [
            {
                'Date': '03/15/2024',
                'Action': 'Deposit',
                'Symbol': 'ACME',
                'Description': 'ESPP',
                'Quantity': '23',
                'TransactionDetails': [{
                    'Details': {
                        'PurchaseFairMarketValue': '$200.00',
                        'TaxWithholdingMethod': 'Withhold for Taxes',
                        'NetSharesDeposited': '18',
                        'SharesWithheld': '5'
                    }
                }]
            }
        ])

        assert len(converted) == 1
        assert converted[0]['qty'] == 18.0
        assert converted[0]['price'] == 200.0
        # ACB = qty * price = 18 * 200 = 3600
        expected_acb = 18.0 * 200.0
        actual_acb = converted[0]['qty'] * converted[0]['price']
        assert actual_acb == expected_acb

    def test_espp_old_format_acb_uses_quantity(self, tmpdir):
        """Old ESPP (no withholding): ACB = Quantity * FMV.
        Buy 15 shares @ $120 FMV, no withholding.
        ACB should be 15 * $120 = $1,800 USD."""
        converted = self._convert(tmpdir, [
            {
                'Date': '06/01/2023',
                'Action': 'Deposit',
                'Symbol': 'ACME',
                'Description': 'ESPP',
                'Quantity': '15',
                'TransactionDetails': [{
                    'Details': {
                        'PurchaseFairMarketValue': '$120.00',
                        'TaxWithholdingMethod': None,
                        'NetSharesDeposited': '',
                        'SharesWithheld': ''
                    }
                }]
            }
        ])

        assert len(converted) == 1
        assert converted[0]['qty'] == 15.0
        assert converted[0]['price'] == 120.0
        expected_acb = 15.0 * 120.0
        actual_acb = converted[0]['qty'] * converted[0]['price']
        assert actual_acb == expected_acb

    def test_espp_mixed_formats_combined_acb(self, tmpdir):
        """Mixed old and new ESPP formats produce correct combined ACB.
        Old: 15 shares @ $120 = $1,800
        New: 18 net shares @ $200 = $3,600
        Total ACB = $5,400 for 33 shares, avg = $163.64/share."""
        converted = self._convert(tmpdir, [
            {
                'Date': '06/01/2023',
                'Action': 'Deposit',
                'Symbol': 'ACME',
                'Description': 'ESPP',
                'Quantity': '15',
                'TransactionDetails': [{
                    'Details': {
                        'PurchaseFairMarketValue': '$120.00',
                        'TaxWithholdingMethod': None,
                        'NetSharesDeposited': '',
                        'SharesWithheld': ''
                    }
                }]
            },
            {
                'Date': '03/15/2024',
                'Action': 'Deposit',
                'Symbol': 'ACME',
                'Description': 'ESPP',
                'Quantity': '23',
                'TransactionDetails': [{
                    'Details': {
                        'PurchaseFairMarketValue': '$200.00',
                        'TaxWithholdingMethod': 'Withhold for Taxes',
                        'NetSharesDeposited': '18',
                        'SharesWithheld': '5'
                    }
                }]
            }
        ])

        assert len(converted) == 2
        total_shares = sum(t['qty'] for t in converted)
        total_acb = sum(t['qty'] * t['price'] for t in converted)
        assert total_shares == 33.0
        assert total_acb == 5400.0
        assert total_acb / total_shares == pytest.approx(163.636, rel=1e-2)
