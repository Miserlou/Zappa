# encoding: utf-8
import botocore
import click
from click import ClickException

from zappa.commands.common import cli


@cli.command()
@click.argument('env', required=False, type=click.STRING)
@click.pass_context
def schedule(ctx, env):
    """
    Given a a list of functions and a schedule to execute them,
    setup up regular execution.

    """
    _schedule(ctx.obj, env)


def _schedule(config, env):
    loader = config.loader(env)
    settings = loader.settings

    function_response = validate_events(loader, settings)

    click.echo("Scheduling..")
    loader.zappa.schedule_events(
        lambda_arn=function_response['Configuration']['FunctionArn'],
        lambda_name=function_response['Configuration']['FunctionName'],
        events=settings.events
    )


@cli.command()
@click.argument('env', required=False, type=click.STRING)
@click.pass_context
def unschedule(ctx, env):
    """
    Given a a list of scheduled functions,
    tear down their regular execution.

    """
    _unschedule(ctx.obj, env)


def _unschedule(config, env):
    loader = config.loader(env)
    settings = loader.settings

    function_response = validate_events(loader, settings)

    click.echo("Unscheduling..")
    loader.zappa.unschedule_events(
        lambda_arn=function_response['Configuration']['FunctionArn'],
        events=settings.events
    )


def validate_events(loader, settings):
    if settings.get('events'):
        if not isinstance(settings.events, list):  # pragma: no cover
            raise ClickException("Events must be supplied as a list.")

        try:
            function_response = loader.zappa.lambda_client.get_function(FunctionName=settings.lambda_name)
        except botocore.exceptions.ClientError:  # pragma: no cover
            raise ClickException(
                "Function does not exist, please deploy first. Ex: zappa deploy {}".format(settings.api_stage))
        return function_response
    else:
        raise ClickException("To schedule events, you need to define the events in your settings file.")
