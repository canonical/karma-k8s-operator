# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

""" # Karma library

This library is designed to be used by a charm consuming or providing the karma-dashboard relation.
"""

import logging

import ops.charm
from ops.framework import EventBase, EventSource, ObjectEvents
from ops.charm import RelationJoinedEvent, RelationDepartedEvent, RelationBrokenEvent
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


class KarmaAlertmanagerConfig:
    required_fields = {"name", "uri"}
    optional_fields = {"cluster"}
    _supported_fields = required_fields | optional_fields

    @staticmethod
    def is_valid(config: Dict[str, str]):
        all_required = all(key in config for key in KarmaAlertmanagerConfig.required_fields)
        all_supported = all(key in KarmaAlertmanagerConfig._supported_fields for key in config)
        return all_required and all_supported

    @staticmethod
    def from_dict(data: Dict[str, str]) -> Dict[str, str]:
        config = {k: data[k] for k in data if k in KarmaAlertmanagerConfig.required_fields}
        optional_config = {
            k: data[k] for k in data if data[k] and k in KarmaAlertmanagerConfig.optional_fields
        }
        config.update(optional_config)
        return config if KarmaAlertmanagerConfig.is_valid(config) else {}

    @staticmethod
    def build(name: str, url: str, *, cluster=None) -> Dict[str, str]:
        # https://github.com/prymitive/karma/blob/main/docs/CONFIGURATION.md#alertmanagers
        return KarmaAlertmanagerConfig.from_dict({"name": name, "uri": url, "cluster": cluster})


class KarmaAlertmanagerConfigChanged(EventBase):
    def __init__(self, handle, data=None):
        super().__init__(handle)
        self.data = data

    def snapshot(self):
        """Save relation data."""
        return {"data": self.data}

    def restore(self, snapshot):
        """Restore relation data."""
        self.data = snapshot["data"]


class KarmaProviderEvents(ObjectEvents):
    alertmanager_config_changed = EventSource(KarmaAlertmanagerConfigChanged)


class KarmaProvider(ProviderBase):
    """A "provider" handler to be used by the Karma charm (the 'provides' side of the 'karma' relation).
    This library offers the interface needed in order to provide Alertmanager URLs and associated information to the
    Karma application.

    To have your charm provide URLs to Karma, declare the interface's use in your charm's metadata.yaml file:

    ```yaml
    provides:
      karma-dashboard:
        interface: karma_dashboard
    ```

    A typical example of importing this library might be

    ```python
    from charms.alertmanager_karma.v0.karma import KarmaProvider
    ```

    In your charm's `__init__` method:

    ```python
    self.provider = KarmaProvider(
        self, "karma-dashboard", "karma", "0.86"
    )
    ```

    The provider charm is expected to observe and respond to the :class:`KarmaAlertmanagerConfigChanged` event,
    for example:

    ```python
    self.framework.observe(
        self.provider.on.alertmanager_config_changed, self._on_alertmanager_config_changed
    )
    ```

    This provider observes relation joined, changed and departed events on behalf of the charm.

    From charm code you can then obtain the list of proxied alertmanagers via:

    ```python
    alertmanagers = self.provider.get_alertmanager_servers()
    ```

    Arguments:
            charm (CharmBase): consumer charm
            name (str): relation name from consumer's metadata.yaml
            service_name (str): service name (must be consistent the consumer)
            version (str): semver-compatible version string

    Attributes:
            charm (CharmBase): consumer charm
    """

    on = KarmaProviderEvents()
    _stored = StoredState()

    def __init__(self, charm, name: str, service_name: str, version: str = None):
        super().__init__(charm, name, service_name, version)
        self.charm = charm
        self._service_name = service_name

        events = self.charm.on[self.name]
        self.framework.observe(events.relation_joined, self._on_relation_joined)
        self.framework.observe(events.relation_changed, self._on_relation_changed)
        self.framework.observe(events.relation_departed, self._on_relation_departed)
        self._stored.set_default(active_relations=set())

    def get_alertmanager_servers(self) -> List[Dict[str, str]]:
        servers = []

        logger.debug("relations for %s: %s", self.name, self.charm.model.relations[self.name])
        for relation in self.charm.model.relations[self.name]:
            if relation.id not in self._stored.active_relations:
                # relation id is not present in the set of active relations
                # this probably means that RelationBroken did not exit yet (was recently removed)
                continue

            # get data from related application
            for key in relation.data:
                if key is not self.charm.unit and isinstance(key, ops.charm.model.Unit):
                    data = relation.data[key]
                    config = KarmaAlertmanagerConfig.from_dict(data)
                    if config and config not in servers:
                        servers.append(config)

        return servers  # TODO sorted

    def _on_relation_joined(self, event: RelationJoinedEvent):
        self._stored.active_relations.add(event.relation.id)
        self.on.alertmanager_config_changed.emit()
        logger.info("REL JOINED: active_relation: %s", self._stored.active_relations)
        logger.info("REL JOINED: relation.data = %s", event.relation.data)

    def _on_relation_changed(self, event):
        self._stored.active_relations.add(event.relation.id)
        self.on.alertmanager_config_changed.emit()
        logger.info("REL CHANGED: active_relation: %s", self._stored.active_relations)
        logger.info("REL CHANGED: relation.data = %s", event.relation.data)

    def _on_relation_departed(self, event: RelationDepartedEvent):
        """Hook is called when a unit leaves, but another unit may still be present"""
        self.on.alertmanager_config_changed.emit()
        logger.info("REL DEPART: active_relation: %s", self._stored.active_relations)
        logger.info("REL DEPART: relation.data = %s", event.relation.data)

    def _on_relation_broken(self, event: RelationBrokenEvent):
        """Hook is called when an application or the relation itself are removed"""
        self._stored.active_relations -= {event.relation.id}
        self.on.alertmanager_config_changed.emit()
        logger.info("REL BROKEN: active_relation: %s", self._stored.active_relations)
        logger.info("REL BROKEN: relation.data = %s", event.relation.data)

    @property
    def config_valid(self) -> bool:
        # karma will fail starting without alertmanager server(s), which would cause pebble to error out.

        # check that there is at least one alertmanager server configured
        servers = self.get_alertmanager_servers()
        logger.info("config_valid: servers = %s", servers)
        return len(servers) > 0


