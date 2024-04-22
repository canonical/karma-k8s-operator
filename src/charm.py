#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Deploy Karma to a Kubernetes environment."""

import hashlib
import logging
import re
import socket
import subprocess
from pathlib import Path
from time import sleep
from typing import Optional
from urllib.parse import urlparse

import yaml
from charms.catalogue_k8s.v0.catalogue import CatalogueConsumer, CatalogueItem
from charms.karma_k8s.v0.karma_dashboard import KarmaConsumer
from charms.observability_libs.v1.cert_handler import CertHandler
from charms.traefik_k8s.v2.ingress import IngressPerAppRequirer
from karma_client import Karma, KarmaBadResponse
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.pebble import Layer, PathError

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

    KEY_PATH = "/srv/server.key"
    CERT_PATH = "/srv/server.cert"
    CA_CERT_PATH = "/usr/local/share/ca-certificates/karma-ca.crt"

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self._stored.set_default(servers={}, config_hash=None)

        self.karma_consumer = KarmaConsumer(self, "dashboard")
        self.container = self.unit.get_container(self._container_name)
        self.unit.set_ports(self._port)

        # Core lifecycle events
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)
        self.framework.observe(
            self.on.karma_pebble_ready, self._on_pebble_ready  # pyright: ignore
        )
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.stop, self._on_stop)
        self.framework.observe(self.on.update_status, self._on_update_status)

        # Custom events
        self.framework.observe(
            self.karma_consumer.on.alertmanager_config_changed,  # pyright: ignore
            self._on_alertmanager_config_changed,
        )

        self.cert_handler = CertHandler(self, key="am-server-cert")
        self.framework.observe(
            self.cert_handler.on.cert_changed,  # pyright: ignore
            self._on_server_cert_changed,
        )

        self.ingress = IngressPerAppRequirer(
            self,
            "ingress",
            port=self._port,
            scheme=lambda: "https" if self.cert_handler.server_cert else "http",
            redirect_https=True,
            # karma config options do not support reverse proxy with path stripping
            strip_prefix=False,
        )
        self.framework.observe(self.ingress.on.ready, self._handle_ingress)  # pyright: ignore
        self.framework.observe(self.ingress.on.revoked, self._handle_ingress)  # pyright: ignore

        self.catalog = CatalogueConsumer(
            charm=self,
            refresh_event=[
                self.ingress.on.ready,  # pyright: ignore
                self.ingress.on.revoked,  # pyright: ignore
                self.on["ingress"].relation_changed,
                self.on.update_status,
                self.on.config_changed,  # also covers upgrade-charm
            ],
            item=CatalogueItem(
                name="Karma",
                icon="bell-alert",
                url=self._external_url,
                description=(
                    "Karma is a dashboard-like frontend to alertmanager alerts, with handy "
                    "filtering, grouping and silencing capabilities."
                ),
            ),
        )

    @property
    def _internal_url(self) -> str:
        """Return the fqdn dns-based in-cluster (private) address of the karma api server."""
        scheme = "https" if self.cert_handler.server_cert else "http"
        return f"{scheme}://{socket.getfqdn()}:{self._port}"

    @property
    def _external_url(self) -> str:
        """Return the externally-reachable (public) address of the karma api server."""
        return self.ingress.url or self._internal_url

    def _handle_ingress(self, _):
        self._common_exit_hook()

    def _update_certs(self):
        ca_cert_path = Path(self.CA_CERT_PATH)

        for path in [self.KEY_PATH, self.CERT_PATH, self.CA_CERT_PATH]:
            self.container.remove_path(path, recursive=True)

        if self.cert_handler.ca_cert:
            self.container.push(
                self.CA_CERT_PATH,
                self.cert_handler.ca_cert,
                make_dirs=True,
            )
            # Repeat for the charm container. We need it there for grafana client requests.
            ca_cert_path.parent.mkdir(exist_ok=True, parents=True)
            ca_cert_path.write_text(self.cert_handler.ca_cert)

        if self.cert_handler.server_cert and self.cert_handler.private_key:
            self.container.push(
                self.CERT_PATH,
                self.cert_handler.server_cert,
                make_dirs=True,
            )
            self.container.push(
                self.KEY_PATH,
                self.cert_handler.private_key,
                make_dirs=True,
            )

        # TODO: Uncomment when we have a rock with update-ca-certificates
        # self.container.exec(["update-ca-certificates", "--fresh"]).wait()
        subprocess.run(["update-ca-certificates", "--fresh"])

    def _on_server_cert_changed(self, event=None):
        self.ingress.provide_ingress_requirements(
            scheme="https" if self.cert_handler.server_cert else "http", port=self.port
        )
        self._common_exit_hook()

    def _common_exit_hook(self) -> None:
        """Event processing hook that is common to all events to ensure idempotency."""
        if not self.container.can_connect():
            self.unit.status = MaintenanceStatus("Waiting for pod startup to complete")
            return

        if not self.karma_consumer.config_valid:
            self.unit.status = BlockedStatus(
                f"Waiting for 'juju relate {self.app.name} ...' to form a dashboard relation"
            )
            return

        self._update_certs()

        # Update pebble layer
        config_changed = self._update_config()
        layer_changed = self._update_layer(restart=False)
        service_running = (
            service := self.container.get_service(self._service_name)
        ) and service.is_running()
        if layer_changed or config_changed or not service_running:
            if not self._restart_service():
                self.unit.status = BlockedStatus("Service restart failed")
                return

        self.unit.status = ActiveStatus()

    def _update_config(self) -> bool:
        """Update the karma yml config file to reflect changes in configuration.

        Returns:
          True if config changed; False otherwise
        """
        alertmanagers = self.karma_consumer.get_alertmanager_servers()

        # TODO: Drop this for loop when we have a rock with update-ca-certificates
        #  Until then, we need the "ca" entry.
        for am in alertmanagers:
            if self.cert_handler.server_cert:
                am["tls"] = {"ca": self.CA_CERT_PATH}

        prefix = urlparse(self._external_url).path.strip("/")
        config = {
            "alertmanager": {"servers": alertmanagers},
            "listen": {
                "prefix": f"/{prefix}/" if prefix else "/",
                "port": self.port,
                # The TLS section is allowed to have empty entries
                # https://github.com/prymitive/karma/blob/main/docs/CONFIGURATION.md#listen
                "tls": {
                    # Render non-empty values only if we have a cert. The key is assumed to exist.
                    "cert": self.CERT_PATH if self.cert_handler.server_cert else "",
                    "key": self.KEY_PATH if self.cert_handler.server_cert else "",
                },
                # "cors": {"allowedOrigins": [am["uri"] for am in alertmanagers]},
            },
            "log": {
                "config": True,
                "level": "info",
                "format": "text",
                "requests": True,
                "timestamp": False,
            },
        }
        config_yaml = yaml.safe_dump(config)
        config_hash = sha256(config_yaml)

        if config_hash != self._stored.config_hash:  # pyright: ignore
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

    def _on_upgrade_charm(self, _):
        """Event handler for the upgrade event during which we will update the K8s service."""
        # update config hash
        if not self.container.can_connect():
            self._stored.config_hash = ""
        else:
            try:
                config = self.container.pull(self.config_file)
            except PathError:
                self._stored.config_hash = ""
            else:
                self._stored.config_hash = sha256(yaml.safe_dump(yaml.safe_load(config)))

        self._on_server_cert_changed(None)

        # After upgrade (refresh), the unit ip address is not guaranteed to remain the same, and
        # the config may need update. Calling the common hook to update.
        self._common_exit_hook()

    def _on_pebble_ready(self, _):
        """Event handler for PebbleReadyEvent."""
        if version := self._karma_version:
            self.unit.set_workload_version(version)
        else:
            logger.debug("Cannot set workload version at this time: could not get Karma version.")
        self._common_exit_hook()

    def _on_start(self, _):
        """Event handler for StartEvent.

        With Juju 2.9.5 encountered a scenario in which pebble_ready and config_changed fired,
        but IP address was not available and the status was stuck on "Waiting for IP address".
        Adding this hook reduce the likelihood of that scenario.
        """
        self._common_exit_hook()

    def _on_stop(self, _):
        self.unit.set_workload_version("")

    def _on_config_changed(self, _):
        """Event handler for ConfigChangedEvent."""
        self._common_exit_hook()

    def _on_alertmanager_config_changed(self, _):
        """Event handler for :class:`KarmaAlertmanagerConfigChanged`."""
        self._common_exit_hook()

    def _restart_service(self) -> bool:
        """Helper function for restarting the underlying service."""
        logger.info("Restarting service %s", self._service_name)

        if not self.container.can_connect():
            logger.error("Cannot (re)start service: container is not ready.")
            return False

        # Check if service exists, to avoid ModelError from being raised when the service does
        # not yet exist
        if not self.container.get_services().get(self._service_name):
            logger.error("Cannot (re)start service: service does not (yet) exist.")
            return False

        self.container.restart(self._service_name)

        # Assuming FQDN is always part of the SANs DNS.
        self.api = Karma(self._external_url)
        # The `/health` endpoint responds with "Pong" ~1 sec after restart
        for attempt in range(1, 4):
            if self.api.healthy:
                return True
            sleep(attempt)

        logger.error(
            "Service restarted but karma server does not respond well on %s", self.api.base_url
        )
        return False

    def _on_update_status(self, _):
        """Event handler for UpdateStatusEvent.

        Logs list of peers, uptime and version info.
        """
        # Assuming FQDN is always part of the SANs DNS.
        self.api = Karma(self._external_url)

        try:
            version = self.api.version
            logger.info("karma %s is up and running", version)
        except KarmaBadResponse as e:
            logger.error("Failed to obtain status update (is karma running?): %s", str(e))

    @property
    def _karma_version(self) -> Optional[str]:
        """Returns the version of Karma."""
        if not self.container.can_connect():
            return None
        version_output, _ = self.container.exec(["/karma", "--version"]).wait_output()
        # Output looks like this:
        # v0.114
        result = re.search(r"v(\d*(\.\d*)+)", version_output)
        if result is None:
            return None
        return result.group(1)


if __name__ == "__main__":
    main(KarmaCharm)
