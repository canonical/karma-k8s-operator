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

from ops.charm import RelationBrokenEvent
from ops.framework import EventBase, EventSource
from ops.model import BlockedStatus
from ops.relation import ConsumerBase, ProviderBase


# The unique Charmhub library identifier, never change it
LIBID = "abcdef1234"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 2

logger = logging.getLogger(__name__)


REQUIRED_FIELDS = {
    "name",
    "uri",
}

OPTIONAL_FIELDS = {
    "proxy",
    "readonly",
    "headers",
    "tls",
}


# Define a custom event "KarmaRelationUpdatedEvent" to be emitted
# when relation change has completed successfully, and handled
# by charm authors.
# See "Notes on defining events" section in docs
# TODO move inside KarmaConsumer class?
class KarmaAvailableEvent(EventBase):
    def __init__(self, handle, data=None):
        super().__init__(handle)
        self.data = data

    def snapshot(self):
        """Save relation data."""
        return {"data": self.data}

    def restore(self, snapshot):
        """Restore relation data."""
        self.data = snapshot["data"]


class KarmaProvider(ProviderBase):
    _provider_relation_name = "karmamanagement"
    karmamanagement_available = EventSource(
        KarmaAvailableEvent
    )  # TODO why same name as in consumer

    def __init__(self, charm, service_name: str, version: str = None):
        super().__init__(charm, self._provider_relation_name, service_name, version)
        self.charm = charm
        self._service_name = service_name

        # Set default value for the public port
        # This is needed here to avoid accessing charm constructs directly
        self._port = 8080  # default value

        events = self.charm.on[self._provider_relation_name]

        # Observe the relation-changed hook event and bind
        # self.on_relation_changed() to handle the event.
        self.framework.observe(events.relation_changed, self._on_relation_changed)
        self.framework.observe(events.relation_broken, self._on_relation_broken)

    def _on_relation_changed(self, event):
        """Handle a change to the karma relation.

        Confirm we have the fields we expect to receive."""
        # `self.unit` isn't available here, so use `self.model.unit`.
        if not self.model.unit.is_leader():
            return

        karma_data = {
            field: event.relation.data[event.app].get(field)
            for field in REQUIRED_FIELDS | OPTIONAL_FIELDS
            if event.relation.data[event.app].get(field)
        }

        missing_fields = sorted(
            [field for field in REQUIRED_FIELDS if karma_data.get(field) is None]
        )

        if missing_fields:
            logger.error(
                "Missing required data fields for karma relation: {}".format(
                    ", ".join(missing_fields)
                )
            )
            self.model.unit.status = BlockedStatus(
                "Missing fields for karma: {}".format(", ".join(missing_fields))
            )

        self.charm._stored.servers[event.relation.id] = karma_data
        # Create an event that our charm can use to decide it's okay to
        # configure the karma.
        self.karmamanagement_available.emit()

    def _on_relation_broken(self, event: RelationBrokenEvent):
        """Remove the unit data from local state."""
        self.charm._stored.servers.pop(event.relation.id, None)


class KarmaConsumer(ConsumerBase):
    """Functionality for the 'requires' side of the 'karma' relation.

    Hook events observed:
      - relation-changed
    """

    karmamanagement_available = EventSource(KarmaAvailableEvent)

    def __init__(
        self, charm, relation_name: str, consumes: dict, multi: bool = False, config_dict={}
    ):
        super().__init__(charm, relation_name, consumes, multi)
        self.charm = charm
        self._consumer_relation_name = relation_name  # from consumer's metadata.yaml
        self.config_dict = config_dict

        events = self.charm.on[self._consumer_relation_name]

        self.framework.observe(events.relation_changed, self._on_relation_changed)
        self.framework.observe(events.relation_broken, self._on_relation_broken)

    def _config_dict_errors(self, update_only=False):
        """Check our config dict for errors."""
        blocked_message = "Error in ingress relation, check `juju debug-log`"
        unknown = [x for x in self.config_dict if x not in REQUIRED_FIELDS | OPTIONAL_FIELDS]

        if unknown:
            logger.error(
                "Karma relation error, unknown key(s) in config dictionary found: %s",
                ", ".join(unknown),
            )
            self.model.unit.status = BlockedStatus(blocked_message)

            return True

        if not update_only:
            missing = [x for x in REQUIRED_FIELDS if x not in self.config_dict]

            if missing:
                logger.error(
                    "Karma relation error, missing required key(s) in config " "dictionary: %s ",
                    ", ".join(missing),
                )
                self.model.unit.status = BlockedStatus(blocked_message)

                return True

        return False

    def _on_relation_broken(self, event: RelationBrokenEvent):
        """Remove the unit data from local state."""
        self.charm._stored.related = False
        self.karmamanagement_available.emit()

    def _on_relation_changed(self, event):
        """Handle the relation-changed event."""
        # `self.unit` isn't available here, so use `self.model.unit`.

        if self.model.unit.is_leader():
            if self._config_dict_errors():
                return

            for key in self.config_dict:
                event.relation.data[self.model.app][key] = str(self.config_dict[key])
        self.charm._stored.related = True
        self.karmamanagement_available.emit()

    def update_config(self, config_dict):
        """Allow for updates to relation."""

        if self.model.unit.is_leader():
            self.config_dict = config_dict

            if self._config_dict_errors(update_only=True):
                return
            relation = self.model.get_relation("karma")

            if relation:
                for key in self.config_dict:
                    relation.data[self.model.app][key] = str(self.config_dict[key])
