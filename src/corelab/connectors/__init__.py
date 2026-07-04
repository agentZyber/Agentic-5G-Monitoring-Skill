"""South-bound connectors (minimal Stage-1 versions).

These are thin, requests-based clients with a graceful-degradation contract:
``is_available()`` never raises, and read methods return ``None``/empty on failure rather than
crashing the agent loop. The full connector registry (declared event domains, read/write
capabilities, O-RAN E2, NWDAF) is Stage-2 scope.
"""

from corelab.connectors.a1_ric import A1PolicyClient
from corelab.connectors.amarisoft import AmarisoftClient, AmarisoftExecutor
from corelab.connectors.base import CONNECTOR_CATALOG, ConnectorInfo, catalog
from corelab.connectors.nwdaf import NWDAFClient
from corelab.connectors.open5gs import Open5GSClient
from corelab.connectors.prometheus import PrometheusClient
from corelab.connectors.ueransim import RunResult, UERANSIMController

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
