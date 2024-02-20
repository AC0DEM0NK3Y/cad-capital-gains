import click

from capgains.commands.capgains_show import capgains_show
from capgains.commands.capgains_calc import capgains_calc
from capgains.commands.capgains_maxcost import capgains_maxcost
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
        "Filters can be applied to select which stocks to calculate the "
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
        "Calculates maximum costs from the transactions file for T1135 "
        "reporting. Supports both CSV and JSON input files. "
        "By default, assumes a Canadian broker and only counts foreign "
        "securities (USD stocks) toward T1135. Use --foreign-broker to "
        "include CAD securities when your account is held outside Canada."
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
@click.option(
    '--foreign-broker',
    is_flag=True,
    help=(
        "Include CAD securities in T1135 calculation. Use this flag if your "
        "securities are held at a broker outside Canada, since all securities "
        "held outside Canada are specified foreign property."
    )
)
def maxcost(transactions_file, year, tickers, format, foreign_broker):
    transactions = TransactionsReader.get_transactions(transactions_file)
    capgains_maxcost(
        transactions,
        year,
        tickers=tickers,
        output_format=format,
        foreign_broker=foreign_broker
    )


if __name__ == '__main__':
    capgains()
