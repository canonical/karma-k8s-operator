# Copyright 2021 Xav Paice
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import shutil
import tempfile
import unittest
from unittest.mock import Mock

import requests
from charm import AlertmanagerKarmaCharm
from ops.model import ActiveStatus
from ops.testing import Harness


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(AlertmanagerKarmaCharm)
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

    @unittest.mock.patch.object(AlertmanagerKarmaCharm, "_check_karma_service_alive")
    def test_config_changed(self, mock_check_karma):
        mock_check_karma.return_value = True
        alertmanager_servers = "test http://1.2.3.4:1234"
        self.harness.update_config({"alertmanager-servers": alertmanager_servers})
        updated_plan = self.harness.get_container_pebble_plan("karma").to_dict()
        expected_plan = {
            "services": {
                "karma": {
                    "override": "replace",
                    "summary": "karma",
                    "startup": "enabled",
                    "command": "/karma",
                    "environment": {
                        "CONFIG_FILE": self.harness.charm.config_file,
                    },
                }
            },
        }
        self.assertEqual(expected_plan, updated_plan)
        # read the config file, check the uri is changed
        with open(self.harness.charm.config_file, "r") as f:
            written_config = f.read()
        self.assertTrue("http://1.2.3.4:1234" in written_config)
        self._check_services_running("karma")

    @unittest.mock.patch.object(requests.Session, "get")
    def test_check_karma_service_alive(self, mock_requests):
        mockresponse = Mock()
        mockresponse.text = "Pong\n"
        mockresponse.status_code = 200
        mock_requests.return_value = mockresponse
        alive = self.harness.charm._check_karma_service_alive()
        self.assertTrue(alive)

    @unittest.mock.patch.object(AlertmanagerKarmaCharm, "_check_karma_service_alive")
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
                    "environment": {
                        "CONFIG_FILE": self.harness.charm.config_file,
                    },
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
        # read the config file, check the uri is default
        with open(self.harness.charm.config_file, "r") as f:
            written_config = f.read()
        self.assertTrue("https://alertmanager.demo.do.prometheus.io" in written_config)
        # Check the service was started
        self._check_services_running("karma")
