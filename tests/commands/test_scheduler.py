from tests.commands.base import CLITestBase
from tests.utils import placebo_session
from zappa.commands.scheduler import _schedule, _unschedule


class TestCLIScheduler(CLITestBase):

    @placebo_session
    def test_schedule(self, session):
        config = self.create_config(boto_session=session)

        _schedule(config, 'ttt888')

    @placebo_session
    def test_unschedule(self, session):
        config = self.create_config(boto_session=session)

        _unschedule(config, 'ttt888')
