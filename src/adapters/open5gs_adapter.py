import requests
import json
from typing import Dict, Any, Optional, List, Callable
from urllib.parse import urljoin

from core_adapter import (
    FiveGCoreAdapter,
    FiveGCoreFactory,
    CoreType,
    SubscriptionRequest,
    SubscriptionResponse,
    LocationEvent,
)


@FiveGCoreFactory.register(CoreType.OPEN5GS)
class Open5GSAdapter(FiveGCoreAdapter):
    """
    Open5GS Core Adapter

    Open5GS provides a REST API through its NRF and NEF-like services.
    Default ports:
        - NRF: 29502
        - NEF: 29508
        - UDR: 29507
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = config.get("base_url", "http://localhost:29508")
        self.nrf_url = config.get("nrf_url", "http://localhost:29502")
        self.client = requests.Session()

        self._setup_auth()

    def _setup_auth(self):
        api_key = self.config.get("api_key", "")
        if api_key:
            self.client.headers.update({"X-API-Key": api_key})

        username = self.config.get("username")
        password = self.config.get("password")
        if username and password:
            self.client.auth = (username, password)

    def get_type(self) -> CoreType:
        return CoreType.OPEN5GS

    def get_auth_token(self) -> str:
        auth_endpoint = urljoin(self.nrf_url, "/oauth2/token")

        try:
            response = self.client.post(
                auth_endpoint,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.config.get("client_id", "netapp"),
                    "client_secret": self.config.get("client_secret", "secret"),
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if response.status_code == 200:
                token_data = response.json()
                return token_data.get("access_token", "")
        except Exception as e:
            print(f"Open5GS auth error: {e}")

        return self.config.get("bearer_token", "")

    def create_subscription(self, request: SubscriptionRequest) -> SubscriptionResponse:
        subscription_endpoint = urljoin(
            self.base_url, "/namf-subscription/v1/subscriptions"
        )

        token = self.get_auth_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        body = {
            "ueId": request.external_id,
            "subscriptionId": f"sub_{request.external_id}",
            "monitoringType": "LOCATION",
            "maximumNumberOfReports": request.num_of_reports,
            "monitorExpireTime": request.monitor_expire_time,
            "notificationDestination": request.callback_url,
        }

        try:
            response = self.client.post(
                subscription_endpoint, json=body, headers=headers
            )

            if response.status_code in [200, 201]:
                data = response.json()
                return SubscriptionResponse(
                    subscription_id=data.get("subscriptionId", data.get("id", "")),
                    external_id=request.external_id,
                    netapp_id=request.netapp_id,
                    status="active",
                    raw_response=data,
                )
            else:
                return SubscriptionResponse(
                    subscription_id="",
                    external_id=request.external_id,
                    netapp_id=request.netapp_id,
                    status=f"failed_{response.status_code}",
                    raw_response={"error": response.text},
                )
        except Exception as e:
            return SubscriptionResponse(
                subscription_id="",
                external_id=request.external_id,
                netapp_id=request.netapp_id,
                status=f"error_{str(e)}",
            )

    def get_subscriptions(
        self, netapp_id: str, offset: int = 0, limit: int = 100
    ) -> List[SubscriptionResponse]:
        subscriptions_endpoint = urljoin(
            self.base_url, "/namf-subscription/v1/subscriptions"
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
                subscriptions = (
                    data.get("subscriptions", data) if isinstance(data, dict) else data
                )
                return [
                    SubscriptionResponse(
                        subscription_id=sub.get("subscriptionId", sub.get("id", "")),
                        external_id=sub.get("ueId", ""),
                        netapp_id=netapp_id,
                        status="active",
                        raw_response=sub,
                    )
                    for sub in (
                        subscriptions if isinstance(subscriptions, list) else []
                    )
                ]
        except Exception as e:
            print(f"Open5GS get_subscriptions error: {e}")

        return []

    def delete_subscription(self, subscription_id: str) -> bool:
        delete_endpoint = urljoin(
            self.base_url, f"/namf-subscription/v1/subscriptions/{subscription_id}"
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
            if "ueId" in data:
                return LocationEvent(
                    external_id=data.get("ueId", ""),
                    cell_id=data.get("cellId", ""),
                    timestamp=data.get("timeStamp", ""),
                    event_type=data.get("monitoringType", "LOCATION"),
                    ipv4_addr=data.get("ueIpv4Address"),
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
        return {
            "ueId": external_id,
            "plmnId": {
                "mcc": self.config.get("mcc", "001"),
                "mnc": self.config.get("mnc", "01"),
            },
        }

    def get_ue_location(self, external_id: str) -> Optional[LocationEvent]:
        location_endpoint = urljoin(
            self.base_url, f"/namf-loc/v1/ues/{external_id}/location"
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

    def get_ue_info(self, external_id: str) -> Optional[Dict[str, Any]]:
        ue_info_endpoint = urljoin(self.base_url, f"/namf-comm/v1/ues/{external_id}")

        token = self.get_auth_token()
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = self.client.get(ue_info_endpoint, headers=headers)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass

        return None
