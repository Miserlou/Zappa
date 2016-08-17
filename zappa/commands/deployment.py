# encoding: utf-8

import click
from click import ClickException

from zappa.commands.common import cli
from zappa.commands.scheduler import _schedule, _unschedule


@cli.command()
@click.option('app_function', '-a', '--app-function', default=None, type=click.STRING,
              help='The WSGI application function.')
@click.argument('env', required=False, type=click.STRING)
@click.pass_context
def deploy(ctx, env, app_function):
    """
    Package your project, upload it to S3, register the Lambda function
    and create the API Gateway routes.

    """
    _deploy(ctx.obj, env, app_function)


def _deploy(config, env, app_function):
    loader = config.loader(env, app_function)
    settings = loader.settings

    # check first before running prebuild scripts
    if loader.is_already_deployed():
        click.echo("This application is " +
                   click.style("already deployed", fg="red") +
                   " - did you mean to call " + click.style("update", bold=True) + "?")
        raise ClickException("Lambda environment is already deployed")

    # run any prebuild scripts, etc...
    loader.pre_deploy()

    # Create the Lambda Zip
    loader.create_package()
    loader.callback('zip')

    # Upload it to S3
    success = loader.zappa.upload_to_s3(settings.zip_path, settings.s3_bucket)

    if not success:  # pragma: no cover
        click.echo("Unable to upload to S3. Quitting.")
        return

    # Register the Lambda function with that zip as the source
    # You'll also need to define the path to your lambda_handler code.
    settings.lambda_arn = loader.zappa.create_lambda_function(
        bucket=settings.s3_bucket,
        s3_key=settings.zip_path,
        function_name=settings.lambda_name,
        handler=settings.lambda_handler,
        description=settings.lambda_description,
        vpc_config=settings.vpc_config,
        timeout=settings.timeout_seconds,
        memory_size=settings.memory_size)

    # Schedule events for this deployment
    _schedule(config, env)

    endpoint_url = ''
    if settings.use_apigateway:
        loader.create_and_configure_apigateway()

    # clean up...
    loader.post_deploy()

    loader.callback('post')

    click.echo("Deployed! {}".format(endpoint_url))


@cli.command()
@click.argument('env', required=False, type=click.STRING)
@click.pass_context
def undeploy(ctx, env):
    """
    Tear down an exiting deployment.
    """
    _undeploy(ctx.obj, env)


def _undeploy(config, env):
    loader = config.loader(env)
    settings = loader.settings

    if not config.auto_confirm:
        confirmed = click.confirm("Are you sure you want to undeploy?")
        if confirmed is False:
            return

    if settings.remove_logs:
        loader.zappa.remove_api_gateway_logs(settings.lambda_name)

    domain_name = settings.get('domain')

    # Only remove the api key when not specified
    if settings.api_key_required and settings.api_key is None:
        api_id = loader.zappa.get_api_id(settings.lambda_name)
        loader.zappa.remove_api_key(api_id, settings.api_stage)

    loader.zappa.undeploy_api_gateway(
        settings.lambda_name,
        domain_name=domain_name
    )

    _unschedule(config, env)  # removes event triggers, including warm up event.

    loader.zappa.delete_lambda_function(settings.lambda_name)

    if settings.remove_logs:
        loader.zappa.remove_lambda_function_logs(settings.lambda_name)

    click.echo("Done!")


@cli.command()
@click.option('app_function', '-a', '--app-function', default=None, type=click.STRING,
              help='The WSGI application function.')
@click.argument('env', required=False, type=click.STRING)
@click.pass_context
def update(ctx, env, app_function):
    """
    Repackage and update the function code.
    """
    _update(ctx.obj, env, app_function)


def _update(config, env, app_function):
    loader = config.loader(env, app_function)
    settings = loader.settings

    # run any prebuild scripts, etc...
    loader.pre_deploy()

    # Create the Lambda Zip
    loader.create_package()
    loader.callback('zip')

    # Upload it to S3
    success = loader.zappa.upload_to_s3(settings.zip_path, settings.s3_bucket)
    if not success:  # pragma: no cover
        click.echo("Unable to upload to S3. Quitting.")
        return

    # Register the Lambda function with that zip as the source
    # You'll also need to define the path to your lambda_handler code.
    settings.lambda_arn = loader.zappa.update_lambda_function(
        settings.s3_bucket, settings.zip_path, settings.lambda_name)

    # Update the configuration, in case there are changes.
    settings.lambda_arn = loader.zappa.update_lambda_configuration(
        lambda_arn=settings.lambda_arn, function_name=settings.lambda_name,
        handler=settings.lambda_handler, description=settings.lambda_description,
        vpc_config=settings.vpc_config, timeout=settings.timeout_seconds,
        memory_size=settings.memory_size)

    if settings.domain:
        endpoint_url = settings.domain
    else:
        endpoint_url = loader.zappa.get_api_url(settings.lambda_name, settings.api_stage)

    # Schedule events for this deployment
    _schedule(config, env)

    loader.zappa.update_stage_config(
        settings.lambda_name,
        settings.api_stage,
        settings.cloudwatch_log_level,
        settings.cloudwatch_data_trace,
        settings.cloudwatch_metrics_enabled
    )

    # clean up...
    loader.post_deploy()

    loader.callback('post')

    if endpoint_url and 'https://' not in endpoint_url:
        endpoint_url = 'https://' + endpoint_url
    click.echo(
        "Your updated Zappa deployment is " + click.style("live", fg='green', bold=True) + "!: {}".format(endpoint_url))


@cli.command()
@click.option('revision', '-n', '--num-rollback', default=0, required=True, type=click.INT,
              help='The number of versions to rollback.')
@click.argument('env', required=False, type=click.STRING)
@click.pass_context
def rollback(ctx, env, revision):
    """
    Rolls back the currently deploy lambda code to a previous revision.
    """
    _rollback(ctx.obj, env, revision)


def _rollback(config, env, revision):
    loader = config.loader(env)
    settings = loader.settings

    click.echo("Rolling back..")

    loader.zappa.rollback_lambda_function_version(settings.lambda_name, versions_back=revision)
    click.echo("Done!")
