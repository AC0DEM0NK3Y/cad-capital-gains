"""
Test TD Direct Investing PDF statement converter functionality.

These tests verify that the TD statements PDF converter correctly extracts
transactions from TD Direct Investing statements and trade confirmations.
"""

import os
import json
import pytest
from click.testing import CliRunner
from capgains.cli import capgains
from capgains.converters.td_statements_pdf import convert_td_statements_directory


@pytest.fixture
def setup_sample_directory():
    """Set up sample directory for testing."""
    # Update this path to match where your sample files are located
    base_path = "tests/sample_data/TD"
    
    # Check if the directories exist
    statements_dir = os.path.join(base_path, "Statements")
    confirmations_dir = os.path.join(base_path, "Confirmations")
    
    statements_exist = os.path.isdir(statements_dir) and len(os.listdir(statements_dir)) > 0
    confirmations_exist = os.path.isdir(confirmations_dir) and len(os.listdir(confirmations_dir)) > 0
    
    return {
        'root': base_path,
        'statements': statements_dir if statements_exist else None,
        'confirmations': confirmations_dir if confirmations_exist else None
    }


def test_td_statements_pdf_converter_cli(setup_sample_directory, tmpdir):
    """Test the TD statements PDF converter CLI command."""
    
    # Skip if sample directories are not available
    dirs = setup_sample_directory
    if not dirs['statements'] or not dirs['confirmations']:
        pytest.skip("Missing required sample directories")
    
    # Create temporary output file
    output_file = os.path.join(tmpdir, "td_output.json")
    
    # Run the converter command
    runner = CliRunner()
    result = runner.invoke(
        capgains, [
            'convert', 'td-statements-pdf',
            dirs['statements'], 
            dirs['confirmations'],
            output_file
        ]
    )
    
    # Check that command was successful
    assert result.exit_code == 0, f"Command failed with output: {result.output}"
    
    # Verify output file was created
    assert os.path.exists(output_file), "Output file was not created"
    
    # Load the output and verify it has the expected format
    with open(output_file, 'r') as f:
        data = json.load(f)
    
    # Basic validation of output
    assert isinstance(data, list), "Output should be a list of transactions"
    assert len(data) > 0, "Output should contain at least one transaction"
    
    # Verify transaction structure for first transaction
    tx = data[0]
    required_fields = ['date', 'ticker', 'action', 'qty', 'price', 'commission', 'currency', 'description']
    for field in required_fields:
        assert field in tx, f"Transaction missing required field: {field}"


def test_td_converter_norberts_gambit_detection(setup_sample_directory, tmpdir):
    """Test that the TD converter correctly identifies Norbert's Gambit transactions."""
    
    # Skip if sample directories are not available
    dirs = setup_sample_directory
    if not dirs['statements'] or not dirs['confirmations']:
        pytest.skip("Missing required sample directories")
    
    # Create temporary output file
    output_file = os.path.join(tmpdir, "td_output.json")
    
    # Run the converter command
    runner = CliRunner()
    result = runner.invoke(
        capgains, [
            'convert', 'td-statements-pdf',
            dirs['statements'], 
            dirs['confirmations'],
            output_file
        ]
    )
    
    # Check that command was successful
    assert result.exit_code == 0
    
    # Load the output
    with open(output_file, 'r') as f:
        transactions = json.load(f)
    
    # Look for Norbert's Gambit related transactions
    dlr_transactions = [tx for tx in transactions if tx.get('ticker') == 'DLR']
    
    # There should be some DLR transactions
    assert len(dlr_transactions) > 0, "No DLR transactions found"
    
    # Check for the different transaction types in a Norbert's Gambit sequence
    actions = [tx.get('action') for tx in dlr_transactions]
    
    # Should find BUY, SELL, JOURNAL_IN, and JOURNAL_OUT actions
    assert 'BUY' in actions, "No DLR buy transactions found"
    assert 'SELL' in actions, "No DLR sell transactions found"
    assert 'JOURNAL_IN' in actions, "No DLR journal in transactions found"
    assert 'JOURNAL_OUT' in actions, "No DLR journal out transactions found"
    
    # Verify journal transactions have zero price and commission
    journal_txs = [tx for tx in dlr_transactions if 'JOURNAL' in tx.get('action', '')]
    for tx in journal_txs:
        assert tx.get('price') == 0, "Journal transaction should have zero price"
        assert tx.get('commission') == 0, "Journal transaction should have zero commission"


