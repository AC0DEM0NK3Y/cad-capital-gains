import click

from capgains.commands.capgains_show import capgains_show
from capgains.commands.capgains_calc import capgains_calc
from capgains.commands.capgains_maxcost import capgains_maxcost
from capgains.commands.capgains_convert import (
    capgains_convert_schwab, capgains_convert_td_trades_pdf,
    capgains_convert_td_statements_pdf
)
from capgains.transactions_reader import TransactionsReader


@click.group()
def capgains():
    pass


@capgains.command(
    help=(
        "Show entries from the transactions file in a tabular format. "
        "Supports both CSV and JSON input files. "
        "Filters can be applied to narrow down the entries."
    )
)
@click.argument('transactions-file')
@click.option('-e', '--show-exchange-rate', is_flag=True)
@click.option(
    '-t',
    '--tickers',
    metavar='TICKERS',
    multiple=True,
    help="Stocks tickers to filter for"
)
@click.option(
    '--format',
    type=click.Choice(['table', 'json']),
    default='table',
    help="Output format (table or json)"
)
def show(transactions_file, show_exchange_rate, tickers, format):
    transactions = TransactionsReader.get_transactions(transactions_file)
    capgains_show(
        transactions,
        show_exchange_rate,
        tickers=tickers,
        output_format=format
    )


@capgains.command(
    help=(
        "Calculates capital gains from the transactions file. "
        "Supports both CSV and JSON input files. "
        "Filters can be applied to select which stocks to calculate "
        "capital gains on."
    )
)
@click.argument('transactions-file')
@click.argument('year', type=click.INT)
@click.option(
    '-t',
    '--tickers',
    metavar='TICKERS',
    multiple=True,
    help="Stocks tickers to filter for"
)
@click.option(
    '--format',
    type=click.Choice(['table', 'json']),
    default='table',
    help="Output format (table or json)"
)
def calc(transactions_file, year, tickers, format):
    transactions = TransactionsReader.get_transactions(transactions_file)
    capgains_calc(transactions, year, tickers=tickers, output_format=format)


@capgains.command(
    help=(
        "Calculates costs from the transactions file. "
        "Supports both CSV and JSON input files. "
        "Filters can be applied to select which stocks to calculate "
        "costs on."
    )
)
@click.argument('transactions-file')
@click.argument('year', type=click.INT)
@click.option(
    '-t',
    '--tickers',
    metavar='TICKERS',
    multiple=True,
    help="Stocks tickers to filter for"
)
@click.option(
    '--format',
    type=click.Choice(['table', 'json']),
    default='table',
    help="Output format (table or json)"
)
def maxcost(transactions_file, year, tickers, format):
    transactions = TransactionsReader.get_transactions(transactions_file)
    capgains_maxcost(transactions, year, tickers=tickers, output_format=format)


@capgains.group(
    help=(
        "Convert transaction data from various sources to cad-capital-gains format. "
        "Each source format has its own subcommand. The output is always a JSON file "
        "that can be used with other capgains commands."
    )
)
def convert():
    pass


@convert.command(
    'schwab-eac',
    short_help='Convert Schwab EAC transaction data to cad-capital-gains format',
    help=(
        'Convert Schwab Equity Awards Center (EAC) transaction data to cad-capital-gains format. '
        'Takes a Schwab EAC JSON file as input and outputs a JSON file in the format required '
        'by the other capgains commands. The input file should be downloaded from the Schwab '
        'EAC portal under "Transaction History". You can optionally filter for specific tickers.'
    )
)
@click.argument('input_file', type=click.Path(exists=True))
@click.argument('output_file', type=click.Path())
@click.option(
    '-t',
    '--tickers',
    multiple=True,
    help='Stock tickers to convert (can be specified multiple times)'
)
def convert_schwab_eac(input_file, output_file, tickers):
    """Convert Schwab equity awards JSON file to cad-capital-gains format."""
    capgains_convert_schwab(input_file, output_file, tickers=tickers)


@convert.command(
    'td-trades-pdf',
    short_help='Convert TD Direct Investing trade confirmation PDFs to cad-capital-gains format',
    help=(
        'Convert TD Direct Investing trade confirmation PDFs to cad-capital-gains format. '
        'Takes a PDF file containing one or more trade confirmations and outputs a JSON file '
        'in the format required by other capgains commands. The input file should be the trade '
        'confirmation PDF downloaded from TD Direct Investing WebBroker. The converter will '
        'extract all trades from the PDF, including the date, ticker, quantity, price, and '
        'commission. Both DLR and DLR.U trades are supported.'
    )
)
@click.argument('input_file', type=click.Path(exists=True))
@click.argument('output_file', type=click.Path())
def convert_td_trades_pdf(input_file, output_file):
    """Convert TD trade confirmation PDF to cad-capital-gains format."""
    capgains_convert_td_trades_pdf(input_file, output_file)


