# encoding: utf-8
import os
import sys

from zappa.commands import common, deployment, function, init, logs, scheduler, manage, bash_complete
from zappa.commands.bash_complete import bash_complete_command
from zappa.commands.common import cli  # NOQA
from zappa.commands.manage import django_management_command
from zappa.util import detect_package

program_name = os.path.basename(sys.argv and sys.argv[0] or __file__)
cli.add_command(bash_complete_command(program_name))

if detect_package('django'):
    cli.add_command(django_management_command())
