from click import Context
from click.testing import CliRunner
from mock import Mock
from slugify import slugify
from zappa.commands.cli_decorators import Config
from zappa.commands.common import setup_cli, cli
from zappa.settings import Settings, SETTINGS_DEFAULT


class CLITestBase(object):
    SETTINGS_FILENAME = 'test_settings.json'

    def setUp(self):
        self.runner = CliRunner()

    def get_cli_context(self):
        ctx = Context(cli, info_name=cli.name, parent=None)
        ctx.obj = Config()

        setup_cli(ctx, yes=False, settings_filename=CLITestBase.SETTINGS_FILENAME)
        return ctx

    def get_settings(self):
        return Settings.from_file(self.SETTINGS_FILENAME)

    def get_stage_settings(self, env):
        all_settings = Settings.from_file(self.SETTINGS_FILENAME)
        settings = Settings(SETTINGS_DEFAULT)
        settings.deep_update(all_settings[env])
        settings.zip_path = "lambda_package-3223453.zip"
        settings.project_name = 'zappa'
        settings.api_stage = env
        settings.lambda_name = slugify(settings.project_name + '-' + settings.api_stage)
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

