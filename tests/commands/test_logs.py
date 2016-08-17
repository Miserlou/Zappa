from mock import Mock
from nose.tools import assert_equals
from tests.commands.base import CLITestBase
from zappa.commands.logs import _tail, fetch_new_logs


class TestCLILogs(CLITestBase):
    LOGS = [
        {u'ingestionTime': 1471882747109, u'timestamp': 1471882732032,
         u'message': u"Zappa Event: {u'command': u'mymodule.myfunc'}\n",
         u'eventId': u'32824081769162759823358392683682714266137040635998633984',
         u'logStreamName': u'2016/08/22/[$LATEST]4d95276b79874a0db1b750e213d048a4'},
        {u'ingestionTime': 1471882747109, u'timestamp': 1471882732032,
         u'message': u'Running my function in a schedule!\n',
         u'eventId': u'32824081769162759823358392683682714266137040635998633985',
         u'logStreamName': u'2016/08/22/[$LATEST]4d95276b79874a0db1b750e213d048a4'},
        {u'ingestionTime': 1471882747109, u'timestamp': 1471882732032, u'message': u'Result of mymodule.myfunc:\n',
         u'eventId': u'32824081769162759823358392683682714266137040635998633986',
         u'logStreamName': u'2016/08/22/[$LATEST]4d95276b79874a0db1b750e213d048a4'},
        {u'ingestionTime': 1471882747109, u'timestamp': 1471882732033, u'message': u'None\n',
         u'eventId': u'32824081769185060568556923306824249984409688997504614403',
         u'logStreamName': u'2016/08/22/[$LATEST]4d95276b79874a0db1b750e213d048a4'},
    ]

    def test_tail(self):
        config = self.create_config()
        config.auto_confirm = True
        config._loader.zappa.fetch_logs = Mock(return_value=self.LOGS)

        _tail(config, 'ttt888', once=True)

        config._loader.zappa.fetch_logs.assert_called_once()

    def test_fetch_new_logs(self):
        config = self.create_config()
        config.auto_confirm = True
        config._loader.zappa.fetch_logs = Mock(return_value=self.LOGS)

        all_logs = []
        new_logs = fetch_new_logs(config._loader, all_logs)

        assert_equals(new_logs, self.LOGS)
        assert_equals(all_logs, self.LOGS)
