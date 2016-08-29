from functools import update_wrapper

import click
from click import ClickException
from zappa.commands import cli_exit_codes
from zappa.commands.cli_utils import print_exception, shamelessly_promote
from zappa.loader import ZappaLoader, DEFAULT_SETTINGS_FILE


def trace(f):
    def new_func(*args, **kwargs):
        click.echo(f.__name__ + " " + "=" * 20)
        rv = f(*args, **kwargs)
        click.echo(rv)
        return rv
    return update_wrapper(new_func, f)


class Config(object):
    """
    Configuration object that gets passed along with the context from command to subcommand.
    Use this as a way to cache any information you may need.
    """
    def __init__(self):
        self._loader = None
        self.settings_filename = DEFAULT_SETTINGS_FILE
        self.settings = None
        self.auto_confirm = False
        self.boto_session = None

    def loader(self, env=None, app_function=None):
        if self._loader is None:
            self._loader = ZappaLoader(
                self.settings, api_stage=env, app_function=app_function, session=self.boto_session)
        return self._loader


def ensure_obj(f):
    """A decorator that ensures context.obj exists. If it doesn't,
    a new dict() is created and stored as obj.
    """
    @click.pass_context
    def new_func(ctx, *args, **kwargs):
        if ctx.obj is None:
            ctx.obj = Config()
        return ctx.invoke(f, *args, **kwargs)
    return update_wrapper(new_func, f)


def catch_exceptions():
    """A decorator that gracefully handles exceptions, exiting
    with :py:obj:`exit_codes.OTHER_FAILURE`.
    """

    def decorator(f):
        @click.pass_context
        def new_func(ctx, *args, **kwargs):
            try:
                return ctx.invoke(f, *args, **kwargs)
            except ClickException as exc:
                handle_error(ctx)
                exc.show()
                ctx.exit(code=exc.exit_code)

            except (KeyboardInterrupt, EOFError, click.exceptions.Abort):
                handle_error(ctx)
                click.echo('Aborted!')
                ctx.exit(code=cli_exit_codes.ABORT)

            except Exception as e:
                print_exception()
                handle_error(ctx)
                shamelessly_promote()
                ctx.exit(code=cli_exit_codes.OTHER_FAILURE)

        return update_wrapper(new_func, f)
    return decorator


def handle_error(ctx):
    """
    Handles an Exception.
    """
    # TODO: We should look into having a clean up method in loader...
    # Remove the Zip from S3 upon failure.
    if hasattr(ctx, 'obj') and ctx.obj._loader is not None:
        if ctx.obj.loader().settings.zip_path:
            click.echo("Removing uploaded zip file from S3")
            ctx.obj.loader().remove_uploaded_zip()
