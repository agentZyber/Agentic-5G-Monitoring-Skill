import requests
import json
import time
from typing import Dict, Any, Optional, List
from urllib.parse import urljoin

from core_adapter import (
    FiveGCoreAdapter,
    FiveGCoreFactory,
    CoreType,
    SubscriptionRequest,
    SubscriptionResponse,
    LocationEvent,
)


@FiveGCoreFactory.register(CoreType.FREE5GC)
class Free5GCAdapter(FiveGCoreAdapter):
    """
    Free5GC Core Adapter

    Free5GC is a full 3GPP R16 compliant 5G core implementation.
    Default ports:
        - NEF: 29507
        - NRF: 29510
        - UDR: 29504
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.nef_url = config.get("nef_url", "http://localhost:29507")
        self.nrf_url = config.get("nrf_url", "http://localhost:29510")
        self.client = requests.Session()

        self._setup_auth()

    def _setup_auth(self):
        self.client.headers.update({"Content-Type": "application/json"})

        if self.config.get("api_key"):
            self.client.headers.update({"X-API-Key": self.config["api_key"]})

    def get_type(self) -> CoreType:
        return CoreType.FREE5GC

    def get_auth_token(self) -> str:
        nrf_token_endpoint = urljoin(self.nrf_url, "/oauth2/token")

        try:
            response = self.client.post(
                nrf_token_endpoint,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.config.get("client_id", "netapp"),
                    "client_secret": self.config.get("client_secret", "free5gcsecret"),
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if response.status_code == 200:
                return response.json().get("access_token", "")
        except Exception as e:
            print(f"Free5GC auth error: {e}")

        return self.config.get("bearer_token", "")

    def create_subscription(self, request: SubscriptionRequest) -> SubscriptionResponse:
        subscription_endpoint = urljoin(
            self.nef_url, "/nnef-subscription/v1/subscriptions"
        )

        token = self.get_auth_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        body = {
            "subscriptionId": f"sub_{request.external_id}_{int(time.time())}",
            "externalId": request.external_id,
            "networkAreaInfo": {"ueId": request.external_id, "allowedGIsciList": []},
            "monitoredAreaList": [],
            "monitoringType": "LOCATION",
            "maximumNumberOfReports": request.num_of_reports,
            "monitorExpireTime": request.monitor_expire_time,
            "notificationDestination": {"callbackUri": request.callback_url},
        }

        try:
            response = self.client.post(
                subscription_endpoint, json=body, headers=headers
            )

            if response.status_code in [200, 201]:
                data = response.json()
                return SubscriptionResponse(
                    subscription_id=data.get("subscriptionId", ""),
                    external_id=request.external_id,
                    netapp_id=request.netapp_id,
                    status="active",
                    raw_response=data,
                )
        except Exception as e:
            print(f"Free5GC subscription error: {e}")

        return SubscriptionResponse(
            subscription_id="",
            external_id=request.external_id,
            netapp_id=request.netapp_id,
            status="failed",
        )

    def get_subscriptions(
        self, netapp_id: str, offset: int = 0, limit: int = 100
    ) -> List[SubscriptionResponse]:
        subscriptions_endpoint = urljoin(
            self.nef_url, "/nnef-subscription/v1/subscriptions"
        )

        token = self.get_auth_token()
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = self.client.get(
                subscriptions_endpoint,
                headers=headers,
                params={"offset": offset, "limit": limit},
            )

            if response.status_code == 200:
                data = response.json()
                items = (
                    data.get("subscriptions", []) if isinstance(data, dict) else data
                )
                return [
                    SubscriptionResponse(
                        subscription_id=sub.get("subscriptionId", ""),
                        external_id=sub.get("externalId", ""),
                        netapp_id=netapp_id,
                        status="active",
                        raw_response=sub,
                    )
                    for sub in (items if isinstance(items, list) else [])
                ]
        except Exception as e:
            print(f"Free5GC get_subscriptions error: {e}")

        return []

    def delete_subscription(self, subscription_id: str) -> bool:
        delete_endpoint = urljoin(
            self.nef_url, f"/nnef-subscription/v1/subscriptions/{subscription_id}"
        )

        token = self.get_auth_token()
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = self.client.delete(delete_endpoint, headers=headers)
            return response.status_code in [200, 204]
        except Exception:
            return False

    def parse_callback(self, data: Dict[str, Any]) -> LocationEvent:
        if isinstance(data, dict):
            if "jsonData" in data:
                json_data = data["jsonData"]
                return LocationEvent(
                    external_id=json_data.get("externalId", ""),
                    cell_id=json_data.get("cellId", ""),
                    timestamp=json_data.get("timeStamp", ""),
                    event_type=json_data.get("monitoringType", "LOCATION"),
                    ipv4_addr=json_data.get("ueIpv4Address"),
                    raw_data=data,
                )
            elif "externalId" in data:
                return LocationEvent.from_dict(data)

        return LocationEvent(
            external_id="unknown",
            cell_id="unknown",
            timestamp="",
            event_type="unknown",
            raw_data=data,
        )

    def format_ue_query(self, external_id: str) -> Dict[str, Any]:
        return {"externalId": external_id, "queryType": "LOCATION"}

    def get_ue_location(self, external_id: str) -> Optional[LocationEvent]:
        location_endpoint = urljoin(
            self.nef_url, f"/nnef-svc/v1/ue/location/{external_id}"
        )

        token = self.get_auth_token()
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = self.client.get(location_endpoint, headers=headers)
            if response.status_code == 200:
                data = response.json()
                return self.parse_callback(data)
        except Exception:
            pass

        return None

    def get_ue_slice_info(self, external_id: str) -> Optional[Dict[str, Any]]:
        slice_endpoint = urljoin(self.nef_url, f"/nnef-svc/v1/ue/slice/{external_id}")

        token = self.get_auth_token()
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = self.client.get(slice_endpoint, headers=headers)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass

        return None

    def get_ue_qos_flows(self, external_id: str) -> Optional[List[Dict[str, Any]]]:
        qos_endpoint = urljoin(self.nef_url, f"/nnef-svc/v1/ue/qos/{external_id}")

        token = self.get_auth_token()
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = self.client.get(qos_endpoint, headers=headers)
            if response.status_code == 200:
                data = response.json()
                return data.get("qosFlows", []) if isinstance(data, dict) else []
        except Exception:
            pass

        return None
