import click
from click import ClickException
from click.testing import CliRunner
from nose.tools import assert_in
from zappa.commands.cli_utils import print_exception, shamelessly_promote


class TestCLIUtils(object):

    def setUp(self):
        self.runner = CliRunner()

    def test_print_exception(self):

        @click.command()
        def hello():
            try:
                raise ClickException("Something went wrong")
            except ClickException:
                print_exception()

        result = self.runner.invoke(hello)
        assert_in("Oh no! An ", result.output.strip(), 'Wrong output for print_exception: {}'.format(result.output))

    def test_shamelessly_promote(self):

        @click.command()
        def hello():
            shamelessly_promote()

        result = self.runner.invoke(hello)
        assert_in("Need help? Found a bug?", result.output.strip(),
                  'Wrong output for shamelessly_promote: {}'.format(result.output))

