import json
import os
import signal
import sys
from threading import Event, Thread
from time import sleep

import pytest
import requests


NETAPP_URL = os.getenv("NETAPP_LIVE_URL", "http://localhost:5001")


def _signal_handler(sig, frame):
    print("You pressed Ctrl+C!")
    event.set()
    thread.join()
    sys.exit()


def _location_updates(stop_event: Event):
    while True:
        if stop_event.is_set():
            break

        resp = requests.get(f"{NETAPP_URL}/VappConsume", timeout=5)
        data = json.loads(resp.text)
        if "nothing" in data:
            continue

        if data["type"] == "log":
            message = "NORMAL LOG: ue {} with ip {} is using cell {}".format(
                data["externalId"], data["ipv4Addr"], data["locationInfo"]["cellId"]
            )
            print({"type": "LOG", "msg": message})
        else:
            message = "ALERT LOG: ue {} with ip {} is using cell {}".format(
                data["externalId"], data["ipv4Addr"], data["locationInfo"]["cellId"]
            )
            print({"type": "ALERT", "msg": message})

        sleep(1)


def main():
    global event, thread

    resp = requests.get(f"{NETAPP_URL}/start_ues", verify=False, timeout=5)
    print("Started_ues", resp.json())

    headers = {"Content-type": "application/json"}

    auth_response = requests.post(
        f"{NETAPP_URL}/vapp_connect",
        headers=headers,
        json={"vapp_ip": "does_not_matter", "port": "777"},
        timeout=5,
    )
    print(auth_response, "vapp_connect")

    auth_response = requests.post(
        f"{NETAPP_URL}/subscription",
        headers=headers,
        json={
            "id": "10003@domain.com",
            "num_of_reports": "100",
            "exp_time": "2022-11-12T12:41:39.781Z",
        },
        timeout=5,
    )
    print(auth_response, "subscription")

    auth_response = requests.post(
        f"{NETAPP_URL}/setPolicy",
        headers=headers,
        json={
            "id": "10003@domain.com",
            "pol-id": "0",
            "cells": "AAAAA1001,AAAAA1002",
        },
        timeout=5,
    )
    print(auth_response, "policy creation")

    event = Event()
    thread = Thread(target=_location_updates, args=(event,))
    thread.start()
    signal.signal(signal.SIGINT, _signal_handler)
    thread.join()


@pytest.mark.skip(reason="Manual live integration harness. Run this file directly.")
def test_live_netapp_endpoints_manual():
    pass


if __name__ == "__main__":
    main()
