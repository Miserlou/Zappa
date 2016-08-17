import click

# from https://github.com/naphatkrit/click-extensions/blob/master/click_extensions/commands.py


def _bash_complete_name(app_name):
    """Given the name of the app, create the equivalent bash-complete
    name. This is the uppercase version of the app name with dashes
    replaced by underscores.

    :param str app_name: the name of the app

    :rtype: str
    :returns: app_name uppercased, with dashes replaced by underscores.
    """
    return app_name.upper().replace('-', '_')


def bash_complete_command(app_name):
    """Return a command that outputs the script that the user can run
    to activate bash completion.

    :param str app_name: the name of the app
    """
    @click.command('bash-complete')
    @click.pass_context
    def bash_complete(ctx):
        """Display the commands to set up bash completion.
        """
        bash_name = _bash_complete_name(app_name)
        click.echo("""
eval "`_{bash_name}_COMPLETE=source {app_name}`"
# Run this command to configure your shell:
# eval `{command}`
""".format(
            bash_name=bash_name,
            app_name=app_name,
            command=ctx.command_path
        ).strip())
    return bash_complete