@convert.command(
    'td-statements-pdf',
    short_help='Convert TD Direct Investing statements and confirmations to cad-capital-gains format',
    help=(
        'Convert TD Direct Investing monthly statements and trade confirmations to cad-capital-gains format. '
        'Takes separate directories for statements and confirmations with PDF files downloaded from TD Direct '
        'Investing WebBroker. The converter will extract all transactions from the PDFs, including buys, sells, '
        'and journal transactions for Norbert\'s Gambit. It supports tracking the transfers between DLR.U and DLR '
        'automatically by cross-validating data from both statements and confirmations for accuracy.'
    )
)
@click.argument('statements-dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.argument('confirmations-dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.argument('output-file', type=click.Path())
@click.option(
    '--include-exchange-rate', is_flag=True,
    help='Include exchange rate in output (warning: may cause issues with other commands)'
)
@click.option(
    '--aliases-file', type=click.Path(exists=True),
    help='Path to a JSON file containing Norbert\'s Gambit securities aliases (e.g., norberts_gambit_aliases.json)'
)
def convert_td_statements_pdf(statements_dir, confirmations_dir, output_file, include_exchange_rate, aliases_file):
    """Convert TD statements and confirmations to cad-capital-gains format."""
    capgains_convert_td_statements_pdf(
        statement_dir=statements_dir,
        confirmation_dir=confirmations_dir,
        output_file=output_file,
        include_exchange_rate=include_exchange_rate,
        aliases_file=aliases_file
    )


@convert.command(
    'norberts-gambit',
    short_help='Convert Norbert\'s Gambit transactions to cad-capital-gains format',
    help=(
        'Convert Norbert\'s Gambit transactions to proper ACB format. '
        'Takes two JSON files as input: one containing the USD buy transactions '
        'and one containing the CAD sell transactions. Outputs a single JSON file '
        'that properly represents the trades for capital gains calculations. '
        'By default, assumes DLR.U for USD trades and DLR for CAD trades, but '
        'this can be customized using the --usd-ticker and --cad-ticker options.'
    )
)
@click.argument('usd_buys_file', type=click.Path(exists=True))
@click.argument('cad_sells_file', type=click.Path(exists=True))
@click.argument('output_file', type=click.Path())
@click.option(
    '--usd-ticker',
    default='DLR.U',
    help='Ticker symbol for the USD side of the gambit (default: DLR.U)'
)
@click.option(
    '--cad-ticker',
    default='DLR',
    help='Ticker symbol for the CAD side of the gambit (default: DLR)'
)
def convert_norberts_gambit(usd_buys_file, cad_sells_file, output_file, usd_ticker, cad_ticker):
    """Convert Norbert's Gambit transactions to proper ACB format."""
    import json
    from datetime import datetime

    # Read the input files
    with open(usd_buys_file, 'r') as f:
        usd_buys = json.load(f)
    with open(cad_sells_file, 'r') as f:
        cad_sells = json.load(f)

    # Create transactions list with both buys and sells
    transactions = []
    
    # Helper function to combine fills from same trade
    def combine_fills(trades):
        # Group by date to find fills from same trade
        trades_by_date = {}
        for trade in trades:
            date = trade['date']
            if date not in trades_by_date:
                trades_by_date[date] = []
            trades_by_date[date].append(trade)
        
        # Combine fills from same trade
        combined_trades = []
        for date, date_trades in trades_by_date.items():
            total_qty = sum(t['qty'] for t in date_trades)
            # Use the commission from the largest trade
            largest_trade = max(date_trades, key=lambda x: x['qty'])
            
            combined_trades.append({
                'date': date,
                'description': largest_trade['description'],
                'ticker': largest_trade['ticker'],
                'action': largest_trade['action'],
                'qty': total_qty,
                'price': largest_trade['price'],
                'commission': largest_trade['commission'],
                'currency': largest_trade['currency']
            })
        
        return combined_trades
    
    # Add all buy transactions (in USD)
    usd_trades = [
        trade for trade in usd_buys 
        if trade['ticker'] in [cad_ticker, usd_ticker]
    ]
    for buy in combine_fills(usd_trades):
        transactions.append({
            'date': buy['date'],
            'description': f'{usd_ticker} Buy - Norbert\'s Gambit',
            'ticker': cad_ticker,  # Use CAD ticker for consistency
            'action': 'BUY',
            'qty': buy['qty'],
            'price': buy['price'],
            'commission': buy['commission'],
            'currency': 'USD'
        })
    
    # Add all sell transactions (in CAD)
    cad_trades = [
        trade for trade in cad_sells 
        if trade['ticker'] == cad_ticker
    ]
    for sell in combine_fills(cad_trades):
        transactions.append({
            'date': sell['date'],
            'description': f'{cad_ticker} Sell - Norbert\'s Gambit',
            'ticker': cad_ticker,
            'action': 'SELL',
            'qty': sell['qty'],
            'price': sell['price'],
            'commission': sell['commission'],
            'currency': 'CAD'
        })

    # Sort by date
    transactions.sort(key=lambda x: x['date'])

    # Write output file
    with open(output_file, 'w') as f:
        json.dump(transactions, f, indent=2)

    print(f"Successfully converted {len(transactions)} transactions")


if __name__ == '__main__':
    capgains()
