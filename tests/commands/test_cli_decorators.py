import click
from click import Abort
from click import ClickException
from click import Context
from click.testing import CliRunner
from mock import MagicMock
from nose.tools import assert_equals, assert_in
from zappa.commands import cli_exit_codes
from zappa.commands.cli_decorators import ensure_obj, Config, catch_exceptions, handle_error


class TestCLIDecorators(object):

    def setUp(self):
        self.runner = CliRunner()

    def test_ensure_obj(self):
        @click.command()
        @click.pass_context
        @ensure_obj
        def hello(ctx):
            if not isinstance(ctx.obj, Config):
                click.echo("ctx.obj is not of type Config")
            else:
                click.echo("{}".format(ctx.obj.__class__.__name__))

        result = self.runner.invoke(hello)
        assert_equals(result.output.strip(), 'Config', 'ctx.obj is not Config: {}'.format(result.output))

    def test_cli_exceptions(self):

        exceptions = {
            ClickException: (cli_exit_codes.ABORT, None),
            Abort: (cli_exit_codes.ABORT, 'Aborted!'),
            KeyboardInterrupt: (cli_exit_codes.ABORT, 'Aborted!'),
            EOFError: (cli_exit_codes.ABORT, 'Aborted!'),
            Exception: (cli_exit_codes.OTHER_FAILURE, None)
        }

        for exc, error_code in exceptions.iteritems():
            yield self.cli_exceptions, exc, error_code[0], error_code[1]

    def cli_exceptions(self, exception, error_code, output=None):
        name = exception.__class__.__name__

        @click.command()
        @click.pass_context
        @ensure_obj
        @catch_exceptions()
        def hello(ctx):
            if isinstance(exception, (KeyboardInterrupt, EOFError)):
                raise exception
            raise exception("Raising {}".format(name))

        result = self.runner.invoke(hello)
        assert_equals(
            result.exit_code, error_code, "Exit code did not equal '{}': {}".format(error_code, result.exit_code))
        if output:
            assert_in(
                output, result.output.strip(), 'Did not raise "{}": {}'.format(output, result.output))
        else:
            assert_in(
                "Raising {}".format(name), result.output.strip(), 'Did not raise "{}": {}'.format(name, result.output))

    def test_cli_handle_error(self):
        @click.command()
        @click.pass_context
        @ensure_obj
        @catch_exceptions()
        def hello(ctx):
            pass

        ctx = Context(hello, info_name=hello.name, parent=None)
        ctx.obj = Config()
        ctx.obj._loader = MagicMock()
        ctx.obj._loader.settings.zip_path = MagicMock(return_value=True)
        ctx.obj._loader.remove_uploaded_zip = MagicMock(return_value=None)

        handle_error(ctx)
        ctx.obj._loader.remove_uploaded_zip.assert_called_once()

