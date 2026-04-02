set -eu

mkdir -p "${PATH_TO_CERTS:-/zortenet_netapp/capif_onboarding}"
cp capif_registration_template.json capif_registration.json

jq -r .capif_host=\"$CAPIF_HOSTNAME\" capif_registration.json > tmp.json && mv tmp.json capif_registration.json
jq -r .folder_to_store_certificates=\"$PATH_TO_CERTS\" capif_registration.json > tmp.json && mv tmp.json capif_registration.json
jq -r .capif_http_port=\"$CAPIF_PORT_HTTP\" capif_registration.json > tmp.json && mv tmp.json capif_registration.json
jq -r .capif_https_port=\"$CAPIF_PORT_HTTPS\" capif_registration.json > tmp.json && mv tmp.json capif_registration.json
jq -r .capif_callback_url=\"http://$CALLBACK_ADDRESS\" capif_registration.json > tmp.json && mv tmp.json capif_registration.json

evolved5g register-and-onboard-to-capif --config_file_full_path="/zortenet_netapp/capif_registration.json" &
exec uvicorn api:app --host 0.0.0.0 --port 5000
