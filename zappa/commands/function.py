# encoding: utf-8
import base64
import types

import click
from zappa.commands.common import cli


@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.argument('env', required=True, type=click.STRING)
@click.argument('function_name', required=True, type=click.STRING)
@click.argument('extra_args', required=False, nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def invoke(ctx, env, function_name, extra_args=None):
    """
    Invoke a remote function.
    """
    _invoke(ctx.obj, env, function_name, extra_args)


def get_invoke_payload(command="command", app_function=None, extra_args=None):
    """
    Get the payload (json dictionary) for the command to execute
    :param command: Can be 'command' (default) or 'manage' for django manage
    :param app_function: The app function to execute, or the word 'manage' for django
    :param extra_args: django management arguments
    :return: The payload
    """
    # TODO: we should have an ENUM command (can only be 'detail-type', 'command', 'manage', or 'Records')

    if app_function == "manage":
        command = "manage"

        # get the rest of the argument list
        if extra_args is not None:
            if isinstance(extra_args, (list, tuple)):
                extra_args = " ".join(extra_args)

            if not isinstance(extra_args, types.StringTypes):
                raise click.ClickException("Extra arguments '{}' is not a list or string".format(str(extra_args)))
            app_function = extra_args
        else:
            app_function = ""

    import json as json
    payload = {command: app_function}
    return json.dumps(payload)


def _invoke(config, env, app_function, extra_args):
    loader = config.loader(env, app_function)
    settings = loader.settings

    payload = get_invoke_payload(app_function=app_function, extra_args=extra_args)

    response = loader.zappa.invoke_lambda_function(
        settings.lambda_name, payload, invocation_type='RequestResponse'
    )

    if 'LogResult' in response:
        click.echo(base64.b64decode(response['LogResult']))
    else:
        click.echo(response)
