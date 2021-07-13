# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

""" # Karma library

This library is designed to be used by a charm consuming or providing the karmamanagement relation.
"""

import logging

import ops.charm
from ops.framework import EventBase, EventSource, ObjectEvents
from ops.charm import RelationJoinedEvent, RelationDepartedEvent
from ops.relation import ConsumerBase, ProviderBase
from ops.framework import StoredState

from typing import List, Dict, Optional

# The unique Charmhub library identifier, never change it
LIBID = "abcdef1234"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 2

logger = logging.getLogger(__name__)


class GenericEvent(EventBase):
    def __init__(self, handle, data=None):
        super().__init__(handle)
        self.data = data

    def snapshot(self):
        """Save relation data."""
        return {"data": self.data}

    def restore(self, snapshot):
        """Restore relation data."""
        self.data = snapshot["data"]


class KarmaAlertmanagerProxyChanged(GenericEvent):
    pass


class KarmaProviderEvents(ObjectEvents):
    alertmanager_proxy_changed = EventSource(KarmaAlertmanagerProxyChanged)


class KarmaProvider(ProviderBase):
    """A "provider" handler to be used by the Karma charm (the 'provides' side of the 'karma' relation).
    This library offers the interface needed in order to provide Alertmanager URIs and associated information to the
    Karma application.

    To have your charm provide URIs to Karma, declare the interface's use in your charm's metadata.yaml file:

    ```yaml
    provides:
      karmamanagement:
        interface: karma
    ```

    A typical example of importing this library might be

    ```python
    from charms.alertmanager_karma.v0.karma import KarmaProvider
    ```

    In your charm's `__init__` method:

    ```python
    self.provider = KarmaProvider(
        self, "karmamanagement", "karma", "0.0.1"
    )
    ```

    The provider charm is expected to observe and respond to the :class:`KarmaAlertmanagerProxyChanged` event,
    for example:

    ```python
    self.framework.observe(
        self.provider.on.alertmanager_proxy_changed, self._on_alertmanager_proxy_changed
    )
    ```

    This provider observes relation joined, changed and departed events on behalf of the charm.

    From charm code you can then obtain the list of proxied alertmanagers via:

    ```python
    alertmanagers = self.provider.get_proxied_alertmanagers()
    ```

    Arguments:
            charm (CharmBase): consumer charm
            relation_name (str): from consumer's metadata.yaml
            service_name (str): service name (must be consistent the consumer)
            version (str): semver-compatible version string

    Attributes:
            charm (CharmBase): consumer charm
    """

    on = KarmaProviderEvents()
    _stored = StoredState()

    def __init__(self, charm, relation_name: str, service_name: str, version: str = None):
        super().__init__(charm, relation_name, service_name, version)
        self.charm = charm
        self._relation_name = relation_name
        self._service_name = service_name

        events = self.charm.on[self._relation_name]
        self.framework.observe(events.relation_joined, self._on_relation_joined)
        self.framework.observe(events.relation_changed, self._on_relation_changed)
        self.framework.observe(events.relation_departed, self._on_relation_departed)
        self._stored.set_default(active_relations=set())

    def get_proxied_alertmanagers(self) -> List[Dict[str, str]]:
        alertmanager_ips = []

        for relation in self.charm.model.relations[self._relation_name]:
            if relation.id not in self._stored.active_relations:
                # relation id is not present in the set of active relations
                # this probably means that RelationBroken did not exit yet (was recently removed)
                continue

            # get related application data
            data = None
            for key in relation.data:
                if key is not self.charm.app and isinstance(key, ops.charm.model.Application):
                    data = relation.data[key]
            if data:
                if (name := data.get("name")) and (uri := data.get("uri")):
                    alertmanager_ips.append({"name": name, "uri": uri})
            else:
                logger.error("proxied alertmanagers: no related apps in relation dict")

        return alertmanager_ips  # TODO sorted

    def _on_relation_joined(self, event: RelationJoinedEvent):
        self._stored.active_relations.add(event.relation.id)

    def _on_relation_changed(self, _):
        self.on.alertmanager_proxy_changed.emit()

    def _on_relation_departed(self, event: RelationDepartedEvent):
        self._stored.active_relations -= {event.relation.id}
        self.on.alertmanager_proxy_changed.emit()

    @property
    def config_valid(self) -> bool:
        # karma will fail starting without alertmanager server(s), which would cause pebble to error out.

        # check that there is at least one alertmanager server configured
        servers = self.get_proxied_alertmanagers()
        if len(servers) == 0:
            return False

        # check that at least one of the entries has the expected keys
        valid = False
        for server in servers:
            if server.get("name") and server.get("uri"):
                valid = True
                break
        return valid


class KarmaConsumer(ConsumerBase):
    """A "consumer" handler to be used by charms that relate to Karma (the 'requires' side of the 'karma' relation).
    This library offers the interface needed in order to provide Alertmanager URIs and associated information to the
    Karma application.

    To have your charm provide URIs to Karma, declare the interface's use in your charm's metadata.yaml file:

    ```yaml
    requires:
      karmamanagement:
        interface: karma
    ```

    A typical example of importing this library might be

    ```python
    from charms.alertmanager_karma.v0.karma import KarmaConsumer
    ```

    In your charm's `__init__` method:

    ```python
    self.karma_lib = KarmaConsumer(
        self,
        "karmamanagement",
        consumes={"karma": ">=0.0.1"},
    )
    ```

    The consumer charm is expected to set config via the consumer library, for example in config-changed:

        if not self.karma_lib.set_config(config):
            logger.warning("Invalid config: %s", config)

    The consumer charm can then obtain the configured IP address, for example:

        self.unit.status = ActiveStatus("Proxying {}".format(self.karma_lib.ip_address))

    Arguments:
            charm (CharmBase): consumer charm
            relation_name (str): from consumer's metadata.yaml
            consumes (dict): provider specifications
            multi (bool): multiple relations flag

    Attributes:
            charm (CharmBase): consumer charm
    """

    _stored = StoredState()

    def __init__(self, charm, relation_name: str, consumes: dict, multi: bool = False):
        super().__init__(charm, relation_name, consumes, multi)
        self.charm = charm
        self._consumer_relation_name = relation_name  # from consumer's metadata.yaml
        self._stored.set_default(config={})

        events = self.charm.on[self._consumer_relation_name]

        self.framework.observe(events.relation_joined, self._on_relation_joined)

    def _on_relation_joined(self, event: RelationJoinedEvent):
        if not self.model.unit.is_leader():
            return

        # update app data bag
        event.relation.data[self.charm.app].update(self._stored.config)

    @staticmethod
    def _is_config_valid(config: Dict[str, str]):
        return all(key in config for key in ("name", "uri"))

    @property
    def config_valid(self):
        return self._is_config_valid(self._stored.config)

    @property
    def ip_address(self) -> Optional[str]:
        return self._stored.config.get("uri", None)

    def set_config(self, config) -> bool:
        if not self._is_config_valid(config):
            return False

        self._stored.config.update(config)
        logger.info("stored config: %s", self._stored.config)

        if not self.model.unit.is_leader():
            return True

        for relation in self.charm.model.relations[self._consumer_relation_name]:
            relation.data[self.charm.app].update(self._stored.config)

        return True
