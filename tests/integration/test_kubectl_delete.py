#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from pathlib import Path

import pytest
import yaml
from helpers import get_config_values, uk8s_group

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
app_name = METADATA["name"]
config = {"external_hostname": "just.a.test"}


@pytest.mark.abort_on_fail
async def test_deploy_from_local_path(ops_test, charm_under_test):
    """Deploy the charm-under-test."""
    logger.debug("deploy local charm")

    resources = {"karma-image": METADATA["resources"]["karma-image"]["upstream-source"]}
    await ops_test.model.deploy(
        charm_under_test, application_name=app_name, resources=resources, trust=True
    )

    await ops_test.model.applications[app_name].set_config(config)
    await ops_test.model.wait_for_idle(apps=[app_name], status="blocked", timeout=1000)


@pytest.mark.abort_on_fail
async def test_config_values_are_retained_after_pod_deleted_and_restarted(ops_test):
    pod_name = f"{app_name}-0"

    cmd = [
        "sg",
        uk8s_group(),
        "-c",
        " ".join(["microk8s.kubectl", "delete", "pod", "-n", ops_test.model_name, pod_name]),
    ]

    logger.debug(
        "Removing pod '%s' from model '%s' with cmd: %s", pod_name, ops_test.model_name, cmd
    )

    retcode, stdout, stderr = await ops_test.run(*cmd)
    assert retcode == 0, f"kubectl failed: {(stderr or stdout).strip()}"
    logger.debug(stdout)
    await ops_test.model.block_until(lambda: len(ops_test.model.applications[app_name].units) > 0)
    await ops_test.model.wait_for_idle(apps=[app_name], status="blocked", timeout=1000)

    assert (await get_config_values(ops_test, app_name)).items() >= config.items()
