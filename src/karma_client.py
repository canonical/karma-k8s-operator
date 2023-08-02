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


class KarmaBadResponse(RuntimeError):
    """A catch-all exception type to indicate 'no reply', regardless the reason."""


class Karma:
    """Karma HTTP API client.

    A typical usage example would be:
    >>> api = Karma("http://localhost:8080")
    >>> version = api.version if api.healthy else None

    Attributes:
        base_url: address, including scheme and port, of the server.
    """

    def __init__(self, endpoint_url: str = "http://localhost:8080", timeout=2.0):
        """Inits Karma.

        Args:
            endpoint_url: URL of karma server, including scheme and port
            timeout: duration, in seconds, after which requests would return regardless of
            response.
        """
        self.base_url = endpoint_url.rstrip("/")
        self.timeout = timeout

    @staticmethod
    def _get(url: str, timeout: float) -> str:
        """Send a GET request with a timeout.

        Args:
            url: target url to GET from
            timeout: duration in seconds after which to return, regardless the result

        Raises:
            AlertmanagerBadResponse: If no response or invalid response, regardless the reason.
        """
        try:
            response = urllib.request.urlopen(url, data=None, timeout=timeout)
            if response.code == 200:
                return response.read()
            raise KarmaBadResponse(
                f"Bad response (code={response.code}, reason={response.reason})"
            )
        except (ValueError, urllib.error.HTTPError, urllib.error.URLError) as e:
            raise KarmaBadResponse("Bad response") from e

    @property
    def healthy(self) -> bool:
        """Check that the Karma web port is listening."""
        url = f"{self.base_url}/health"
        try:
            return bool(self._get(url, timeout=self.timeout))
        except KarmaBadResponse:
            return False

    @property
    def version(self) -> str:
        """Retrieve version information from a running Karma server.

        Response looks like this:
            {
              "version": "v0.90",
              "golang": "go1.16.7"
            }
        """
        url = f"{self.base_url}/version"

        try:
            version_info = json.loads(self._get(url, timeout=self.timeout))
            karma_version = version_info["version"]
            karma_version_number = karma_version[1:]  # to drop the leading "v"
            return karma_version_number
        except KeyError as e:
            raise KarmaBadResponse("Unexpected response") from e
