try:
    from evolved5g.sdk import LocationSubscriber
    from evolved5g.swagger_client import LoginApi, Configuration, ApiClient

    EVOLVED5G_SDK_AVAILABLE = True
except ImportError:
    LocationSubscriber = None
    LoginApi = None
    Configuration = None
    ApiClient = None
    EVOLVED5G_SDK_AVAILABLE = False


def get_token(username, password, nef_url):
    if not EVOLVED5G_SDK_AVAILABLE or Configuration is None or ApiClient is None:
        raise RuntimeError("evolved5g SDK is not available in this environment")

    configuration = Configuration()
    configuration.host = nef_url
    api_client = ApiClient(configuration=configuration)
    api_client.select_header_content_type(["application/x-www-form-urlencoded"])
    api = LoginApi(api_client)
    token = api.login_access_token_api_v1_login_access_token_post(
        "", username, password, "", "", ""
    )
    return token.access_token


def get_api_client(token, nef_url):
    if not EVOLVED5G_SDK_AVAILABLE or Configuration is None or ApiClient is None:
        raise RuntimeError("evolved5g SDK is not available in this environment")

    configuration = Configuration()
    configuration.host = nef_url
    configuration.access_token = (
        token.access_token if hasattr(token, "access_token") else token
    )
    return ApiClient(configuration=configuration)


def monitor_subscription(
    expire_time,
    netapp_id,
    external_id,
    times,
    host,
    access_token,
    certificate_folder,
    capifhost,
    capifport,
    callback_server,
):
    if not EVOLVED5G_SDK_AVAILABLE or LocationSubscriber is None:
        raise RuntimeError("evolved5g SDK is not available in this environment")

    location_subscriber = LocationSubscriber(
        host, access_token, certificate_folder, capifhost, capifport
    )

    subscription = location_subscriber.create_subscription(
        netapp_id=netapp_id,
        external_id=external_id,
        notification_destination=callback_server,
        maximum_number_of_reports=times,
        monitor_expire_time=expire_time,
    )
    monitoring_response = subscription.to_dict()

    return monitoring_response
