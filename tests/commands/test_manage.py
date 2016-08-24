import click
from nose.tools import raises
from tests.commands.base import CLITestBase
from zappa.commands.manage import check_for_django_settings


class TestCLILogs(CLITestBase):

    @raises(click.UsageError)
    def test_check_for_django_settings_bad(self):
        config = self.create_config()

        check_for_django_settings(config, 'ttt888')

    def test_check_for_django_settings(self):
        config = self.create_config()
        config._loader.settings.django_settings = 'myproject.settings'

        check_for_django_settings(config, 'ttt888')
