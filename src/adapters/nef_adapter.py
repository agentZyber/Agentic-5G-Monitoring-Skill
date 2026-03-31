import requests
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

try:
    from evolved5g.sdk import LocationSubscriber
    from evolved5g.swagger_client import LoginApi, Configuration, ApiClient

    EVOLVED5G_AVAILABLE = True
except ImportError:
    EVOLVED5G_AVAILABLE = False


@FiveGCoreFactory.register(CoreType.NEF)
class NEFAdapter(FiveGCoreAdapter):
    """
    NEF (Network Exposure Function) Adapter

    Generic 3GPP NEF interface using the evolved5g SDK.
    This is the original adapter used in Phase 1-3.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.nef_url = config.get("nef_url", "http://localhost:8080")
        self.nef_user = config.get("nef_user", "admin")
        self.nef_pass = config.get("nef_password", "admin")

        self.capif_host = config.get("capif_host", "")
        self.capif_https_port = config.get("capif_https_port", 8080)
        self.capif_certs_path = config.get("path_to_certs", "./capif_certs")

        self._token = None
        self._location_subscriber = None

    def get_type(self) -> CoreType:
        return CoreType.NEF

    def get_auth_token(self) -> str:
        if not EVOLVED5G_AVAILABLE:
            return self.config.get("bearer_token", "")

        try:
            configuration = Configuration()
            configuration.host = self.nef_url
            api_client = ApiClient(configuration=configuration)
            api_client.select_header_content_type(["application/x-www-form-urlencoded"])
            api = LoginApi(api_client)
            token = api.login_access_token_api_v1_login_access_token_post(
                "", self.nef_user, self.nef_pass, "", "", ""
            )
            self._token = token.access_token
            return self._token
        except Exception as e:
            print(f"NEF auth error: {e}")
            return self.config.get("bearer_token", "")

    def _get_location_subscriber(self):
        if not EVOLVED5G_AVAILABLE:
            return None

        if self._location_subscriber is None:
            token = self.get_auth_token()
            self._location_subscriber = LocationSubscriber(
                nef_url=self.nef_url,
                nef_bearer_access_token=token,
                folder_path_for_certificates_and_capif_api_key=self.capif_certs_path,
                capif_host=self.capif_host,
                capif_https_port=self.capif_https_port,
            )
        return self._location_subscriber

    def create_subscription(self, request: SubscriptionRequest) -> SubscriptionResponse:
        if not EVOLVED5G_AVAILABLE:
            return SubscriptionResponse(
                subscription_id="",
                external_id=request.external_id,
                netapp_id=request.netapp_id,
                status="failed_evolved5g_not_available",
            )

        try:
            subscriber = self._get_location_subscriber()
            if subscriber is None:
                return SubscriptionResponse(
                    subscription_id="",
                    external_id=request.external_id,
                    netapp_id=request.netapp_id,
                    status="failed_no_subscriber",
                )

            subscription = subscriber.create_subscription(
                netapp_id=request.netapp_id,
                external_id=request.external_id,
                notification_destination=request.callback_url,
                maximum_number_of_reports=request.num_of_reports,
                monitor_expire_time=request.monitor_expire_time,
            )

            sub_dict = subscription.to_dict()
            return SubscriptionResponse(
                subscription_id=sub_dict.get("id", ""),
                external_id=request.external_id,
                netapp_id=request.netapp_id,
                status="active",
                raw_response=sub_dict,
            )
        except Exception as e:
            print(f"NEF subscription error: {e}")
            return SubscriptionResponse(
                subscription_id="",
                external_id=request.external_id,
                netapp_id=request.netapp_id,
                status=f"error_{str(e)}",
            )

    def get_subscriptions(
        self, netapp_id: str, offset: int = 0, limit: int = 100
    ) -> List[SubscriptionResponse]:
        if not EVOLVED5G_AVAILABLE:
            return []

        try:
            subscriber = self._get_location_subscriber()
            if subscriber is None:
                return []

            all_subs = subscriber.get_all_subscriptions(netapp_id, offset, limit)

            subscriptions = []
            for sub in all_subs if isinstance(all_subs, list) else [all_subs]:
                sub_dict = sub.to_dict() if hasattr(sub, "to_dict") else sub
                subscriptions.append(
                    SubscriptionResponse(
                        subscription_id=sub_dict.get("id", ""),
                        external_id=sub_dict.get("externalId", ""),
                        netapp_id=netapp_id,
                        status="active",
                        raw_response=sub_dict,
                    )
                )
            return subscriptions
        except Exception as e:
            print(f"NEF get_subscriptions error: {e}")
            return []

    def delete_subscription(self, subscription_id: str) -> bool:
        return True

    def parse_callback(self, data: Dict[str, Any]) -> LocationEvent:
        return LocationEvent.from_dict(data)

    def format_ue_query(self, external_id: str) -> Dict[str, Any]:
        return {
            "externalId": external_id,
            "netappId": self.config.get("netapp_id", "zorte_netapp"),
        }

    def get_ue_location(self, external_id: str) -> Optional[LocationEvent]:
        return None
