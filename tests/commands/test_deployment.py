from tests.commands.base import CLITestConfigBase
from tests.utils import placebo_session
from zappa.commands.deployment import _deploy, _undeploy, _update, _rollback


class TestCLIDeployment(CLITestConfigBase):

    @placebo_session
    def setUp(self, session):
        self.config = self.create_config(boto_session=session)
        self.loader = self.config.loader('ttt888')
        self.loader.settings.touch = False

    @placebo_session
    def test_01_deploy(self, session):
        config = self.create_config(boto_session=session)
        self.config.auto_confirm = True

        # when using placebo, we have to make sure that we don't already have one deployed...
        self.ensure_not_deployed()
        _deploy(self.config, 'ttt888', None)

    @placebo_session
    def test_02_update(self, session):
        config = self.create_config(boto_session=session)
        config.auto_confirm = True

        # when using placebo, we have to make sure that we already have one deployed...
        self.ensure_deployed()
        _update(self.config, 'ttt888', None)

    @placebo_session
    def test_03_rollback(self, session):
        config = self.create_config(boto_session=session)
        config.auto_confirm = True

        revisions = 1

        # when using placebo, we have to make sure that we already have one deployed...
        self.ensure_deployed()

        _rollback(config, 'ttt888', revisions)

    @placebo_session
    def test_04_undeploy(self, session):
        config = self.create_config(boto_session=session)
        config.auto_confirm = True

        _undeploy(config, 'ttt888')

        # when using placebo, we have to make sure that we already have one deployed...
        self.ensure_deployed()
