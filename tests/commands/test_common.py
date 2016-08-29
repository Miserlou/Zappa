from click import Context
from click.testing import CliRunner
from nose.tools import assert_equals, assert_in, assert_is_instance
from nose.tools import assert_raises
from zappa.commands.cli_decorators import Config
from zappa.commands.common import cli, setup_cli
from zappa.settings import Settings


class TestCLICommon(object):

    def setUp(self):
        self.runner = CliRunner()

    def test_print_exception(self):

        result = self.runner.invoke(cli, ['-h'])
        assert_in(
            'Usage: cli [OPTIONS] COMMAND [ARGS]...',
            result.output, "'zappa -h' out put looks wrong: \n\n{}".format(result.output)
        )

    def test_setup_cli(self):
        filename = 'test_settings.json'
        good_keys = ["_settings_filename", "ttt888", "devor"]

        ctx = Context(cli, info_name=cli.name, parent=None)
        ctx.obj = Config()

        assert_raises(RuntimeError, setup_cli, ctx, True, 'Bob')

        ctx = Context(cli, info_name=cli.name, parent=None)
        ctx.obj = Config()
        setup_cli(ctx, yes=True, settings_filename=filename)
        assert_is_instance(ctx.obj.settings, Settings)
        assert_equals(ctx.obj.settings.keys(), good_keys)
        assert_equals(ctx.obj.settings_filename, filename)
        assert_equals(ctx.obj.auto_confirm, True)

        ctx = Context(cli, info_name=cli.name, parent=None)
        ctx.obj = Config()
        setup_cli(ctx, yes=False, settings_filename=filename)
        assert_equals(ctx.obj.settings_filename, filename)
        assert_equals(ctx.obj.auto_confirm, False)
