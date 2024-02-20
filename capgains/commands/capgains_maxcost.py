import click
import json
from itertools import groupby

from capgains.exchange_rate import ExchangeRate
from capgains.ticker_gains import TickerGains

# T1135 reporting threshold in CAD
T1135_THRESHOLD = 100000

# describes how to align the individual table columns
colalign = (
    "left",  # ticker
    "right",  # max cost
    "right",  # year end
)


def _get_max_cost(transactions, year, year_min):
    transactions_to_report = transactions.filter_by(year=year)

    max_cost = 0
    for t in transactions_to_report:
        max_cost = max(max_cost, t.cumulative_cost)

    # check against end of last year
    max_cost = max(
        max_cost, _get_year_end_cost(transactions, year - 1, year_min)
    )  # noqa: E501

    return max_cost


def _get_year_end_cost(transactions, year, year_min):
    transactions_to_report = transactions.filter_by(year=year)

    # if none this year, return last year
    if not transactions_to_report:
        # stop if we hit floor of years to check against
        if year <= year_min:
            return 0

        return _get_year_end_cost(transactions, year - 1, year_min)

    return transactions_to_report[len(transactions_to_report) -
                                  1].cumulative_cost  # noqa: E501


def _get_map_of_currencies_to_exchange_rates(transactions):
    """First, split the list of txs into sublists where each sublist
    will only contain transactions with the same currency."""

    contiguous_currencies = sorted(
        transactions.transactions, key=lambda t: t.currency
    )
    currency_groups = [
        list(g)
        for _, g in groupby(contiguous_currencies, lambda t: t.currency)
    ]
    currencies_to_exchange_rates = dict()
    # Create a separate ExchangeRate object for each currency
    for currency_group in currency_groups:
        currency = currency_group[0].currency
        min_date = currency_group[0].date
        max_date = currency_group[-1].date
        currencies_to_exchange_rates[currency] = ExchangeRate(
            currency, min_date, max_date
        )
    return currencies_to_exchange_rates


def calculate_costs(transactions, year, ticker):
    ticker_transactions = transactions.filter_by(
        tickers=[ticker], max_year=year
    )
    er_map = _get_map_of_currencies_to_exchange_rates(ticker_transactions)
    tg = TickerGains(ticker)
    tg.add_transactions(ticker_transactions, er_map)
    return ticker_transactions


def _is_foreign_security(transactions):
    """Determine if a ticker represents a foreign security.

    A ticker is considered a foreign security if any of its transactions
    are in a non-CAD currency (e.g., USD). This is used to identify
    shares of non-resident corporations.
    """
    for t in transactions:
        if t.currency != 'CAD':
            return True
    return False


def _counts_for_t1135(transactions, foreign_broker=False):
    """Determine if a ticker should be counted for T1135 purposes.

    T1135 rules:
    - Foreign securities (USD stocks) always count as specified foreign
      property
    - Canadian securities (CAD stocks) only count if held at a foreign broker

    Args:
        transactions: The transactions for a ticker
        foreign_broker: If True, include CAD stocks in T1135 calculation
            (they are foreign property when held outside Canada).
    """
    is_foreign = _is_foreign_security(transactions)

    if is_foreign:
        # Foreign securities always count (shares of non-resident corporations)
        return True
    else:
        # CAD securities only count if held at a foreign broker
        return foreign_broker


def capgains_maxcost(
    transactions,
    year,
    tickers=None,
    output_format='table',
    foreign_broker=False
):
    """Take a list of txs and output the calculated costs.

    Args:
        transactions: list of txs to process
        year: Year to calculate costs for
        tickers: Optional list of tickers to filter by
        output_format: Output format ('table' or 'json')
        foreign_broker: If True, include CAD stocks in T1135 calculation
            (they are foreign property when held at a broker outside Canada)
    """
    filtered_transactions = transactions.filter_by(tickers=tickers)
    if not filtered_transactions:
        if output_format == 'json':
            click.echo(json.dumps({'error': 'No transactions available'}))
        else:
            click.echo("No transactions available")
        return

    if output_format == 'json':
        results = {}
        total_t1135_max_cost = 0
        for ticker in filtered_transactions.tickers:
            transactions_to_report = calculate_costs(
                filtered_transactions, year, ticker
            )
            if not transactions_to_report:
                results[ticker] = {
                    'year': year,
                    'max_cost': 0,
                    'year_end_cost': 0,
                    'is_foreign_security': False,
                    'counts_for_t1135': foreign_broker
                }
                continue

            max_cost = _get_max_cost(
                transactions_to_report, year, transactions_to_report.year_min
            )
            year_end_cost = _get_year_end_cost(
                transactions_to_report, year, transactions_to_report.year_min
            )
            is_foreign = _is_foreign_security(transactions_to_report)
            counts_t1135 = _counts_for_t1135(
                transactions_to_report, foreign_broker
            )

            # Count toward T1135 threshold based on rules
            if counts_t1135:
                total_t1135_max_cost += max_cost

            results[ticker] = {
                'year': year,
                'max_cost': float(max_cost),
                'year_end_cost': float(year_end_cost),
                'is_foreign_security': is_foreign,
                'counts_for_t1135': counts_t1135
            }

        # Add T1135 summary
        results['_t1135_summary'] = {
            'total_max_cost': float(total_t1135_max_cost),
            'threshold': T1135_THRESHOLD,
            'exceeds_threshold': total_t1135_max_cost > T1135_THRESHOLD,
            'foreign_broker': foreign_broker
        }
        click.echo(json.dumps(results, indent=2))
        return

    # Original table output format
    total_t1135_max_cost = 0
    for ticker in filtered_transactions.tickers:
        transactions_to_report = calculate_costs(
            filtered_transactions, year, ticker
        )

        if transactions_to_report:
            is_foreign = _is_foreign_security(transactions_to_report)
            counts_t1135 = _counts_for_t1135(
                transactions_to_report, foreign_broker
            )
        else:
            is_foreign = False
            counts_t1135 = foreign_broker

        # Show indicator for securities
        indicator = ""
        if is_foreign:
            indicator = " [FOREIGN]"
        elif foreign_broker:
            indicator = " [CAD - included via --foreign-broker]"

        click.echo("{}-{}{}".format(ticker, year, indicator))

        if not transactions_to_report:
            click.echo("Nothing to report\n")
            continue

        max_cost = _get_max_cost(
            transactions_to_report, year, transactions_to_report.year_min
        )
        year_end_cost = _get_year_end_cost(
            transactions_to_report, year, transactions_to_report.year_min
        )

        # Count toward T1135 threshold based on rules
        if counts_t1135:
            total_t1135_max_cost += max_cost

        click.echo("[Max cost = {0:,.2f}]".format(max_cost))
        click.echo("[Year end = {0:,.2f}]\n".format(year_end_cost))

    # Display T1135 summary and warning if threshold exceeded
    click.echo("=" * 50)
    if foreign_broker:
        click.echo(
            "T1135 Summary for {} (foreign broker - all securities included)"
            .format(year)
        )
    else:
        click.echo(
            "T1135 Summary for {} (Canadian broker - foreign securities only)"
            .format(year)
        )
    click.echo(
        "Total specified foreign property maximum cost: ${0:,.2f} CAD"
        .format(total_t1135_max_cost)
    )
    if total_t1135_max_cost > T1135_THRESHOLD:
        click.echo(
            click.style(
                "WARNING: Total cost exceeds ${0:,.0f} CAD. "
                "You may need to file form T1135.".format(T1135_THRESHOLD),
                fg='yellow',
                bold=True
            )
        )
