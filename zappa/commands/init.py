# encoding: utf-8
import random
import string

import click
from click import Abort
from six.moves import input
from zappa.commands.cli_utils import validate_environment
from zappa.commands.common import cli, DEFAULT_SETTINGS_FILE
from zappa.settings import Settings
from zappa.util import detect_django_settings, detect_flask_settings, detect_package

BANNER = u"""
███████╗ █████╗ ██████╗ ██████╗  █████╗
╚══███╔╝██╔══██╗██╔══██╗██╔══██╗██╔══██╗
  ███╔╝ ███████║██████╔╝██████╔╝███████║
 ███╔╝  ██╔══██║██╔═══╝ ██╔═══╝ ██╔══██║
███████╗██║  ██║██║     ██║     ██║  ██║
╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝     ╚═╝  ╚═╝
"""


# noinspection PyUnresolvedReferences
@cli.command()
@click.pass_context
def init(ctx):
    """
    Initialize a new Zappa project by creating a new zappa_settings.json in a guided process.
    """

    # This should probably be broken up into few separate components once it's stable.
    # Testing these inputs requires monkey patching with mock, which isn't pretty.
    _init(ctx.obj)


def print_init_intro():
    # Explain system.
    click.echo(click.style(BANNER, fg='green', bold=True))

    click.echo(click.style("Welcome to ", bold=True) +
               click.style("Zappa", fg='green', bold=True) + click.style("!\n", bold=True))
    click.echo(
        click.style("Zappa", bold=True) +
        " is a system for running server-less Python web applications on AWS Lambda and AWS API Gateway.")
    click.echo("This `init` command will help you create and configure your new Zappa deployment.")
    click.echo("Let's get started!\n")


def print_init_tail(env):
    click.echo(click.style("Done", bold=True) + "! Now you can " +
               click.style("deploy", bold=True) + " your Zappa application by executing:\n")
    click.secho("\t$ zappa deploy {}".format(env), bold=True)

    click.echo("\nAfter that, you can " + click.style("update", bold=True) + " your application code with:\n")
    click.secho("\t$ zappa update {}".format(env), bold=True)

    click.echo(
        "\nTo learn more, check out our project page on " + click.style("GitHub", bold=True) + " here: " + click.style(
            "https://github.com/Miserlou/Zappa", fg="cyan", bold=True))
    click.echo(
        "and stop by our " + click.style("Slack", bold=True) + " channel here: " + click.style("http://bit.do/zappa",
                                                                                               fg="cyan", bold=True))
    click.echo("\nEnjoy!,")
    click.echo(" ~ Team " + click.style("Zappa", bold=True) + "!")


def prompt_for_environment(config):
    env = 'dev'

    # Create Env
    click.echo("Your Zappa configuration can support multiple deployed environments, like '" +
               click.style("dev", bold=True) + "', '" + click.style("staging", bold=True) + "', and '" +
               click.style("production", bold=True) + "'.")

    if config.auto_confirm:
        click.echo("Your initial environment will be 'dev'.  You can change this in the settings file.")
    else:
        env = input("What do you want to call this environment (default 'dev')?: ") or "dev"
    return env


def prompt_for_s3_bucket(config):
    bucket = "zappa-" + ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(9))

    # Create Bucket
    click.echo(
        "\nYour Zappa deployments will need to be uploaded to a " + click.style("private S3 bucket", bold=True) + ".")
    if config.auto_confirm:
        click.echo("Your S3 bucket will be named: {}".format(bucket))
    else:
        click.echo("If you don't have a bucket yet, we'll create one for you too.")
        bucket = input("What do you want call your bucket? (default '{}'): ".format(bucket)) or bucket
    click.echo()
    return bucket


def prompt_for_django(config):
    matches = detect_django_settings()
    if not matches:
        return

    click.echo("It looks like this is a " + click.style("Django", bold=True) + " application!")
    click.echo("What is the " + click.style("module path", bold=True) + " to your projects's Django settings?")

    while django_settings in [None, '']:
        if matches:
            click.echo("We discovered: " + click.style(', '.join('{}'.format(i) for v, i in enumerate(matches)), bold=True))
            if config.auto_confirm:
                django_settings = matches[0]
            else:
                django_settings = input("Where are your project's settings? (default '{}'): ".format(matches[0]))
        else:
            click.echo("(This will likely be something like 'your_project.settings')")
            django_settings = input("Where are your project's settings?: ")
    return django_settings.replace("'", "").replace('"', "")


def prompt_for_flask(config):
    matches = detect_flask_settings()
    if not matches:
        return

    click.echo("It looks like this is a " + click.style("Flask", bold=True) + " application!")
    click.echo("What's the " + click.style("modular path", bold=True) + " to your app's function?")
    click.echo("This will likely be something like 'your_module.app'.")

    while app_function in [None, '']:
        if matches:
            click.echo("We discovered: " + click.style(', '.join('{}'.format(i) for v, i in enumerate(matches)),
                                                       bold=True))
            if config.auto_confirm:
                app_function = matches[0]
            else:
                app_function = input("Where is your app's function? (default '{}'): ".format(matches[0])) or matches[0]
        else:
            app_function = input("Where is your app's function?: ")
    return app_function.replace("'", "").replace('"', "")


def prompt_for_app(config):
    click.echo("What's the " + click.style("modular path", bold=True) + " to your app's function?")
    click.echo("This will likely be something like 'app.app'.")
    if config.auto_confirm:
        click.echo("We are defaulting to 'app.app' because auto-confirm is on.  " +
                   "You can change this later in the settings file if you need too.")
        app_function = 'app.app'
    else:
        app_function = input("Where is your app's function?: ")
    return app_function


def confirm_settings(config, settings):
    # Confirm
    zappa_settings_json = settings.toJSON(sort_keys=True, indent=4)

    click.echo("\nOkay, here's your " + click.style(DEFAULT_SETTINGS_FILE, bold=True) + ":\n")
    click.secho(zappa_settings_json, fg="yellow", bold=False)
    click.echo()

    if not config.auto_confirm:
        confirmed = click.confirm("Does this look " + click.style("okay", bold=True, fg="green") + "?")
        if not confirmed:
            click.echo("" + click.style("Sorry", bold=True, fg='red') + " to hear that! Please init again.")
            raise Abort()

    # Write
    settings.save_json(DEFAULT_SETTINGS_FILE, sort_keys=True)


def _init(config):
    settings = Settings()
    validate_environment(config, api_stage='init')
    print_init_intro()

    env = prompt_for_environment(config)
    settings[env] = Settings()
    bucket = prompt_for_s3_bucket(config)
    settings[env].s3_bucket = bucket

    # Detect Django/Flask
    has_django = detect_package('django')
    has_flask = detect_package('flask')

    # App-specific
    if has_django:  # pragma: no cover
        django_settings = prompt_for_django(config)
        if django_settings is not None:
            settings[env].django_settings = django_settings

    elif has_flask:
        app_function = prompt_for_flask(config)
        if app_function is not None:
            settings[env].app_function = app_function

    if not settings[env].get('django_settings') and not settings[env].get('app_function'):
        settings[env].app_function = prompt_for_app(config)

    # TODO: Create VPC?
    # Memory size? Time limit?

    confirm_settings(config, settings)
    print_init_tail(env)
