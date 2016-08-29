##
# CLI
##

from mock import Mock
from nose.tools import assert_false
from nose.tools import assert_true

from zappa.loader import ZappaLoader
from zappa.settings import Settings

"""
# NOTE: Postponing writing cli tests until we can figure out how to get placebo to work
# with click, or decouple it from the cli interface, as it should be.
"""

got_prebuild_callback = False


def loader_callback(loader):
    loader.settings.got_loader_callback = True


def prebuild_callback():
    global got_prebuild_callback
    got_prebuild_callback = True


class TestZappaLoader(object):
    SETTINGS_FILENAME = 'test_settings.json'

    def get_zappa_mock(self):
        zappa = Mock()
        zappa.cloudwatch = Mock()
        zappa.lambda_client = Mock()

        # zappa.get_lambda_function_versions = Mock(return_value=self.versions)
        # zappa.lambda_client.get_function = Mock(return_value={'Configuration': self.CONFIGURATION})
        # zappa.cloudwatch.get_metric_statistics = Mock(return_value={'Datapoints': [{'Sum': 400}]})
        # zappa.get_event_rules_for_arn = Mock(return_value=self.RULES)
        return zappa

    def test_cli_sanity(self):
        settings = Settings.from_file(self.SETTINGS_FILENAME)
        loader = ZappaLoader(settings, api_stage='ttt888')
        assert loader is not None

    def test_callback(self):
        settings = Settings.from_file(self.SETTINGS_FILENAME)
        loader = ZappaLoader(settings, api_stage='ttt888')
        loader.settings.callbacks = {'zip': "tests.test_loader.loader_callback"}

        loader.callback('zip')

        assert_true(loader.settings.get('got_loader_callback', False))

    def test_pre_deploy(self):
        settings = Settings.from_file(self.SETTINGS_FILENAME)
        loader = ZappaLoader(settings, api_stage='ttt888')
        loader.settings.prebuild_script = "tests.test_loader.prebuild_callback"

        loader.execute_prebuild_script()

        assert_true(got_prebuild_callback)

    def test_post_deploy(self):
        settings = Settings.from_file(self.SETTINGS_FILENAME)
        loader = ZappaLoader(settings, api_stage='ttt888')
        loader.settings.zip_path = "temp.zip"
        loader.zappa = self.get_zappa_mock()

        loader.post_deploy()

        loader.zappa.remove_from_s3.assert_called_once()
        loader.zappa.remove_from_s3.assert_called_with(
            loader.settings.zip_path, loader.settings.s3_bucket)

    def test_is_already_deployed(self):
        settings = Settings.from_file(self.SETTINGS_FILENAME)
        loader = ZappaLoader(settings, api_stage='ttt888')
        loader.zappa = self.get_zappa_mock()
        loader.zappa.get_lambda_function_versions = Mock(return_value=['one', 'two'])

        assert_true(loader.is_already_deployed())

        loader.zappa.get_lambda_function_versions = Mock(return_value=[])
        assert_false(loader.is_already_deployed())

    def test_create_and_configure_apigateway(self):
        settings = Settings.from_file(self.SETTINGS_FILENAME)
        loader = ZappaLoader(settings, api_stage='ttt888')

        loader.settings.lambda_arn = 'arn:aws:lambda:us-east-1:411416456432:function:hello-dev'
        loader.settings.touch = False

        loader.zappa = self.get_zappa_mock()
        loader.zappa.create_api_gateway_routes = Mock(return_value='bob')

        loader.create_and_configure_apigateway()

        loader.zappa.create_api_gateway_routes.assert_called_once()
        loader.zappa.deploy_api_gateway.assert_called_once()
