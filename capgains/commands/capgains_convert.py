"""
Command handlers for converting various transaction data formats to
cad-capital-gains format.
Currently supports:
- Schwab Equity Awards Center (EAC) JSON format
- TD Direct Investing trade confirmations PDF format
"""

import click
from capgains.converters.schwab_eac import convert_schwab_file
from capgains.converters.td_trade_confirm_pdf import convert_td_trades_file
from capgains.converters.td_statements_pdf import convert_td_statements_directory


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


def capgains_convert_td_trades_pdf(input_file, output_file):
    """Convert TD trade confirmation PDF to cad-capital-gains format.

    Args:
        input_file: Path to TD trade confirmation PDF
        output_file: Path to write converted JSON file
    """
    try:
        convert_td_trades_file(input_file, output_file)
        click.echo(f"Successfully converted transactions to {output_file}")
    except FileNotFoundError:
        click.echo(f"Error: Could not find input file {input_file}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.Abort()


def capgains_convert_td_statements_pdf(statement_dir, confirmation_dir, output_file, include_exchange_rate=False, aliases_file=None):
    """Convert TD Direct Investing statements and confirmations to cad-capital-gains format.
    
    Args:
        statement_dir: Path to directory containing TD statement PDFs
        confirmation_dir: Path to directory containing TD confirmation PDFs
        output_file: Path to write the converted JSON file
        include_exchange_rate: Whether to include exchange rate in output
        aliases_file: Optional path to a JSON file containing ticker aliases
    """
    try:
        convert_td_statements_directory(
            statement_dir, 
            confirmation_dir, 
            output_file, 
            include_exchange_rate,
            aliases_file
        )
        click.echo(f"Successfully converted transactions to {output_file}")
    except FileNotFoundError as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.Abort()
