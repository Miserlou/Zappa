from datetime import datetime, timedelta

import click
from click import ClickException
from zappa.commands.common import cli
from zappa.commands.cli_utils import tabular_print, METRIC_NAMES


@cli.command()
@click.argument('env', required=False, type=click.STRING)
@click.pass_context
def versions(ctx, env):
    loader = ctx.obj.loader(env)
    settings = loader.settings
    vers = get_lambda_versions(loader.zappa, settings.lambda_name)
    for ver in vers:
        for k,v in ver.items():
            tabular_print(k, v)
        click.echo()


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


def get_lambda_event_rules(zappa, lambda_name):
    return zappa.get_event_rules_for_lambda(lambda_name)


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


def print_api_gateway_status(zappa, settings, api_url, api_id):
    tabular_print("API Gateway URL", api_url)

    # Api Keys
    for api_key in zappa.get_api_keys(api_id, settings.api_stage):
        tabular_print("API Gateway x-api-key", api_key)


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
    api_id = loader.zappa.get_api_id(settings.lambda_name)
    api_url = get_lambda_api_url(loader.zappa, settings.lambda_name, settings.api_stage)
    domain_url = settings.get('domain')
    event_rules = get_lambda_event_rules(loader.zappa, settings.lambda_name)

    # print to the console
    print_versions_status(lambda_versions, settings)
    print_configuration_status(conf)
    print_metrics_status(invocations, errors, error_rate)

    print_api_gateway_status(loader.zappa, settings, api_url=api_url, api_id=api_id)

    # There literally isn't a better way to do this.
    # AWS provides no way to tie a APIGW domain name to its Lambda funciton.
    if domain_url:
        tabular_print("Domain URL", 'https://' + domain_url)
    else:
        tabular_print("Domain URL", "None Supplied")

    tabular_print("Domain URL", domain_url)
    print_rule_status(event_rules)

    # TODO: S3/SQS/etc. type events?
