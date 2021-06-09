#!/usr/bin/env python3
# Copyright 2021 Xav Paice
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

    https://discourse.charmhub.io/t/4208
"""

import logging
from urllib.parse import urlparse

import requests
import yaml
from charms.nginx_ingress_integrator.v0.ingress import IngressRequires
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, UnknownStatus
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class AlertmanagerKarmaCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.karma_pebble_ready, self._on_karma_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self._stored.set_default(things=[])
        self.port = 8080
        self.service_hostname = "karma.juju"
        self.config_file = "/srv/karma.yaml"
        self.ingress = IngressRequires(
            self,
            {
                "service-hostname": self.service_hostname,
                "service-name": self.app.name,
                "service-port": self.port,
            },
        )

    def _karma_layer(self):
        """Returns the Pebble configuration layer for Karma."""
        pebble_layer = {
            "summary": "karma layer",
            "description": "pebble config layer for karma",
            "services": {
                "karma": {
                    "override": "replace",
                    "summary": "karma",
                    "startup": "enabled",
                    "command": "/karma",
                    "environment": {
                        "CONFIG_FILE": self.config_file,
                    },
                },
            },
        }

        return pebble_layer

    def _on_karma_pebble_ready(self, event):
        """Define and start a workload using the Pebble API."""
        # Get a reference the container attribute on the PebbleReadyEvent
        container = event.workload
        # Define an initial Pebble layer configuration
        # Add intial Pebble config layer using the Pebble API
        container.add_layer("karma", self._karma_layer(), combine=True)
        self._write_config_file()
        self._restart_service(container, "karma")

    def _check_karma_service_alive(self) -> bool:
        """Check that the Karma web port is listening."""
        retry_strategy = Retry(total=3, backoff_factor=1, allowed_methods=["GET"])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        http = requests.Session()
        http.mount("https://", adapter)
        http.mount("http://", adapter)
        r = http.get("http://localhost:{}/health".format(self.port), timeout=3)

        if r.status_code == 200 and r.text == "Pong\n":
            return True
        else:
            return False

    def _on_config_changed(self, _):
        """Handle the config-changed event"""
        container = self.unit.get_container("karma")
        # Create a new config layer
        layer = self._karma_layer()
        # Get the current config
        plan = container.get_plan()
        # Check if there are any changes to services

        if plan.services != layer["services"]:
            # Changes were made, add the new layer
            container.add_layer("karma", layer, combine=True)
            logging.info("Added updated layer 'karma' to Pebble plan")
        self._write_config_file()
        self._restart_service(container, "karma")

    def _write_config_file(self):
        """Write out a config file."""
        servers = []

        for server in self.model.config["alertmanager-servers"].split(","):
            # TODO deal with errors like multiple whitespace
            try:
                name, uri = server.split(" ")
            except ValueError as e:
                self.unit.status = BlockedStatus(
                    message="Loading alertmanager-servers failed"
                )
                logging.error(f"Loading alertmanager-servers failed with: {e}")

                return False
            # check the uri looks like a uri
            try:
                parsed_uri = urlparse(uri)
            except Exception as e:
                self.unit.status = BlockedStatus(
                    message="Loading alertmanager-servers failed"
                )
                logging.error(f"Loading alertmanager-servers failed with: {e}")

                return False

            if not all([parsed_uri.scheme, parsed_uri.netloc]):
                self.unit.status = BlockedStatus(
                    message=f"URI setting {uri} is invalid"
                )
                logging.error(f"URI setting {uri} is invalid")
            servers.append({"name": name, "uri": uri, "proxy": True})

        config = {
            "alertmanager": {
                "servers": servers,
            },
            "listen": {"port": self.port},
        }
        with open(self.config_file, "w") as f:
            f.write(yaml.dump(config))

        return True

    def _restart_service(self, container, service):
        """Perform a service restart on the container."""

        if container.get_service(service).is_running():
            container.stop(service)
        # Restart it and report a new status to Juju
        container.start(service)
        logging.info(f"Restarted service: {service}")
        # workaround for https://github.com/canonical/pebble/issues/46

        if self._check_karma_service_alive():
            self.unit.status = ActiveStatus()
        else:
            self.unit.status = UnknownStatus()


if __name__ == "__main__":
    main(AlertmanagerKarmaCharm)
