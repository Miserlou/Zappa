# encoding: utf-8
import os.path

import click
import sys
from click_didyoumean import DYMGroup
from click_plugins import with_plugins
from pkg_resources import iter_entry_points
from zappa.commands.cli_decorators import ensure_obj, catch_exceptions
from zappa.loader import DEFAULT_SETTINGS_FILE
from zappa.settings import Settings

click.disable_unicode_literals_warning = True
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


@with_plugins(iter_entry_points('zappa.plugins'))
@click.group(cls=DYMGroup, context_settings=CONTEXT_SETTINGS)
@click.version_option()
@click.option('-y', '--yes', is_flag=True, default=False, help='Auto confirm yes')
@click.option('settings_filename', '-s', '--settings', envvar='ZAPPA_SETTINGS', default=DEFAULT_SETTINGS_FILE,
              type=click.Path(), help='The path to a zappa settings file.')
@click.pass_context
@ensure_obj
@catch_exceptions()
def cli(ctx, yes, settings_filename):
    """
    Zappa - Deploy Python applications to AWS Lambda and API Gateway.

    """
    if '-h' in sys.argv or '--help' in sys.argv:
        return
    setup_cli(ctx, yes, settings_filename)


def setup_cli(ctx, yes, settings_filename):
    if not ctx.invoked_subcommand == 'init':
        ctx.obj.settings = Settings.from_file(settings_filename)
    else:
        ctx.obj.settings = Settings()

    ctx.obj.settings_filename = settings_filename
    ctx.obj.auto_confirm = yes
