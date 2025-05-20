"""
Converter for TD Direct Investing trade confirmations from PDF format.
This module handles trade confirmation PDFs from TD Direct Investing.
"""

import sys
import json
import re
from datetime import datetime
from decimal import Decimal
import pdfplumber
from click import ClickException


def extract_date(text, prefix):
    """Extract date from text using prefix."""
    # Try different date formats
    patterns = [
        # "Transaction on February 23, 2024"
        f"{prefix}\\s*on\\s*([A-Za-z]+\\s+\\d+,\\s+\\d{{4}})",
        # "For settlement on: February 26, 2024"
        f"{prefix}\\s*on:\\s*[A-Za-z]\\s*([A-Za-z]+\\s+\\d+,\\s+\\d{{4}})",
        # Just the date part
        f"{prefix}\\s*([A-Za-z]+\\s+\\d+,\\s+\\d{{4}})"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            try:
                return datetime.strptime(date_str, "%B %d, %Y")
            except ValueError:
                continue
    return None


def extract_amount(text, prefix):
    """Extract amount from text using prefix."""
    pattern = f"{prefix}\\s*(?:USD)?\\s*\\$?(\\d+(?:,\\d{3})*\\.\\d{2})"
    match = re.search(pattern, text)
    if match:
        amount_str = match.group(1).replace(",", "")
        return Decimal(amount_str)
    return None


def extract_quantity(text):
    """Extract quantity from text."""
    pattern = r"(?:You bought|You sold)\s+[^0-9\n]+\s+([0-9,]+(?:\.[0-9]*)?)"
    match = re.search(pattern, text)
    if match:
        qty_str = match.group(1).replace(",", "")
        return Decimal(qty_str)
    return None


def extract_ticker(text):
    """Extract ticker symbol from text."""
    pattern = r"Ticker symbol:\s+([A-Z]+(?:\.[A-Z]+)?)"
    match = re.search(pattern, text)
    if match:
        return match.group(1)
    return None


def extract_security_name(text):
    """Extract security name from text."""
    pattern = r"(?:You bought|You sold)\s+([^0-9\n]+?)\s+(?:\d|$)"
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    return None


def extract_action(text):
    """Extract trade action (BUY/SELL) from text."""
    if re.search(r"You bought", text, re.IGNORECASE):
        return "BUY"
    elif re.search(r"You sold", text, re.IGNORECASE):
        return "SELL"
    return None


def extract_currency(text):
    """Extract currency from text."""
    if "USD" in text:
        return "USD"
    return "CAD"  # Default to CAD if not specified


def extract_price(text):
    """Extract price from text."""
    pattern = r"(?:You bought|You sold)[^0-9]+\d+(?:,\d{3})*(?:\.\d*)?\s+(\d+\.\d+)"
    match = re.search(pattern, text)
    if match:
        return Decimal(match.group(1))
    return None


def extract_commission(text):
    """Extract commission from text."""
    patterns = [
        r"Commission(?:CAD|USD)?\s*-?\s*(\d+\.\d{2})",  # Matches "CommissionCAD -9.99" or "CommissionCAD 9.99"
        r"Plus Commission\s*-?\s*(\d+\.\d{2})",  # Old format
        r"Commission:\s*-?\s*(\d+\.\d{2})"  # Another possible format
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            # Always return commission as positive since it's a cost
            return abs(Decimal(match.group(1)))
    
    return Decimal('0.00')  # Return 0 if no commission found


def parse_trade_confirmation(text):
    """Parse a single trade confirmation section.
    
    Args:
        text: Text content of a single trade confirmation
        
    Returns:
        Dictionary containing trade information or None if not a valid trade
    """
    try:
        # Skip if this doesn't look like a trade confirmation
        if not any(keyword in text for keyword in ["You bought", "You sold"]):
            print("No BUY/SELL keywords found in section", file=sys.stderr)
            return None

        trade = {
            'date': extract_date(text, "Transaction"),
            'settlement_date': extract_date(text, "settlement"),
            'action': extract_action(text),
            'security_name': extract_security_name(text),
            'ticker': extract_ticker(text),
            'quantity': extract_quantity(text),
            'price': extract_price(text),
            'commission': extract_commission(text),
            'currency': extract_currency(text),
            'total_amount': extract_amount(text, "Gross transaction amount")
        }

        # Debug: Print extracted fields
        print("Extracted fields:", file=sys.stderr)
        for field, value in trade.items():
            print(f"{field}: {value}", file=sys.stderr)
        print("-" * 80, file=sys.stderr)

        # Validate required fields
        required_fields = ['date', 'action', 'security_name', 'ticker', 'quantity', 'price']
        missing_fields = [field for field in required_fields if not trade[field]]
        
        if missing_fields:
            print(
                f"Warning: Missing required fields: {', '.join(missing_fields)}",
                file=sys.stderr
            )
            return None

        return trade

    except Exception as e:
        print(
            f"Warning: Could not parse trade confirmation: {str(e)}",
            file=sys.stderr
        )
        return None


def extract_trades_from_pdf(pdf_path):
    """Extract trade information from TD trade confirmation PDF.
    
    Args:
        pdf_path: Path to the PDF file containing trade confirmations
        
    Returns:
        List of dictionaries containing trade information
    """
    trades = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if not text:
                    print(f"No text found on page {page_num}", file=sys.stderr)
                    continue

                print(f"Processing page {page_num}", file=sys.stderr)
                
                # Each page is a separate trade confirmation
                trade = parse_trade_confirmation(text)
                if trade:
                    trades.append(trade)
                    print(f"Successfully parsed trade from page {page_num}", file=sys.stderr)

        return trades

    except Exception as e:
        raise ClickException(f"Error reading PDF file: {str(e)}")


def convert_trade_to_transaction(trade):
    """Convert a trade dictionary to cad-capital-gains transaction format.
    
    Args:
        trade: Dictionary containing trade information
        
    Returns:
        Dictionary in cad-capital-gains transaction format
    """
    try:
        return {
            'date': trade['date'].strftime('%Y-%m-%d'),
            'description': f"TD Trade - {trade['security_name']}",
            'ticker': trade['ticker'],
            'action': trade['action'],
            'qty': float(trade['quantity']),
            'price': float(trade['price']),
            'commission': float(trade['commission']),
            'currency': trade['currency']
        }
    except Exception as e:
        raise ClickException(
            f"Error converting trade to transaction: {str(e)}"
        )


def convert_td_trades_file(input_file, output_file):
    """Convert TD trade confirmation PDF to cad-capital-gains format.
    
    Args:
        input_file: Path to TD trade confirmation PDF
        output_file: Path to write converted JSON file
    """
    try:
        # Extract trades from PDF
        trades = extract_trades_from_pdf(input_file)

        if not trades:
            raise ClickException("No valid trades found in PDF file")

        # Convert to transactions
        transactions = []
        for trade in trades:
            transaction = convert_trade_to_transaction(trade)
            if transaction:
                transactions.append(transaction)

        # Sort by date
        transactions.sort(key=lambda x: x['date'])

        # Write output file
        with open(output_file, 'w') as f:
            json.dump(transactions, f, indent=2)

        print(f"Successfully converted {len(transactions)} transactions")

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        raise
