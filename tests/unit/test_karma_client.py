#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from karma_client import Karma


class TestKarmaClient(unittest.TestCase):
    def setUp(self):
        self.api = Karma("http://address:12345")

    def test_base_url(self):
        self.assertEqual("http://address:12345", self.api.base_url)

    @patch("karma_client.urllib.request.urlopen")
    def test_healthy(self, urlopen_mock):
        urlopen_mock.return_value.code = 200
        urlopen_mock.return_value.reason = "OK"
        urlopen_mock.return_value.readlines = lambda: "whatever"

        self.assertTrue(self.api.healthy)
        urlopen_mock.assert_called()

    @patch("karma_client.urllib.request.urlopen")
    def test_unhealthy(self, urlopen_mock):
        urlopen_mock.return_value.code = 500
        urlopen_mock.return_value.reason = "OK"
        urlopen_mock.return_value.readlines = lambda: "whatever"

        self.assertFalse(self.api.healthy)
        urlopen_mock.assert_called()
