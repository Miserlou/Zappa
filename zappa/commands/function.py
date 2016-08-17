# encoding: utf-8
import base64
import types
from datetime import datetime, timedelta

import click
from click import ClickException
from zappa.commands.cli_utils import tabular_print, METRIC_NAMES
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


"""
get_lambda_event_rules ====================
[{u'ScheduleExpression': u'rate(5 minutes)', u'Name': u'zappa-keep-warm-insitome-dev', 'ResponseMetadata': {'HTTPStatusCode': 200, 'RequestId': 'e773b3c0-6948-11e6-b1bb-f3a2160db3a1', 'HTTPHeaders': {'x-amzn-requestid': 'e773b3c0-6948-11e6-b1bb-f3a2160db3a1', 'date': 'Tue, 23 Aug 2016 15:47:31 GMT', 'content-length': '287', 'content-type': 'application/x-amz-json-1.1'}}, u'RoleArn': u'arn:aws:iam::611616856832:role/ZappaLambdaExecution', u'State': u'ENABLED', u'Arn': u'arn:aws:events:us-east-1:611616856832:rule/zappa-keep-warm-insitome-dev', u'Description': u'Zappa Keep Warm - insitome-dev'}]
"""

@cli.command()
@click.argument('env', required=False, type=click.STRING)
@click.pass_context
def status(ctx, env):
    """
    Describe the status of the current deployment.
    """
    _status(ctx.obj, env)


def get_lambda_versions(zappa, lambda_name):
    lambda_versions = zappa.get_lambda_function_versions(lambda_name)
    if not lambda_versions:
        raise ClickException("No Lambda detected - have you deployed yet?")
    return lambda_versions


def get_lambda_configuration(zappa, lambda_name):
    function_response = zappa.lambda_client.get_function(FunctionName=lambda_name)
    return function_response['Configuration']


def get_lambda_metrics_by_name(zappa, metric="Invocations", lambda_name=None):
    if metric not in METRIC_NAMES:
        raise ClickException(
            "Metric '{}' is not a valid metric. Possible values include: {}".format(metric, str(METRIC_NAMES)))
    try:
        result = zappa.cloudwatch.get_metric_statistics(
            Namespace='AWS/Lambda',
            MetricName=metric,
            StartTime=datetime.utcnow()-timedelta(days=1),
            EndTime=datetime.utcnow(),
            Period=1440,
            Statistics=['Sum'],
            Dimensions=[{'Name': 'FunctionName',
                         'Value': '{}'.format(lambda_name)}]
        )['Datapoints'][0]['Sum']
    except:
        result = 0
    return result


def get_error_rate(errors, invocations):
    error_rate = 0
    if errors > 0:
        try:
            error_rate = "{0:.0f}%".format(float(errors) / float(invocations) * 100)
        except:
            error_rate = "Error calculating"
    return error_rate


def get_lambda_api_url(zappa, lambda_name, api_stage):
    return zappa.get_api_url(lambda_name, api_stage)


def get_lambda_event_rules(zappa, function_arn):
    return zappa.get_event_rules_for_arn(function_arn)


def print_versions_status(lambda_versions, settings):
    tabular_print("Lambda Versions", len(lambda_versions))
    tabular_print("Lambda Name", settings.lambda_name)


def print_configuration_status(conf):
    tabular_print("Lambda ARN", conf['FunctionArn'])
    tabular_print("Lambda Role", conf['Role'])
    tabular_print("Lambda Handler", conf['Handler'])
    tabular_print("Lambda Code Size", conf['CodeSize'])
    tabular_print("Lambda Version", conf['Version'])
    tabular_print("Lambda Last Modified", conf['LastModified'])
    tabular_print("Lambda Memory Size", conf['MemorySize'])
    tabular_print("Lambda Timeout", conf['Timeout'])
    tabular_print("Lambda Runtime", conf['Runtime'])


def print_metrics_status(invocations, errors, error_rate):
    tabular_print("Invocations (24h)", int(invocations))
    tabular_print("Errors (24h)", int(errors))
    tabular_print("Error Rate (24h)", error_rate)


def print_rule_status(rules):
    tabular_print("Num. Event Rules", len(rules))

    for rule in rules:
        rule_name = rule['Name']
        print('')
        tabular_print("Event Rule Name", rule_name)
        tabular_print("Event Rule Schedule", rule.get(u'ScheduleExpression'))
        tabular_print("Event Rule State", rule.get(u'State').title())
        tabular_print("Event Rule ARN", rule.get(u'Arn'))


def _status(config, env):
    loader = config.loader(env)
    settings = loader.settings

    click.echo("Status for " + click.style(settings.lambda_name, bold=True) + ": ")

    # Collect all information needed
    conf = get_lambda_configuration(loader.zappa, settings.lambda_name)
    lambda_versions = get_lambda_versions(loader.zappa, settings.lambda_name)
    invocations = get_lambda_metrics_by_name(loader.zappa, 'Invocations', settings.lambda_name)
    errors = get_lambda_metrics_by_name(loader.zappa, 'Errors', settings.lambda_name)
    error_rate = get_error_rate(errors, invocations)
    api_url = get_lambda_api_url(loader.zappa, settings.lambda_name, settings.api_stage)
    domain_url = settings.get('domain')
    event_rules = get_lambda_event_rules(loader.zappa, conf['FunctionArn'])

    # print to the console
    print_versions_status(lambda_versions, settings)
    print_configuration_status(conf)
    print_metrics_status(invocations, errors, error_rate)

    tabular_print("API Gateway URL", api_url)
    tabular_print("Domain URL", domain_url)
    print_rule_status(event_rules)

    # TODO: S3/SQS/etc. type events?