def test_td_converter_transaction_matching(setup_sample_directory, tmpdir):
    """Test that the TD converter correctly matches related transactions."""
    # Skip if sample directories are not available
    dirs = setup_sample_directory
    if not dirs['statements'] or not dirs['confirmations']:
        pytest.skip("Missing required sample directories")
    
    # Convert the TD statements and confirmations to JSON format
    output_path = os.path.join(tmpdir, "transactions.json")
    
    # Run the converter
    convert_td_statements_directory(
        dirs['statements'],
        dirs['confirmations'],
        output_path
    )
    
    # Load the output file
    with open(output_path, 'r') as f:
        transactions = json.load(f)
        
    assert len(transactions) > 0, "No transactions were output by the converter"
    
    # Check that we have both CAD and USD transactions
    currencies = set(tx.get('currency', '') for tx in transactions)
    assert 'CAD' in currencies, "Missing CAD transactions"
    assert 'USD' in currencies, "Missing USD transactions"
    
    # Check that we have all required actions
    actions = set(tx.get('action', '') for tx in transactions)
    print(f"Found actions: {actions}")
    
    # Make sure we have at least BUY or SELL actions
    has_trades = 'BUY' in actions or 'SELL' in actions
    assert has_trades, "No BUY or SELL actions found in transactions"
    
    # Verify description format matches our expectations
    for tx in transactions:
        if 'action' in tx and tx['action'] in ['BUY', 'SELL']:
            assert 'TD Trade' in tx.get('description', ''), f"Invalid description format: {tx.get('description', '')}"
        elif 'action' in tx and 'JOURNAL' in tx['action']:
            assert 'TD Journal' in tx.get('description', ''), f"Invalid description format: {tx.get('description', '')}"


def test_td_converter_output_format(setup_sample_directory, tmpdir):
    """Test that the TD converter produces output in the format expected by the calculator."""
    
    # Skip if sample directories are not available
    dirs = setup_sample_directory
    if not dirs['statements'] or not dirs['confirmations']:
        pytest.skip("Missing required sample directories")
    
    # Convert the TD statements and confirmations to JSON format
    converter_output = os.path.join(tmpdir, "transactions.json")
    
    # Run the converter
    convert_td_statements_directory(
        dirs['statements'],
        dirs['confirmations'],
        converter_output
    )
    
    # Check the output file exists and is not empty
    assert os.path.exists(converter_output), f"Output file {converter_output} does not exist"
    assert os.path.getsize(converter_output) > 0, f"Output file {converter_output} is empty"
    
    # Load the output file
    with open(converter_output, 'r') as f:
        transactions = json.load(f)
    
    # Verify the output file contains transactions
    assert len(transactions) > 0, "No transactions found in output"
    
    # Check that each transaction has the required fields
    required_fields = ['date', 'ticker', 'action', 'qty', 'price', 'commission', 'currency', 'description']
    for tx in transactions:
        for field in required_fields:
            assert field in tx, f"Missing required field '{field}' in transaction: {json.dumps(tx)}"
    
    # Now try using the converted data with the calculator
    runner = CliRunner()
    calc_result = runner.invoke(
        capgains, [
            'calc', 
            converter_output,
            '2024',  # Use 2024 as the tax year
            '--format', 'json'
        ]
    )
    
    # The calculation should succeed with the converted data
    assert calc_result.exit_code == 0, f"Calculation failed: {calc_result.output}"
    
    # Extract the JSON data from the output
    calc_data = json.loads(calc_result.output)
    
    # There should be results for at least one ticker
    assert len(calc_data) > 0, "No results returned from calculator" 