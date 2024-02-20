"""
Converter for Schwab Equity Awards Center (EAC) transaction data.
This module handles ESPP, RS (Restricted Stock), and Share Sale transactions.
"""

import json
import sys
from datetime import datetime
from decimal import Decimal


def convert_schwab_date(date_str):
    """Convert date from MM/DD/YYYY to YYYY-MM-DD format."""
    return datetime.strptime(date_str, '%m/%d/%Y').strftime('%Y-%m-%d')


def convert_schwab_amount(amount_str):
    """Convert amount string like '$123.45' or '-$123.45' to decimal."""
    if not amount_str:
        return Decimal('0')
    # Remove $ and any commas
    amount_str = amount_str.replace('$', '').replace(',', '')
    return Decimal(amount_str)


def convert_schwab_transaction(tx, tickers=None):
    """Convert a single Schwab transaction to cad-capital-gains format.

    Args:
        tx: Transaction data from Schwab EAC JSON
        tickers: Optional list of tickers to filter by
    """
    # Skip transactions that don't affect capital gains
    if tx['Action'] in ['Tax Withholding', 'Dividend', 'Transfer']:
        return None

    # Skip transactions for other tickers if filtering is enabled
    if tickers and tx['Symbol'] not in tickers:
        return None

    # Determine if this is a buy or sell
    action = None
    if tx['Action'] == 'Deposit':
        action = 'BUY'
    elif tx['Action'] == 'Sale':
        action = 'SELL'
    else:
        return None  # Skip other transaction types

    # Get quantity and price
    quantity = Decimal(tx['Quantity']) if tx['Quantity'] else Decimal('0')

    # For sales, get price from TransactionDetails
    price = Decimal('0')
    if tx['TransactionDetails']:
        for detail in tx['TransactionDetails']:
            if 'Details' not in detail:
                continue

            details = detail['Details']

            # For sales
            if tx['Action'] == 'Sale' and 'SalePrice' in details:
                sale_price = details['SalePrice']
                if sale_price:
                    price = convert_schwab_amount(sale_price)
                    break

            # For ESPP deposits
            elif (tx['Description'] == 'ESPP'
                  and 'PurchaseFairMarketValue' in details):
                fair_market_value = details['PurchaseFairMarketValue']
                if fair_market_value:
                    price = convert_schwab_amount(fair_market_value)
                    break

            # For RSU deposits
            elif 'VestFairMarketValue' in details:
                vest_price = details['VestFairMarketValue']
                if vest_price:
                    price = convert_schwab_amount(vest_price)
                    break

    # For consistency with manual data, set commission to 0
    commission = Decimal('0')

    # Clean up description
    description = tx['Description']
    if description == 'Share Sale':
        description = 'Share Sale'
    elif description == 'RS':
        description = 'RS'
    elif description == 'ESPP':
        description = 'ESPP'

    # Convert Decimal objects to float for JSON serialization
    return {
        'date': convert_schwab_date(tx['Date']),
        'description': description,
        'ticker': tx['Symbol'],
        'action': action,
        'qty': float(quantity),
        'price': float(price),
        'commission': float(commission),
        'currency': 'USD'.strip()  # Remove any extra spaces
    }


def group_and_sort_transactions(transactions):
    """Group transactions by date and sort within each date."""
    # Group transactions by date
    grouped = {}
    for tx in transactions:
        date = tx['date']
        if date not in grouped:
            grouped[date] = []
        grouped[date].append(tx)

    # Sort transactions within each date
    for date, txs in grouped.items():
        # Sort by:
        # 1. Description (ESPP first, then RS, then Share Sale)
        # 2. Action (BUY, then SELL)
        desc_order = {'ESPP': 0, 'RS': 1, 'Share Sale': 2}
        action_order = {'BUY': 0, 'SELL': 1}

        txs.sort(
            key=lambda x:
            (desc_order[x['description']], action_order[x['action']])
        )

    # Flatten back to list
    sorted_transactions = []
    for date in sorted(grouped.keys()):
        sorted_transactions.extend(grouped[date])

    return sorted_transactions


def convert_schwab_file(input_file, output_file, tickers=None):
    """Convert Schwab equity awards JSON file to cad-capital-gains format.

    Args:
        input_file: Path to Schwab EAC JSON file
        output_file: Path to write converted JSON file
        tickers: Optional list of tickers to filter by
    """
    try:
        # Read input file
        with open(input_file, 'r') as f:
            schwab_data = json.load(f)

        # Convert transactions
        converted_transactions = []
        for tx in schwab_data['Transactions']:
            converted_tx = convert_schwab_transaction(tx, tickers=tickers)
            if converted_tx:
                converted_transactions.append(converted_tx)

        # Sort and group transactions
        converted_transactions = group_and_sort_transactions(
            converted_transactions
        )

        # Write output file
        with open(output_file, 'w') as f:
            json.dump(converted_transactions, f, indent=2)

        print(
            f"Successfully converted {len(converted_transactions)} "
            "transactions"
        )

    except FileNotFoundError:
        print(f"Error: Couldn't find input file {input_file}", file=sys.stderr)
        raise
    except json.JSONDecodeError:
        print(f"Error: {input_file} is not a valid JSON file", file=sys.stderr)
        raise
    except KeyError as e:
        print(
            f"Error: Input file is missing required field {e}",
            file=sys.stderr
        )
        raise
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        raise
