import base64
import copy
import json

from click import ClickException
from mock import Mock
from nose.tools import assert_equals, raises
from tests.commands.base import CLITestBase
from zappa.commands.cli_utils import METRIC_NAMES
from zappa.commands.function import _invoke, get_invoke_payload, get_lambda_versions, get_lambda_metrics_by_name, \
    get_lambda_configuration, get_error_rate, _status


class TestCLIDeployment(CLITestBase):

    def test_get_invoke_payload(self):
        result = get_invoke_payload(app_function="app.app")
        assert_equals(result, '{"command": "app.app"}')

        result = get_invoke_payload(app_function="manage", extra_args="check --list-tags")
        assert_equals(result, '{"manage": "check --list-tags"}')

        result = get_invoke_payload(app_function="manage", extra_args=["check", "--list-tags"])
        assert_equals(result, '{"manage": "check --list-tags"}')

    def test_invoke(self):
        config = self.create_config()
        settings = config._loader.settings

        config._loader.zappa.invoke_lambda_function = Mock(return_value={'status': 'ok'})

        _invoke(config, 'ttt888', settings.app_function, None)

        config._loader.zappa.invoke_lambda_function.assert_called_once()
        config._loader.zappa.invoke_lambda_function.assert_called_with(
            settings.lambda_name,
            json.dumps({'command': settings.app_function}),
            invocation_type='RequestResponse'
        )

    def test_invoke_manage(self):
        config = self.create_config()
        settings = config._loader.settings

        # ensure that we decode log results too
        config._loader.zappa.invoke_lambda_function = Mock(
            return_value={'LogResult': base64.b32encode('[1471883001765] Time left for execution: 29999')}
        )

        _invoke(config, 'ttt888', "manage", ["check", "--list-tags"])

        config._loader.zappa.invoke_lambda_function.assert_called_once()
        config._loader.zappa.invoke_lambda_function.assert_called_with(
            settings.lambda_name,
            '{"manage": "check --list-tags"}',
            invocation_type='RequestResponse'
        )


class TestCLIStatus(CLITestBase):
    CONFIGURATION = {
        u'Version': u'$LATEST',
        u'CodeSha256': u'RyI7bX1WRtrXrWfHckLzQ5GkasAtt/tQ0NJeLam6wRk=',
        u'FunctionName': u'hello-dev',
        u'MemorySize': 128,
        u'CodeSize': 5995856,
        u'FunctionArn': u'arn:aws:lambda:us-east-1:611616856832:function:hello-dev',
        u'Handler': u'handler.lambda_handler',
        u'Role': u'arn:aws:iam::411216846232:role/ZappaLambdaExecution',
        u'Timeout': 30,
        u'LastModified': u'2016-08-22T17:13:14.332+0000',
        u'Runtime': u'python2.7',
        u'Description': u'Zappa Deployment'}

    RULES = [
        {
            u'ScheduleExpression': u'rate(5 minutes)',
            u'Name': u'zappa-keep-warm-hello-dev',
            'ResponseMetadata': {
                'HTTPStatusCode': 200,
                'RequestId': 'e773b3c0-6948-11e6-b1bb-f3a2160db3a1',
                'HTTPHeaders': {
                    'x-amzn-requestid': 'e773b3c0-6948-11e6-b1bb-f3a2160db3a1',
                    'date': 'Tue, 23 Aug 2016 15:47:31 GMT',
                    'content-length': '287',
                    'content-type': 'application/x-amz-json-1.1'
                }
            },
            u'RoleArn': u'arn:aws:iam::411216846232:role/ZappaLambdaExecution',
            u'State': u'ENABLED',
            u'Arn': u'arn:aws:events:us-east-1:411216846232:rule/zappa-keep-warm-hello-dev',
            u'Description': u'Zappa Keep Warm - hello-dev'
        }
    ]

    @property
    def versions(self):
        versions = [self.CONFIGURATION]
        for n in range(5):
            conf = copy.copy(self.CONFIGURATION)
            conf[u'Version'] = n
            versions.append(conf)
        return versions

    def get_zappa_mock(self):
        zappa = Mock()
        zappa.cloudwatch = Mock()
        zappa.lambda_client = Mock()
        zappa.get_lambda_function_versions = Mock(return_value=self.versions)
        zappa.lambda_client.get_function = Mock(return_value={'Configuration': self.CONFIGURATION})
        zappa.cloudwatch.get_metric_statistics = Mock(return_value={'Datapoints': [{'Sum': 400}]})
        zappa.get_event_rules_for_arn = Mock(return_value=self.RULES)
        return zappa

    def test_get_lambda_versions(self):
        zappa = self.get_zappa_mock()
        rv = get_lambda_versions(zappa, 'hello')
        assert_equals(rv, self.versions)

    def test_get_lambda_configuration(self):
        settings = self.get_stage_settings('ttt888')
        zappa = self.get_zappa_mock()

        rv = get_lambda_configuration(zappa, settings.lambda_name)
        assert_equals(rv, self.CONFIGURATION)

    def test_lambda_metrics_by_name(self):
        for metric in METRIC_NAMES:
            yield self.lambda_metrics_by_name, metric

    def lambda_metrics_by_name(self, metric):
        settings = self.get_stage_settings('ttt888')
        zappa = self.get_zappa_mock()

        rv = get_lambda_metrics_by_name(zappa, metric=metric, lambda_name=settings.lambda_name)
        assert_equals(rv, 400)

        zappa.cloudwatch.get_metric_statistics = Mock(return_value='bob')
        rv = get_lambda_metrics_by_name(zappa, metric=metric, lambda_name=settings.lambda_name)
        assert_equals(rv, 0)

    @raises(ClickException)
    def test_lambda_metrics_by_bad_name(self):
        settings = self.get_stage_settings('ttt888')
        zappa = self.get_zappa_mock()

        # should raise an exception if not in METRIC_NAMES
        get_lambda_metrics_by_name(zappa, metric="bob", lambda_name=settings.lambda_name)

    def test_get_error_rate(self):
        assert_equals(get_error_rate(0, 0), 0)
        assert_equals(get_error_rate(10, 0), "Error calculating")
        assert_equals(get_error_rate(10, 10), "100%")
        assert_equals(get_error_rate(10, 5), "200%")
        assert_equals(get_error_rate(5, 10), "50%")

    def test_status(self):
        config = self.create_config()
        zappa = self.get_zappa_mock()
        config._loader.zappa = zappa

        _status(config, 'ttt888')

        zappa.lambda_client.get_function.assert_called_once()
        zappa.get_lambda_function_versions.assert_called_once()
        zappa.get_api_url.assert_called_once()
        zappa.get_event_rules_for_arn.assert_called_once()
        assert_equals(zappa.cloudwatch.get_metric_statistics.call_count, 2)
