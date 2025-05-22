#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
import asyncio
import logging
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace

import pytest
import yaml
from helpers import deploy_literal_bundle

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())

am = SimpleNamespace(name="am", charm="alertmanager-k8s", scale=1)
ca = SimpleNamespace(name="ca", charm="self-signed-certificates", scale=1)
karma = SimpleNamespace(name="karma", scale=1)


def bundle_under_test(charm_under_test, tls_enabled: bool) -> str:
    without_tls = dedent(
        f"""
        ---
        bundle: kubernetes
        applications:
          {karma.name}:
            charm: {charm_under_test}
            scale: {karma.scale}
            trust: true
            resources:
              karma-image: {METADATA["resources"]["karma-image"]["upstream-source"]}
          {am.name}:
            charm: {am.charm}
            channel: 2/edge
            scale: {am.scale}
            trust: true
        relations:
        - [{karma.name}:dashboard, {am.name}:karma-dashboard]
        """
    )

    with_tls = dedent(
        f"""
        ---
        bundle: kubernetes
        applications:
          {karma.name}:
            charm: {charm_under_test}
            scale: {karma.scale}
            trust: true
            resources:
              karma-image: {METADATA["resources"]["karma-image"]["upstream-source"]}
          {am.name}:
            charm: {am.charm}
            channel: 2/edge
            scale: {am.scale}
            trust: true
          {ca.name}:
            charm: {ca.charm}
            channel: edge
            scale: {ca.scale}
        relations:
        - [{am.name}:certificates, {ca.name}:certificates]
        - [{karma.name}:certificates, {ca.name}:certificates]
        - [{karma.name}:dashboard, {am.name}:karma-dashboard]
        """
    )

    return with_tls if tls_enabled else without_tls


@pytest.mark.parametrize("tls_enabled", [False, True], scope="module")
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test, charm_under_test, tls_enabled):
    """Deploy the charm-under-test and deploy it together with related charms."""
    # GIVEN a karma bundle
    await deploy_literal_bundle(ops_test, bundle_under_test(charm_under_test, tls_enabled))

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
