# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from pytest_operator.plugin import OpsTest

log = logging.getLogger(__name__)


async def get_unit_address(ops_test, app_name: str, unit_num: int) -> str:
    status = await ops_test.model.get_status()  # noqa: F821
    return status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["address"]


async def get_config_values(ops_test, app_name) -> dict:
    """Return the app's config, but filter out keys that do not have a value."""
    config = await ops_test.model.applications[app_name].get_config()
    return {key: config[key]["value"] for key in config if "value" in config[key]}


class IPAddressWorkaround:
    """Context manager for deploying a charm that needs to have its IP address.

    Due to a juju bug, occasionally some charms finish a startup sequence without
    having an ip address returned by `bind_address`.
    https://bugs.launchpad.net/juju/+bug/1929364
    Issuing dummy update_status just to trigger an event, and then restore it.
    """

    def __init__(self, ops_test: OpsTest):
        self.ops_test = ops_test

    async def __aenter__(self):
        """On entry, the update status interval is set to the minimum 10s."""
        config = await self.ops_test.model.get_config()
        self.revert_to = config["update-status-hook-interval"]
        await self.ops_test.model.set_config({"update-status-hook-interval": "10s"})
        return self

    async def __aexit__(self, exc_type, exc_value, exc_traceback):
        """On exit, the update status interval is reverted to its original value."""
        await self.ops_test.model.set_config({"update-status-hook-interval": self.revert_to})
