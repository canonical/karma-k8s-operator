#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Deploy Karma to a Kubernetes environment."""

import logging

import requests
import yaml
from charms.alertmanager_karma.v0.karma import KarmaProvider
from charms.nginx_ingress_integrator.v0.ingress import IngressRequires
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, UnknownStatus
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# from urllib.parse import urlparse


logger = logging.getLogger(__name__)


class AlertmanagerKarmaCharm(CharmBase):
    _container_name = "karma"  # automatically determined from charm name
    _layer_name = "karma"  # layer label argument for container.add_layer
    _service_name: str = "karma"  # chosen arbitrarily to match charm name
    port = 8080  # web interface

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.container = self.unit.get_container(self._container_name)

        self.framework.observe(self.on.karma_pebble_ready, self._on_karma_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        self._stored.set_default(servers={})

        # TODO fetch version from karma container
        self.provider = KarmaProvider(self, "karma", "0.0.1")
        self.framework.observe(self.provider.karmamanagement_available, self._on_config_changed)

        self.service_hostname = self._external_hostname
        self.config_file = "/srv/karma.yaml"
        self.ingress = IngressRequires(
            self,
            {
                "service-hostname": self.service_hostname,
                "service-name": self.app.name,
                "service-port": self.port,
            },
        )

    @property
    def _external_hostname(self):
        """Return the external hostname to be passed to ingress via the relation."""
        # It is recommended to default to `self.app.name` so that the external
        # hostname will correspond to the deployed application name in the
        # model, but allow it to be set to something specific via config.

        return self.config["external_hostname"] or f"{self.app.name}.juju"

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
                    "environment": {"CONFIG_FILE": self.config_file},
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
        container.add_layer(self._layer_name, self._karma_layer(), combine=True)
        config = self._get_config_file()

        if config:
            container.push(self.config_file, config)
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
            container.add_layer(self._layer_name, layer, combine=True)
            logging.info("Added updated layer 'karma' to Pebble plan")
        config = self._get_config_file()

        if config:
            container.push(self.config_file, config)
            self._restart_service(container, "karma")

    def _get_config_file(self):
        """Return a string to write to a Karma config file."""

        if len(self._stored.servers.keys()) == 0:
            self.unit.status = BlockedStatus(message="Waiting for Karma relation.")
            logging.info("No relations found for Karma, no Alertmanager URIs to view.")

            return False

        # self._stored.servers is a special type ops.framework.StoredDict which can't
        # be turned to a string by yaml.dump, so here we convert it.
        serverlist = []

        for server in [self._stored.servers[s] for s in self._stored.servers.keys()]:
            serverlist.append({s: server[s] for s in server.keys()})

        config = {
            "alertmanager": {"servers": serverlist},
            "listen": {"port": self.port},
        }

        return yaml.dump(config)

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
    main(AlertmanagerKarmaCharm, use_juju_for_storage=True)