class KarmaConsumer(ConsumerBase):
    """A "consumer" handler to be used by charms that relate to Karma (the 'requires' side of the 'karma' relation).
    This library offers the interface needed in order to provide Alertmanager URLs and associated information to the
    Karma application.

    To have your charm provide URLs to Karma, declare the interface's use in your charm's metadata.yaml file:

    ```yaml
    requires:
      karma-dashboard:
        interface: karma_dashboard
    ```

    A typical example of importing this library might be

    ```python
    from charms.karma_k8s.v0.karma import KarmaConsumer
    ```

    In your charm's `__init__` method:

    ```python
    self.karma_lib = KarmaConsumer(
        self,
        "karma-dashboard",
        consumes={"karma": ">=0.86"},
    )
    ```

    The consumer charm is expected to set the target URL via the consumer library, for example in config-changed:

        self.karma_lib.target = "http://whatever:9093"

    The consumer charm can then obtain the configured IP address, for example:

        self.unit.status = ActiveStatus("Proxying {}".format(self.karma_lib.target))

    Arguments:
            charm (CharmBase): consumer charm
            name (str): from consumer's metadata.yaml
            consumes (dict): provider specifications
            multi (bool): multiple relations flag

    Attributes:
            charm (CharmBase): consumer charm
    """

    _stored = StoredState()

    def __init__(self, charm, name: str, consumes: dict, multi: bool = False):
        super().__init__(charm, name, consumes, multi)
        self.charm = charm

        # StoredState is used for holding the target URL.
        # It is needed here because the target URL may be set by the consumer before any "karma-dashboard" relation is
        # joined, in which case there are no relation unit data bags available for storing the target URL.
        self._stored.set_default(config={})

        events = self.charm.on[self.name]
        self.framework.observe(events.relation_joined, self._on_relation_joined)

    def _on_relation_joined(self, event: RelationJoinedEvent):
        self._update_relation_data(event)

    @property
    def config_valid(self):
        return KarmaAlertmanagerConfig.is_valid(self._stored.config)

    @property
    def target(self) -> Optional[str]:
        return self._stored.config.get("uri", None)

    @target.setter
    def target(self, url: str):
        name = self.charm.unit.name
        cluster = "{}_{}".format(self.charm.model.name, self.charm.app.name)
        if not (config := KarmaAlertmanagerConfig.build(name, url, cluster=cluster)):
            logger.warning("Invalid config: {%s, %s}", name, url)
            return

        self._stored.config.update(config)
        logger.debug("stored karma config: %s", self._stored.config)

        # target changed - must update all relation data
        self._update_relation_data()

    def _update_relation_data(self, event: RelationJoinedEvent = None):
        if event is None:
            # update all existing relation data
            # a single consumer charm's unit may be related to multiple karma dashboards
            if self.name in self.charm.model.relations:
                for relation in self.charm.model.relations[self.name]:
                    relation.data[self.charm.unit].update(self._stored.config)
        else:
            # update relation data only for the newly joined relation
            event.relation.data[self.charm.unit].update(self._stored.config)
