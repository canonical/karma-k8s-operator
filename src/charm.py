#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Deploy Karma to a Kubernetes environment."""

from charms.karma_k8s.v0.karma import KarmaProvider
from charms.nginx_ingress_integrator.v0.ingress import IngressRequires

import ops
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.pebble import ChangeError

from kubernetes_service import K8sServicePatch, PatchFailed
from typing import Optional, Dict, Any
import logging
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import yaml
import hashlib

logger = logging.getLogger(__name__)


def sha256(hashable) -> str:
    """Use instead of the builtin hash() for repeatable values"""
    if isinstance(hashable, str):
        hashable = hashable.encode("utf-8")
    return hashlib.sha256(hashable).hexdigest()


class AlertmanagerKarmaCharm(CharmBase):
    _container_name = "karma"  # automatically determined from charm name
    _layer_name = "karma"  # layer label argument for container.add_layer
    _service_name = "karma"  # chosen arbitrarily to match charm name
    _peer_relation_name = "replicas"  # must match metadata.yaml peer role name
    port = 8080  # web interface
    config_file = "/srv/karma.yaml"

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.container = self.unit.get_container(self._container_name)

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)

        self.framework.observe(self.on.karma_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.start, self._on_start)

        self._stored.set_default(servers={}, pebble_ready=False, config_hash=None)

        # TODO obtain version from karma (if ever gets added to its HTTP API)
        self.provider = KarmaProvider(self, "dashboard", self._service_name, "0.86")
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

    @property
    def peer_relation(self) -> Optional[ops.model.Relation]:
        # Returns None if called too early, e.g. during install.
        return self.model.get_relation(self._peer_relation_name)

    @property
    def private_address(self) -> Optional[str]:
        """Get the unit's ip address.

        Returns:
          None if no IP is available (called before unit "joined"); unit's ip address otherwise
        """
        if bind_address := self.model.get_binding(self.peer_relation).network.bind_address:
            bind_address = str(bind_address)
        return bind_address

    def _common_exit_hook(self) -> bool:
        if not self._stored.pebble_ready:
            self.unit.status = MaintenanceStatus("Waiting for pod startup to complete")
            return False

        # Wait for IP address. IP address is needed for config hot-reload and status updates.
        if not self.private_address:
            self.unit.status = MaintenanceStatus("Waiting for IP address")
            return False

        if not self.provider.config_valid:
            self.unit.status = BlockedStatus("Waiting for a dashboard relation")
            return False

        # Update pebble layer
        try:
            config_changed = self._update_config()
            layer_changed = self._update_layer(restart=False)
            if layer_changed or config_changed or not self.is_service_running:
                if not self._restart_service():
                    self.unit.status = BlockedStatus("Service restart failed")
                    return False

        except ChangeError as e:
            logger.error("Pebble error: %s", str(e))
            self.unit.status = BlockedStatus("Pebble error")
            return False

        self.provider.ready()
        self.unit.status = ActiveStatus()

        return True

    def _update_config(self) -> bool:
        """Update the karma yml config file to reflect changes in configuration.
        Args:
          None
        Returns:
          True if config changed; False otherwise
        """
        alertmanagers = self.provider.get_alertmanager_servers()
        config = {
            "alertmanager": {"servers": alertmanagers},
            "listen": {"port": self.port},
        }
        config_yaml = yaml.safe_dump(config)
        config_hash = sha256(config_yaml)

        config_changed = False
        if config_hash != self._stored.config_hash:
            self.container.push(self.config_file, config_yaml)
            self._stored.config_hash = config_hash
            config_changed = True

        return config_changed

    def _update_layer(self, restart: bool = True) -> bool:
        """Update service layer to reflect changes in peers (replicas).
        Args:
          restart: a flag indicating if the service should be restarted if a change was detected.
        Returns:
          True if anything changed; False otherwise
        """
        overlay = self._karma_layer()

        plan = self.container.get_plan()

        is_changed = False
        # if this unit has just started, the services does not yet exist - using "get"
        service = plan.services.get(self._service_name)
        overlay_command = overlay["services"][self._service_name]["command"]
        overlay_environment = overlay["services"][self._service_name]["environment"]

        if service is None or any(
            [service.command != overlay_command, service.environment != overlay_environment]
        ):
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

        return self.config["external_hostname"] or f"{self.app.name}.juju"

    @property
    def _port(self):
        """Return the default Karma port."""
        return 8080

    def _karma_layer(self) -> Dict[str, Any]:
        """Returns the Pebble configuration layer for Karma."""
        return {
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

    def _on_install(self, _):
        """Event handler for the install event during which we will update the K8s service"""
        self._patch_k8s_service()

    def _on_upgrade_charm(self, _):
        """Event handler for the upgrade_charm event during which we will update the K8s service"""
        self._patch_k8s_service()

    def _patch_k8s_service(self):
        """Fix the Kubernetes service that was setup by Juju with correct port numbers"""
        if self.unit.is_leader():
            service_ports = [
                (f"{self.app.name}", self._port, self._port),
            ]
            try:
                K8sServicePatch.set_ports(self.app.name, service_ports)
            except PatchFailed as e:
                logger.error("Unable to patch the Kubernetes service: %s", str(e))
            else:
                logger.info("Successfully patched the Kubernetes service")

    def _on_pebble_ready(self, event):
        self._stored.pebble_ready = True
        self._common_exit_hook()

    def _on_start(self, _):
        # With Juju 2.9.5 encountered a scenario in which pebble_ready and config_changed fired, but IP address was not
        # available and the status was stuck on "Waiting for IP address". Adding this hook as a workaround.
        self._common_exit_hook()

    def _check_karma_service_alive(self) -> bool:
        """Check that the Karma web port is listening."""
        retry_strategy = Retry(total=3, backoff_factor=1)
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
        self._common_exit_hook()

    def _on_alertmanager_config_changed(self, _):
        self._common_exit_hook()

    @property
    def is_service_running(self) -> bool:
        """Helper function for checking if the alertmanager service is running.
        Returns:
          True if the service is running; False otherwise.
        Raises:
          ModelError: If the service is not defined (e.g. layer does not exist).
        """
        return self.container.get_service(self._service_name).is_running()

    def _restart_service(self) -> bool:
        logger.info("Restarting service %s", self._service_name)

        try:
            # if the service does not exist, ModelError will be raised
            if self.is_service_running:
                self.container.stop(self._service_name)
            self.container.start(self._service_name)

            if self._check_karma_service_alive():
                return True
            else:
                logger.warning("Service restarted but karma server does not respond")
                return False

        except ops.model.ModelError:
            logger.warning("Service does not (yet?) exist; (re)start aborted")
            return False
        except ChangeError as e:
            logger.error("ChangeError: failed to (re)start service: %s", str(e))
            return False
        except Exception as e:
            logger.error("failed to (re)start service: %s", str(e))
            raise


if __name__ == "__main__":
    main(AlertmanagerKarmaCharm, use_juju_for_storage=True)
