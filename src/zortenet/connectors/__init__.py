"""South-bound connectors (minimal Stage-1 versions).

These are thin, requests-based clients with a graceful-degradation contract:
``is_available()`` never raises, and read methods return ``None``/empty on failure rather than
crashing the agent loop. The full connector registry (declared event domains, read/write
capabilities, O-RAN E2, NWDAF) is Stage-2 scope.
"""

from zortenet.connectors.a1_ric import A1PolicyClient
from zortenet.connectors.amarisoft import AmarisoftClient, AmarisoftExecutor
from zortenet.connectors.base import CONNECTOR_CATALOG, ConnectorInfo, catalog
from zortenet.connectors.nwdaf import NWDAFClient
from zortenet.connectors.open5gs import Open5GSClient
from zortenet.connectors.prometheus import PrometheusClient
from zortenet.connectors.ueransim import RunResult, UERANSIMController

__all__ = [
    "A1PolicyClient",
    "AmarisoftClient",
    "AmarisoftExecutor",
    "CONNECTOR_CATALOG",
    "ConnectorInfo",
    "catalog",
    "NWDAFClient",
    "Open5GSClient",
    "PrometheusClient",
    "RunResult",
    "UERANSIMController",
]
