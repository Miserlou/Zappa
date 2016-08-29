from tests.commands.base import CLITestBase
from tests.utils import placebo_session
from zappa.commands.logs import _tail, fetch_new_logs


class TestCLILogs(CLITestBase):

    @placebo_session
    def test_tail(self, session):
        config = self.create_config(boto_session=session)
        config.auto_confirm = True

        _tail(config, 'ttt888', once=True)

    @placebo_session
    def test_fetch_new_logs(self, session):
        config = self.create_config(boto_session=session)
        config.auto_confirm = True

        all_logs = []
        fetch_new_logs(config.loader('ttt888'), all_logs)
