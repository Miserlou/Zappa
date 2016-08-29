import click
from nose.tools import raises
from tests.commands.base import CLITestBase
from tests.utils import placebo_session
from zappa.commands.manage import check_for_django_settings


class TestCLILogs(CLITestBase):

    @raises(click.UsageError)
    def test_check_for_django_settings_bad(self):
        config = self.create_config()

        check_for_django_settings(config, 'ttt888')

    @placebo_session
    def test_check_for_django_settings(self, session):
        config = self.create_config(boto_session=session)
        loader = config.loader('ttt888')
        loader.settings.django_settings = 'myproject.settings'

        check_for_django_settings(config, 'ttt888')
