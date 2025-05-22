#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
import asyncio
import logging
from pathlib import Path

import pytest
import sh
import yaml

# pyright: reportAttributeAccessIssue = false

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())

karma_image_rev = METADATA["resources"]["karma-image"]["upstream-source"]


@pytest.mark.parametrize("tls_enabled", [False, True], scope="module")
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test, charm_under_test, tls_enabled):
    """Deploy the charm-under-test and deploy it together with related charms."""
    assert ops_test.model
    # GIVEN a karma bundle
    sh.juju.deploy(
        charm_under_test,
        "karma",
        model=ops_test.model.name,
        resource=f"karma-image={karma_image_rev}",
        trust=True,
    )
    sh.juju.deploy(
        "alertmanager-k8s", "alertmanager", model=ops_test.model.name, channel="2/edge", trust=True
    )
    sh.juju.relate("karma:dashboard", "alertmanager", model=ops_test.model.name)
    if tls_enabled:
        sh.juju.deploy("self-signed-certificates", model=ops_test.model.name, channel="edge")
        sh.juju.relate("karma:certificates", "self-signed-certificates", model=ops_test.model.name)
        sh.juju.relate(
            "alertmanager:certificates", "self-signed-certificates", model=ops_test.model.name
        )

    # WHEN the deployment is settled
    # THEN all apps are in active/idle
    await ops_test.model.wait_for_idle(
        status="active", raise_on_error=False, timeout=600, idle_period=30
    )

    # AND karma is able to communicate with alertmanager
    # TODO when karma will have an HTTP API, query it to make sure alertmanager is reachable.


@pytest.mark.abort_on_fail
async def test_remove(ops_test):
    # WHEN the apps are removed
    apps = list(ops_test.model.applications.values())
    logger.info("Removing apps: %s", apps)
    for app in apps:
        await app.destroy(destroy_storage=True, force=False, no_wait=False)

    # THEN no app goes into error state and the model is empty
    # TODO when the app removal Juju bug is fixed, replace the following with a wait_for_idle
    #  with raise_on_error=True and assert len(ops_test.model.applications) == 0

    # Sometimes it take time to remove an app, and sometimes juju never really finishes
    # removing. Sleep for a bit and then forcing removal.
    await asyncio.sleep(30)
    apps = list(ops_test.model.applications.values())
    logger.info("Removing apps forcefully: %s", apps)
    for app in apps:
        await app.destroy(destroy_storage=True, force=True, no_wait=True)
    await ops_test.model.block_until(lambda: len(ops_test.model.applications) == 0)

    # Note: Removing all apps is also needed to clean the model for the next parametrization.
