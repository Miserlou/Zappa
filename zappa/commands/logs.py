# encoding: utf-8
import os
import sys

import click

from zappa.commands.common import cli


@cli.command()
@click.argument('env', required=False, type=click.STRING)
@click.option('once', '--once', default=False, type=click.BOOL)
@click.pass_context
def tail(ctx, env, once=False):
    """
    Tail this function's logs.

    """
    _tail(ctx.obj, env, once)


def print_logs(logs):
    """
    Parse, filter and print logs to the console.

    """

    for log in logs:
        timestamp = log['timestamp']
        message = log['message']
        if "START RequestId" in message:
            continue
        if "REPORT RequestId" in message:
            continue
        if "END RequestId" in message:
            continue

        print("[" + str(timestamp) + "] " + message.strip())


def fetch_new_logs(loader, all_logs):
    all_logs_again = loader.zappa.fetch_logs(loader.settings.lambda_name)
    new_logs = []
    for log in all_logs_again:
        if log not in all_logs:
            new_logs.append(log)
            all_logs.append(log)
    return new_logs


def _tail(config, env, once=False):
    loader = config.loader(env)
    settings = loader.settings

    try:
        # Tail the available logs
        all_logs = loader.zappa.fetch_logs(settings.lambda_name)
        print_logs(all_logs)
        if once:
            return

        # Keep polling, and print any new logs.
        while True:
            new_logs = fetch_new_logs(loader, all_logs)
            print_logs(new_logs)

    except KeyboardInterrupt:  # pragma: no cover
        # Die gracefully
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(130)  # NOQA
