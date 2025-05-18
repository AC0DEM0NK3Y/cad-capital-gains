"""
Command handlers for converting various transaction data formats to
cad-capital-gains format.
Currently supports:
- Schwab Equity Awards Center (EAC) JSON format
"""

import click
from capgains.converters.schwab_eac import convert_schwab_file


def capgains_convert_schwab(input_file, output_file, tickers=None):
    """Convert Schwab equity awards JSON file to cad-capital-gains format.

    Args:
        input_file: Path to Schwab EAC JSON file
        output_file: Path to write converted JSON file
        tickers: Optional list of tickers to filter by
    """
    try:
        convert_schwab_file(input_file, output_file, tickers=tickers)
        click.echo(f"Successfully converted transactions to {output_file}")
    except FileNotFoundError:
        click.echo(f"Error: Could not find input file {input_file}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.Abort()
