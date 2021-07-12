# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""
# Karma Library

This library provides the interface needed in order to provide Alertmanager URIs
and associated information to the Karma application.

To have your charm provide URIs to Karma, you need to declare the interface's use in
your charm's metadata.yaml file:

```yaml
provides:
  karmamanagement:
    interface: karma
```

A typical example of including this library might be

```
from charms.alertmanager_karma.v0.karma import KarmaProvides

# in your charm's `__init__` method:

```
self.karmamanagement = KarmaProvides(self, {"name": self.app.name,
                                            "uri": self.config["external_hostname"],
                                           })
```

In config-changed, you can:

```
self.karmamanagement.update_config(
    {"service-hostname": self.config["external_hostname"]}
    )
```
"""

import logging

import ops.charm
from ops.framework import EventBase, EventSource, ObjectEvents
from ops.relation import ConsumerBase, ProviderBase
from ops.framework import StoredState

from typing import List, Dict

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


# Define a custom event "KarmaRelationUpdatedEvent" to be emitted
# when relation change has completed successfully, and handled
# by charm authors.
# See "Notes on defining events" section in docs
# TODO move inside KarmaConsumer class?
class KarmaAvailableEvent(GenericEvent):
    pass


class KarmaProxyEvents(ops.relation.ConsumerEvents):
    karmamanagement_available = EventSource(KarmaAvailableEvent)


class KarmaAlertmanagerProxyChanged(GenericEvent):
    pass


class KarmaProviderEvents(ObjectEvents):
    alertmanager_proxy_changed = EventSource(KarmaAlertmanagerProxyChanged)


class KarmaProvider(ProviderBase):
    on = KarmaProviderEvents()

    def __init__(self, charm, relation_name: str, version: str = None):
        super().__init__(charm, relation_name, relation_name, version)
        self.charm = charm
        self._relation_name = relation_name

        events = self.charm.on[self._relation_name]
        self.framework.observe(events.relation_changed, self._on_relation_changed)
        self.framework.observe(events.relation_departed, self._on_relation_departed)
        self.framework.observe(events.relation_broken, self._on_relation_broken)

    def get_proxied_alertmanagers(self) -> List[Dict[str, str]]:
        alertmanager_ips = []
        for relation in self.charm.model.relations[self._relation_name]:
            # get related application data
            data = None
            for key in relation.data:
                if key is not self.charm.app and isinstance(key, ops.model.Application):
                    data = relation.data[key]
            if data:
                if (name := data.get("name")) and (uri := data.get("uri")):
                    alertmanager_ips.append({"name": name, "uri": uri})
            else:
                logger.error("proxied alertmanagers: no related apps in relation dict")

        return alertmanager_ips  # TODO sorted

    def _on_relation_changed(self, _):
        logger.info("===== RELATION CHANGED =====")
        self.on.alertmanager_proxy_changed.emit()

    def _on_relation_departed(self, _):
        logger.info("===== RELATION DEPARTED =====")
        self.on.alertmanager_proxy_changed.emit()

    def _on_relation_broken(self, _):
        logger.info("===== RELATION BROKEN =====")
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
    """Functionality for the 'requires' side of the 'karma' relation.

    Hook events observed:
      - relation-changed
    """

    on = KarmaProxyEvents()
    _stored = StoredState()

    def __init__(self, charm, relation_name: str, consumes: dict, multi: bool = False):
        super().__init__(charm, relation_name, consumes, multi)
        self.charm = charm
        self._consumer_relation_name = relation_name  # from consumer's metadata.yaml
        self._stored.set_default(config={})

        events = self.charm.on[self._consumer_relation_name]

        self.framework.observe(events.relation_changed, self._on_relation_changed)

    def _update_relation_data(self):
        if not self.model.unit.is_leader():
            return

        for relation in self.charm.model.relations[self._consumer_relation_name]:
            relation.data[self.charm.app].update(self._stored.config)

    def _on_relation_changed(self, _):
        # update app data bag
        self._update_relation_data()
        self.on.karmamanagement_available.emit()

    @property
    def config_valid(self):
        return all(key in self._stored.config for key in ("name", "uri"))

    def store_config(self, config):
        self._stored.config.update(config)
        logger.info("stored config: %s", self._stored.config)

        if self.config_valid:
            self.on.karmamanagement_available.emit()
            self._update_relation_data()
