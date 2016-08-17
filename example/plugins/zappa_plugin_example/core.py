"""
An example plugin for zappa
"""

import click

colors = (
    'black',
    'red',
    'green',
    'yellow',
    'blue',
    'magenta',
    'cyan',
    'white'
)


@click.command()
@click.option('color', '--color', default=None, type=click.Choice(colors), help="An example option")
@click.pass_context
def example(ctx, color):
    """
    Do some stuff...
    """
    click.secho('Option value: {}'.format(color), fg=color, bold=True)
    click.secho(str(ctx.obj.__dict__), fg=color, bold=True)
