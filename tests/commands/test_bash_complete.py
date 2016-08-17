from click.testing import CliRunner
from nose.tools import eq_
from zappa.commands.bash_complete import _bash_complete_name, bash_complete_command


class TestCLIBashComplete(object):
    app_name = 'APP-NAME'

    def setUp(self):
        self.runner = CliRunner()

    def test_bash_complete_name(self):
        value = _bash_complete_name(self.app_name)
        eq_(value, 'APP_NAME')

    def test_bash_complete_command(self):
        result = self.runner.invoke(bash_complete_command(self.app_name))
        assert result.exit_code == 0
        assert '_APP_NAME_COMPLETE=source' in result.output
