from nose.tools import assert_equals
from tests.commands.base import CLITestConfigBase
from tests.utils import placebo_session
from zappa.commands.function import _invoke, get_invoke_payload


class TestCLIFunction(CLITestConfigBase):

    def test_get_invoke_payload(self):
        result = get_invoke_payload(app_function="app.app")
        assert_equals(result, '{"command": "app.app"}')

        result = get_invoke_payload(app_function="manage", extra_args="check --list-tags")
        assert_equals(result, '{"manage": "check --list-tags"}')

        result = get_invoke_payload(app_function="manage", extra_args=["check", "--list-tags"])
        assert_equals(result, '{"manage": "check --list-tags"}')

    @placebo_session
    def test_invoke(self, session):
        config = self.create_config(boto_session=session)
        settings = config.loader('ttt888').settings

        self.ensure_deployed()

        _invoke(config, 'ttt888', settings.app_function, None)

    @placebo_session
    def test_invoke_manage(self, session):
        config = self.create_config(boto_session=session)

        self.ensure_deployed()

        _invoke(config, 'ttt888', "manage", ["check", "--list-tags"])


