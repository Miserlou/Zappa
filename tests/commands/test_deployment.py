import botocore
from click import ClickException
from mock import Mock, MagicMock
from nose.tools import assert_equal, raises
from tests.commands.base import CLITestBase
from zappa.commands.cli_decorators import Config
from zappa.commands.deployment import _deploy, _undeploy, _update, _rollback
from zappa.settings import Settings, SETTINGS_DEFAULT


class TestCLIDeployment(CLITestBase):

    def get_stage_settings(self, env):
        all_settings = Settings.from_file(self.SETTINGS_FILENAME)
        settings = Settings(SETTINGS_DEFAULT)
        settings.deep_update(all_settings[env])
        settings.zip_path = "lambda_package-3223453.zip"
        return settings

    def create_config(self, already_deployed=False, upload_s3_success=True):
        config = Config()
        config._loader = Mock()
        config._loader.zappa = Mock()
        config._loader.settings = self.get_stage_settings('ttt888')
        config.settings_filename = self.SETTINGS_FILENAME
        config.auto_confirm = False

        config._loader.is_already_deployed = Mock(return_value=already_deployed)
        config._loader.zappa.upload_to_s3 = Mock(return_value=upload_s3_success)

        return config

    def test_deploy(self):
        """
        Test the deploy command, but not loader
        """
        config = self.create_config()

        _deploy(config, 'ttt888', None)

        config._loader.is_already_deployed.assert_called_once()
        config._loader.pre_deploy.assert_called_once()
        config._loader.post_deploy.assert_called_once()

        config._loader.create_package.assert_called_once()
        config._loader.zappa.upload_to_s3.assert_called_once()

        config._loader.zappa.create_lambda_function.assert_called_once()
        config._loader.zappa.create_keep_warm.assert_called_once()
        config._loader.create_and_configure_apigateway.assert_called_once()

        assert_equal(config._loader.callback.call_count, 2)

    def test_undeploy(self):
        """
        Test the undeploy command, but not loader
        """
        config = self.create_config()
        config.auto_confirm = True

        _undeploy(config, 'ttt888')

        config._loader.zappa.undeploy_api_gateway.assert_called_once()
        config._loader.zappa.remove_keep_warm.assert_called_once()
        config._loader.zappa.delete_lambda_function.assert_called_once()

    @raises(ClickException)
    def test_undeploy_exception(self):
        config = self.create_config()
        config.auto_confirm = True

        error_response = {
            'Error': {
                'Code': 'Unknown',
                'Message': 'Unknown'
            }
        }

        config._loader.zappa.delete_lambda_function = MagicMock(
            side_effect=botocore.exceptions.ClientError(
                error_response, 'deleting_my_lambda'))
        _undeploy(config, 'ttt888')

        config._loader.zappa.undeploy_api_gateway.assert_called_once()
        config._loader.zappa.remove_keep_warm.assert_called_once()
        config._loader.zappa.delete_lambda_function.assert_called_once()

    def test_update(self):
        config = self.create_config()
        config.auto_confirm = True

        _update(config, 'ttt888', None)

        config._loader.pre_deploy.assert_called_once()
        config._loader.post_deploy.assert_called_once()
        config._loader.create_package.assert_called_once()

        config._loader.zappa.upload_to_s3.assert_called_once()
        config._loader.zappa.update_lambda_function.assert_called_once()
        config._loader.zappa.create_keep_warm.assert_called_once()
        config._loader.zappa.update_stage_config.assert_called_once()

        assert_equal(config._loader.callback.call_count, 2)

    def test_rollback(self):
        config = self.create_config()
        config.auto_confirm = True

        revisions = 2

        _rollback(config, 'ttt888', revisions)
        config._loader.zappa.rollback_lambda_function_version.assert_called_once()
