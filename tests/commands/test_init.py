import os

from nose.tools import assert_equals
from tests.commands.base import CLITestBase
from zappa.commands import cli


class TestCLIInit(CLITestBase):

    def test_init(self):
        tmp_settings_file = 'zappa_settings.json'
        if os.path.exists(tmp_settings_file):
            os.remove(tmp_settings_file)

        result = self.runner.invoke(cli, ['-y', '-s', tmp_settings_file, 'init'])
        assert_equals(result.exit_code, 0)

        if os.path.exists(tmp_settings_file):
            os.remove(tmp_settings_file)
