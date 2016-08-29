import logging
import unittest

from click import Context
from click.testing import CliRunner
from slugify import slugify
from tests.utils import placebo_session
from zappa.commands.cli_decorators import Config
from zappa.commands.common import setup_cli, cli
from zappa.commands.deployment import _deploy, _undeploy
from zappa.settings import Settings, SETTINGS_DEFAULT

logging.getLogger('botocore').setLevel(logging.INFO)


class CLITestBase(unittest.TestCase):
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
        all_settings = self.get_settings()
        settings = Settings(SETTINGS_DEFAULT)
        settings.deep_update(all_settings[env])
        settings.zip_path = "lambda_package-3223453.zip"
        settings.project_name = 'zappa'
        settings.api_stage = env
        settings.lambda_name = slugify(settings.project_name + '-' + settings.api_stage)
        return settings

    def create_config(self, boto_session=None):
        config = Config()
        config.settings = self.get_settings()
        config.settings_filename = self.SETTINGS_FILENAME
        config.boto_session = boto_session

        # set a few things to make sure we don't prompt, or request urls outside of boto...
        loader = config.loader('ttt888')
        loader.settings.touch = False
        config.auto_confirm = False
        return config


class CLITestConfigBase(CLITestBase):

    @placebo_session
    def setUp(self, session):
        self.config = self.create_config(boto_session=session)
        self.loader = self.config.loader('ttt888')
        self.loader.settings.touch = False

    def ensure_not_deployed(self):
        if not hasattr(self, 'loader'):
            self.fail("Must define self.loader before ensuring deployed")
        if self.loader.is_already_deployed():
            _undeploy(self.config, 'ttt888')

    def ensure_deployed(self):
        if not hasattr(self, 'loader'):
            self.fail("Must define self.loader before ensuring deployed")

        # let's not actually produce a zipfile...
        if not self.loader.is_already_deployed():
            _deploy(self.config, 'ttt888', None)
