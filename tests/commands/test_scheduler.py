from mock import Mock
from nose.tools import assert_equals
from tests.commands.base import CLITestBase
from zappa.commands.logs import _tail, fetch_new_logs
from zappa.commands.scheduler import _schedule, _unschedule


class TestCLIScheduler(CLITestBase):
    CONFIGURATION = {
        u'Version': u'$LATEST',
        u'CodeSha256': u'RyI7bX1WRtrXrWfHckLzQ5GkasAtt/tQ0NJeLam6wRk=',
        u'FunctionName': u'hello-dev',
        u'MemorySize': 128,
        u'CodeSize': 5995856,
        u'FunctionArn': u'arn:aws:lambda:us-east-1:611616856832:function:insitome-dev',
        u'Handler': u'handler.lambda_handler',
        u'Role': u'arn:aws:iam::411216846232:role/ZappaLambdaExecution',
        u'Timeout': 30,
        u'LastModified': u'2016-08-22T17:13:14.332+0000',
        u'Runtime': u'python2.7',
        u'Description': u'Zappa Deployment'}

    def test_schedule(self):
        config = self.create_config()
        config._loader.zappa.lambda_client.get_function = Mock(return_value={'Configuration': self.CONFIGURATION})

        _schedule(config, 'ttt888')

        config._loader.zappa.schedule_events.assert_called_once()

    def test_unschedule(self):
        config = self.create_config()
        config._loader.zappa.lambda_client.get_function = Mock(return_value={'Configuration': self.CONFIGURATION})

        _unschedule(config, 'ttt888')

        config._loader.zappa.unschedule_events.assert_called_once()
