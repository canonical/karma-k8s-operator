# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import shutil
import tempfile
import unittest

from ops.model import ActiveStatus
from ops.testing import Harness

from charm import KarmaCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(KarmaCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.test_dir = tempfile.mkdtemp()
        self.harness.charm.config_file = f"{self.test_dir}/karma.yaml"

    def tearDown(self):
        """Cleanup temporary dir."""
        shutil.rmtree(self.test_dir)

    def _check_services_running(self, app):
        """Check that the supplied service is running and charm is ActiveStatus."""
        service = self.harness.model.unit.get_container(app).get_service(app)
        self.assertTrue(service.is_running())
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    @unittest.skip("out of date")  # FIXME
    def test_karma_pebble_ready(self, mock_check_karma):
        mock_check_karma.return_value = True
        # Check the initial Pebble plan is empty
        initial_plan = self.harness.get_container_pebble_plan("karma")
        self.assertEqual(initial_plan.to_yaml(), "{}\n")
        # Expected plan after Pebble ready with default config
        expected_plan = {
            "services": {
                "karma": {
                    "override": "replace",
                    "summary": "karma",
                    "startup": "enabled",
                    "command": "/karma",
                    "environment": {"CONFIG_FILE": self.harness.charm.config_file},
                }
            },
        }
        # Get the karma container from the model
        container = self.harness.model.unit.get_container("karma")
        # Emit the PebbleReadyEvent carrying the karma container
        self.harness.charm.on.karma_pebble_ready.emit(container)
        # Get the plan now we've run PebbleReady
        updated_plan = self.harness.get_container_pebble_plan("karma").to_dict()
        # Check we've got the plan we expected
        self.assertEqual(expected_plan, updated_plan)
        # Check the service was started
        # TODO this is actually blocked, when there's no relation
        # self._check_services_running("karma")

    # TODO test for _get_config_file()
    # TODO test for relation
    # TODO tests for karma.py
