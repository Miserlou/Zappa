from click import ClickException
from nose.tools import assert_equals, raises
from tests.commands.base import CLITestBase
from tests.utils import placebo_session
from zappa.commands.cli_utils import METRIC_NAMES
from zappa.commands.status import get_lambda_configuration, get_lambda_metrics_by_name, _status, get_error_rate


class TestCLIStatus(CLITestBase):

    @placebo_session
    def test_get_lambda_configuration(self, session):
        config = self.create_config(boto_session=session)
        loader = config.loader('ttt888')

        get_lambda_configuration(loader.zappa, loader.settings.lambda_name)

    def test_lambda_metrics_by_name(self):
        for metric in METRIC_NAMES:
            yield self.lambda_metrics_by_name, metric

    @placebo_session
    def lambda_metrics_by_name(self, metric, session):
        config = self.create_config(boto_session=session)
        loader = config.loader('ttt888')

        get_lambda_metrics_by_name(loader.zappa, metric=metric, lambda_name=loader.settings.lambda_name)

    @raises(ClickException)
    @placebo_session
    def test_lambda_metrics_by_bad_name(self, session):
        config = self.create_config(boto_session=session)
        loader = config.loader('ttt888')

        # should raise an exception if not in METRIC_NAMES
        get_lambda_metrics_by_name(loader.zappa, metric="bob", lambda_name=loader.settings.lambda_name)

    def test_get_error_rate(self):
        assert_equals(get_error_rate(0, 0), 0)
        assert_equals(get_error_rate(10, 0), "Error calculating")
        assert_equals(get_error_rate(10, 10), "100%")
        assert_equals(get_error_rate(10, 5), "200%")
        assert_equals(get_error_rate(5, 10), "50%")

    @placebo_session
    def test_status(self, session):
        config = self.create_config(boto_session=session)

        _status(config, 'ttt888')
