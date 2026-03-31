import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("CALLBACK_ADDRESS", "localhost:5000")
    monkeypatch.setenv("CAPIF_HOSTNAME", "capif.local")
    monkeypatch.setenv("CAPIF_PORT_HTTP", "8080")
    monkeypatch.setenv("CAPIF_PORT_HTTPS", "8443")
    monkeypatch.setenv("PATH_TO_CERTS", "/certs")
    monkeypatch.setenv("NEF_ADDRESS", "nef.local")
    monkeypatch.setenv("NEF_USER", "testuser")
    monkeypatch.setenv("NEF_PASSWORD", "testpass")
    return monkeypatch


@pytest.fixture
def sample_location_event():
    return {
        "externalId": "ue123@domain.com",
        "type": "log",
        "ipv4Addr": "10.0.0.1",
        "locationInfo": {
            "cellId": "AAAAA1001",
            "ueLocationTimestamp": "2024-01-15T10:30:00Z",
            "age": 0,
        },
    }


@pytest.fixture
def sample_alert_event():
    return {
        "externalId": "ue456@domain.com",
        "type": "alert",
        "ipv4Addr": "10.0.0.2",
        "locationInfo": {
            "cellId": "UNAUTH_CELL",
            "ueLocationTimestamp": "2024-01-15T10:35:00Z",
            "age": 0,
        },
    }


@pytest.fixture
def sample_policy():
    return {"policy_id": "pol_001", "cells": ["AAAAA1001", "AAAAA1002", "AAAAA1003"]}


@pytest.fixture
def mock_netapp_utils():
    with patch("netapp_utils.get_token") as mock:
        mock.return_value = "mock_token_12345"
        yield mock


@pytest.fixture
def mock_evolved5g():
    with patch("evolved5g.sdk.LocationSubscriber") as mock_loc_sub:
        mock_instance = MagicMock()
        mock_loc_sub.return_value = mock_instance
        yield mock_loc_sub
