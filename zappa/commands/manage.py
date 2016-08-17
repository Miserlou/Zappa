# encoding: utf-8

import click
from zappa.commands.function import invoke
from zappa.commands.common import cli


def django_management_command():
    @cli.command(context_settings=dict(ignore_unknown_options=True))
    @click.argument('env', required=True, type=click.STRING)
    @click.argument('manage_args', nargs=-1, type=click.UNPROCESSED)
    @click.pass_context
    def manage(ctx, env, manage_args):
        """
        Call django's management command.  This is only available for projects using django.
        """
        check_for_django_settings(ctx.obj, env)
        # manage_args = " ".join(manage_args)
        ctx.invoke(invoke, env=env, function_name="manage", extra_args=manage_args)
    return manage


def check_for_django_settings(config, env):
    settings = config.loader(env).settings

    if not settings.get('django_settings'):
        msg = "\n".join([
            "This command is for Django projects only!",
            "If this is a Django project, please define django_settings in your zappa_settings."
        ])
        raise click.UsageError(msg)
