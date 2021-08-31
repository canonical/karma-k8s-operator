#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Deploy Karma to a Kubernetes environment."""

import hashlib
import logging
from typing import Optional

import yaml
from charms.karma_k8s.v0.karma import KarmaProvider
from charms.nginx_ingress_integrator.v0.ingress import IngressRequires
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.pebble import Layer

from karma_client import Karma, KarmaBadResponse
from kubernetes_service import K8sServicePatch, PatchFailed

logger = logging.getLogger(__name__)


def sha256(hashable) -> str:
    """Use instead of the builtin hash() for repeatable values."""
    if isinstance(hashable, str):
        hashable = hashable.encode("utf-8")
    return hashlib.sha256(hashable).hexdigest()


class KarmaCharm(CharmBase):
    """A Juju charm for Karma."""

    _container_name = "karma"  # automatically determined from charm name
    _layer_name = "karma"  # layer label argument for container.add_layer
    _service_name = "karma"  # chosen arbitrarily to match charm name
    _peer_relation_name = "replicas"  # must match metadata.yaml peer role name
    _port = 8080  # web interface
    config_file = "/srv/karma.yaml"

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self._stored.set_default(servers={}, config_hash=None)
        self.api = Karma(port=self.port)

        try:
            workload_version = self.api.version
        except KarmaBadResponse:
            workload_version = "0.0.0"

        self.provider = KarmaProvider(self, "dashboard", self._service_name, workload_version)
        self.container = self.unit.get_container(self._container_name)

        # Core lifecycle events
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)
        self.framework.observe(self.on.karma_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.update_status, self._on_update_status)

        # Custom events
        self.framework.observe(
            self.provider.on.alertmanager_config_changed, self._on_alertmanager_config_changed
        )

        self.service_hostname = self._external_hostname
        self.ingress = IngressRequires(
            self,
            {
                "service-hostname": self.service_hostname,
                "service-name": self.app.name,
                "service-port": self.port,
            },
        )

    def _common_exit_hook(self) -> None:
        """Event processing hook that is common to all events to ensure idempotency."""
        if not self.container.is_ready():
            self.unit.status = MaintenanceStatus("Waiting for pod startup to complete")
            return

        if not self.provider.config_valid:
            self.unit.status = BlockedStatus(
                "Waiting for a dashboard relation (e.g. alertmanager)"
            )
            return

        # Update pebble layer
        with self.container.is_ready() as c:
            config_changed = self._update_config()
            layer_changed = self._update_layer(restart=False)
            service_running = (
                service := self.container.get_service(self._service_name)
            ) and service.is_running()
            if layer_changed or config_changed or not service_running:
                if not self._restart_service():
                    self.unit.status = BlockedStatus("Service restart failed")
                    return

        if not c.completed:
            logger.error("Alertmanager container not ready")
            self.unit.status = BlockedStatus("Alertmanager container not ready")
            return

        self.provider.ready()
        self.unit.status = ActiveStatus()

    def _update_config(self) -> bool:
        """Update the karma yml config file to reflect changes in configuration.

        Args:
          None

        Returns:
          True if config changed; False otherwise
        """
        alertmanagers = self.provider.get_alertmanager_servers()
        config = {"alertmanager": {"servers": alertmanagers}, "listen": {"port": self.port}}
        config_yaml = yaml.safe_dump(config)
        config_hash = sha256(config_yaml)

        if config_hash != self._stored.config_hash:
            self.container.push(self.config_file, config_yaml)
            self._stored.config_hash = config_hash
            return True

        return False

    def _update_layer(self, restart: bool) -> bool:
        """Update service layer to reflect changes in peers (replicas).

        Args:
          restart: a flag indicating if the service should be restarted if a change was detected.

        Returns:
          True if anything changed; False otherwise
        """
        overlay = self._karma_layer()
        plan = self.container.get_plan()
        is_changed = False

        if self._service_name not in plan.services or overlay.services != plan.services:
            is_changed = True
            self.container.add_layer(self._layer_name, overlay, combine=True)

        if is_changed and restart:
            self._restart_service()

        return is_changed

    @property
    def _external_hostname(self):
        """Return the external hostname to be passed to ingress via the relation."""
        # It is recommended to default to `self.app.name` so that the external
        # hostname will correspond to the deployed application name in the
        # model, but allow it to be set to something specific via config.
        return self.config.get("external_hostname", self.app.name)

    @property
    def port(self):
        """Return the default Karma port."""
        return self._port

    def _karma_layer(self) -> Layer:
        """Returns the Pebble configuration layer for Karma."""
        return Layer(
            {
                "summary": "karma layer",
                "description": "pebble config layer for karma",
                "services": {
                    self._service_name: {
                        "override": "replace",
                        "summary": "karma service",
                        "startup": "enabled",
                        "command": "/karma",
                        "environment": {"CONFIG_FILE": self.config_file},
                    },
                },
            }
        )

    def _on_install(self, _):
        """Event handler for the install event during which we will update the K8s service."""
        self._patch_k8s_service()

    def _on_upgrade_charm(self, _):
        """Event handler for the upgrade event during which we will update the K8s service."""
        # Ensure that older deployments of Karma run the logic to patch the K8s service
        self._patch_k8s_service()

        # update config hash
        with self.container.is_ready() as c:
            self._stored.config_hash = sha256(
                yaml.safe_dump(yaml.safe_load(self.container.pull(self.config_file)))
            )
        if not c.completed:
            self._stored.config_hash = ""

        # After upgrade (refresh), the unit ip address is not guaranteed to remain the same, and
        # the config may need update. Calling the common hook to update.
        self._common_exit_hook()

    def _patch_k8s_service(self):
        """Fix the Kubernetes service that was setup by Juju with correct port numbers."""
        if self.unit.is_leader():
            service_ports = [
                (f"{self.app.name}", self._port, self._port),
            ]
            try:
                K8sServicePatch.set_ports(self.app.name, service_ports)
            except PatchFailed as e:
                logger.error("Unable to patch the Kubernetes service: %s", str(e))
            else:
                logger.debug("Successfully patched the Kubernetes service")

    def _on_pebble_ready(self, _):
        """Event handler for PebbleReadyEvent."""
        self._common_exit_hook()

    def _on_start(self, _):
        """Event handler for StartEvent.

        With Juju 2.9.5 encountered a scenario in which pebble_ready and config_changed fired,
        but IP address was not available and the status was stuck on "Waiting for IP address".
        Adding this hook reduce the likelihood of that scenario.
        """
        self._common_exit_hook()

    def _on_config_changed(self, _):
        """Event handler for ConfigChangedEvent."""
        self._common_exit_hook()

    def _on_alertmanager_config_changed(self, _):
        """Event handler for :class:`KarmaAlertmanagerConfigChanged`."""
        self._common_exit_hook()

    def _restart_service(self) -> bool:
        """Helper function for restarting the underlying service."""
        logger.info("Restarting service %s", self._service_name)

        with self.container.is_ready() as c:
            # Check if service exists, to avoid ModelError from being raised when the service does
            # not yet exist
            if not c.get_services().get(self._service_name):
                logger.error("Cannot (re)start service: service does not (yet) exist.")
                return False

            self.container.restart(self._service_name)

            if not self.api.healthy:
                logger.error("Service restarted but karma server does not respond")
                return False

        if not c.completed:
            logger.error("Cannot (re)start service: container is not ready.")
            return False

        return True

    def _on_update_status(self, _):
        """Event handler for UpdateStatusEvent.

        Logs list of peers, uptime and version info.
        """
        try:
            version = self.api.version
            logger.info("karma %s is up and running", version)
        except KarmaBadResponse as e:
            logger.error("Failed to obtain status update (is karma running?): %s", str(e))

        # Calling the common hook to make sure a single unit set its IP in case all events fired
        # before an IP address was ready, leaving UpdateStatue as the last resort.
        self._common_exit_hook()


if __name__ == "__main__":
    main(KarmaCharm, use_juju_for_storage=True)
