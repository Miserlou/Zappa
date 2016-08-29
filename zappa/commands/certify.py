# encoding: utf-8
import botocore
import click
from click import ClickException
from zappa.commands.cli_utils import shamelessly_promote

from zappa.commands.common import cli


@cli.command()
@click.argument('env', required=False, type=click.STRING)
@click.pass_context
def certify(ctx, env):
    """
    Register or update a domain certificate for this env.
    """

    loader = ctx.obj.loader(env)
    _certify(loader)


def _certify(loader):
    settings = loader.settings

    # Make sure this isn't already deployed.
    deployed_versions = loader.zappa.get_lambda_function_versions(settings.lambda_name)
    if len(deployed_versions) == 0:
        click.echo("This application " +
                   click.style("isn't deployed yet", fg="red") +
                   " - did you mean to call " +
                   click.style("deploy", bold=True) + "?")
        return

    # Get install account_key to /tmp/account_key.pem
    account_key_location = settings.get('lets_encrypt_key')
    domain = settings.get('domain')

    if not account_key_location:
        click.echo(
            "Can't certify a domain without " + click.style("lets_encrypt_key", fg="red", bold=True) + " configured!")
        return
    if not domain:
        click.echo("Can't certify a domain without " + click.style("domain", fg="red", bold=True) + " configured!")
        return

    if 's3://' in account_key_location:
        bucket = account_key_location.split('s3://')[1].split('/')[0]
        key_name = account_key_location.split('s3://')[1].split('/')[0]
        loader.zappa.s3_client.download_file(bucket, key_name, '/tmp/account.key')
    else:
        from shutil import copyfile
        copyfile(account_key_location, '/tmp/account.key')

    click.echo("Certifying domain " + click.style(domain, fg="green", bold=True) + "..")

    # Get cert and update domain.
    from letsencrypt import get_cert_and_update_domain, cleanup
    cert_success = get_cert_and_update_domain(
        loader.zappa,
        settings.lambda_name,
        settings.api_stage,
        domain
    )
    cleanup()

    if cert_success:
        click.echo("Certificate " + click.style("updated", fg="green", bold=True) + "!")
    else:
        click.echo(click.style("Failed", fg="red", bold=True) + " to generate or install certificate! :(")
        click.echo("\n==============\n")
        shamelessly_promote()


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

    if settings.get('keep_warm', True):
        add_keep_warm_event(loader)

    if settings.get('lets_encrypt_expression'):
        add_lets_encrypt_event(loader)

    click.echo("Scheduling..")
    loader.zappa.schedule_events(
        lambda_arn=function_response['Configuration']['FunctionArn'],
        lambda_name=function_response['Configuration']['FunctionName'],
        events=settings.events
    )


def add_keep_warm_event(loader):
    settings = loader.settings
    if not settings.events:
        settings.events = []
    keep_warm_rate = settings.get('keep_warm_expression', "rate(2 minutes)")
    settings.events.append({
        'name': 'zappa-keep-warm',
        'function': 'handler.keep_warm_callback',
        'expression': keep_warm_rate,
        'description': 'Zappa Keep Warm - {}'.format(settings.lambda_name)
    })


def add_lets_encrypt_event(loader):
    settings = loader.settings
    function_response = loader.zappa.lambda_client.get_function(FunctionName=settings.lambda_name)
    conf = function_response['Configuration']
    timeout = conf['Timeout']

    if timeout < 60:
        click.echo(click.style(
            "Unable to schedule certificate autorenewer!", fg="red", bold=True) +
                   " Please redeploy with a " + click.style("timeout_seconds", bold=True) + " greater than 60!")
    else:
        settings.events.append({'name': 'zappa-le-certify',
                                'function': 'handler.certify_callback',
                                'expression': settings.get('lets_encrypt_expression'),
                                'description': 'Zappa LE Certificate Renewer - {}'.format(settings.lambda_name)})


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
    try:
        loader.zappa.unschedule_events(
            lambda_arn=function_response['Configuration']['FunctionArn'],
            events=settings.events
        )
    except:
        pass


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
