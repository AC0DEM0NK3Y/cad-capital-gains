import click

from capgains.commands.capgains_show import capgains_show
from capgains.commands.capgains_calc import capgains_calc
from capgains.commands.capgains_maxcost import capgains_maxcost
from capgains.commands.capgains_convert import capgains_convert_schwab
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


if __name__ == '__main__':
    capgains()
