#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import urllib.error
import urllib.parse
import urllib.request


class Karma:
    def __init__(self, address: str = "localhost", port: int = 8080, timeout=2.0):
        self.base_url = f"http://{address}:{port}/"
        self.timeout = timeout

    @staticmethod
    def _get(url: str, timeout) -> str:
        """Send a GET request with a timeout"""
        try:
            response = urllib.request.urlopen(url, data=None, timeout=timeout)
            if response.code == 200:
                text = response.readlines()
            else:
                text = None
        except (ValueError, urllib.error.HTTPError):
            text = None
        return text

    @property
    def healthy(self) -> bool:
        """Check that the Karma web port is listening."""
        url = urllib.parse.urljoin(self.base_url, "/health")
        return bool(self._get(url, timeout=self.timeout))
