#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Client library for Karma API."""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


class Karma:
    """Karma HTTP API client.

    A typical usage example would be:
    >>> api = Karma("localhost", 8080)
    >>> version = api.version if api.healthy else None

    Attributes:
        base_url: address, including scheme and port, of the server.
    """

    def __init__(self, address: str = "localhost", port: int = 8080, timeout=2.0):
        """Inits Karma.

        Args:
            address: address of karma server, without scheme or port
            port: karma server api port
            timeout: duration, in seconds, after which requests would return regardless of
            response.
        """
        self.base_url = f"http://{address}:{port}/"
        self.timeout = timeout

    @staticmethod
    def _get(url: str, timeout) -> str:
        """Send a GET request with a timeout."""
        try:
            response = urllib.request.urlopen(url, data=None, timeout=timeout)
            if response.code == 200:
                text = response.read()
            else:
                text = None
        except (ValueError, urllib.error.HTTPError, urllib.error.URLError):
            text = None
        return text

    @property
    def healthy(self) -> bool:
        """Check that the Karma web port is listening."""
        url = urllib.parse.urljoin(self.base_url, "/health")
        return bool(self._get(url, timeout=self.timeout))

    @property
    def version(self) -> str:
        """Retrieve version information from a running Karma server.

        Response looks like this:
            {
              "version": "v0.90",
              "golang": "go1.16.7"
            }
        """
        url = urllib.parse.urljoin(self.base_url, "/version")

        if version_info := self._get(url, timeout=self.timeout):
            logger.info("version_info: %s", version_info)
            version_info = json.loads(version_info)
            karma_version = version_info["version"]
            karma_version_number = karma_version[1:]  # to drop the leading "v"
        else:
            karma_version_number = "0.0.0"

        return karma_version_number
