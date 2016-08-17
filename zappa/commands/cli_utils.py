import os

import click

# cloudwatch lambda metrics
import sys
from click import Abort

METRIC_NAMES = ['Duration', 'Errors', 'Invocations', 'Throttles']


def print_exception():
    click.echo("Oh no! An " + click.style("error occurred", fg='red', bold=True) + "! :(")
    click.echo("\n==============\n")
    import traceback
    traceback.print_exc()
    click.echo("\n==============\n")


def shamelessly_promote():
    """
    Shamelessly promote our little community.
    """

    click.echo("Need " +
               click.style("help", fg='green', bold=True) +
               "? Found a " +
               click.style("bug", fg='green', bold=True) +
               "? Let us " +
               click.style("know", fg='green', bold=True) +
               "! :D")
    click.echo("File bug reports on " +
               click.style("GitHub", bold=True) +
               " here: " +
               click.style("https://github.com/Miserlou/Zappa", fg='cyan', bold=True))
    click.echo("And join our " +
               click.style("Slack", bold=True) +
               " channel here: " +
               click.style("http://bit.do/zappa", fg='cyan', bold=True))
    click.echo("Love!,")
    click.echo(" ~ Team " + click.style("Zappa", bold=True) + "!")


def tabular_print(title, value):
    """
    Convenience function for printing formatted table items.
    """
    click.echo('%-*s%s' % (32, click.style("\t" + title, fg='green') + ':', str(value)))


def validate_environment(config, api_stage=None):

    if api_stage == 'init' and os.path.isfile(config.settings_filename):
        click.echo("This project is " + click.style("already initialized", fg="red", bold=True) + "!")
        raise Abort()

    # Ensure Py2 until Lambda supports it.
    if sys.version_info >= (3, 0):  # pragma: no cover
        click.echo("Zappa currently only works with Python 2, until AWS Lambda adds Python 3 support.")
        raise Abort()

    # Ensure we are inside a virtualenv.
    if not hasattr(sys, 'real_prefix'):  # pragma: no cover
        click.echo("Zappa must be run inside of a virtual environment!")
        click.echo("Learn more about virtual environments here: http://docs.python-guide.org/en/latest/dev/virtualenvs/")
        raise Abort()
