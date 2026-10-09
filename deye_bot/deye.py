"""Client for the DeyeCloud Open API (https://developer.deyecloud.com)."""
import hashlib
import logging
import time
from dataclasses import dataclass

import requests

from .modbus import parse_read_response, read_holding_frame

log = logging.getLogger(__name__)

DATA_CENTERS = {
    "eu": "https://eu1-developer.deyecloud.com",
    "am": "https://us1-developer.deyecloud.com",
    "india": "https://india-developer.deyecloud.com",
}
ORDER_OK = 666  # `status` of a finished, successful order


class DeyeError(Exception):
    pass


@dataclass(frozen=True)
class Snapshot:
    ts: int  # unix seconds, inverter collection time
    pv_w: float
    load_w: float
    grid_w: float  # + importing from grid, - exporting
    battery_w: float  # + discharging, - charging
    soc: float


def _num(values: dict, key: str) -> float:
    try:
        return float(values[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise DeyeError(f"inverter data is missing {key!r}") from exc


class DeyeClient:
    def __init__(self, app_id, app_secret, email, password, data_center="eu",
                 password_is_hashed=False, session=None, timeout=20):
        if data_center not in DATA_CENTERS:
            raise ValueError(f"unknown data center {data_center!r}")
        self.base = DATA_CENTERS[data_center] + "/v1.0"
        self.app_id, self.app_secret, self.email = app_id, app_secret, email
        # The Open API expects the account password as a lowercase SHA-256 hex digest.
        self.password = password if password_is_hashed else hashlib.sha256(password.encode()).hexdigest()
        self.http = session or requests.Session()
        self.timeout = timeout
        self._token = None
        self._token_expiry = 0.0

    # ---- plumbing -------------------------------------------------------
    def _parse(self, resp):
        try:
            data = resp.json()
        except ValueError as exc:
            raise DeyeError(f"HTTP {resp.status_code}: non-JSON reply") from exc
        if resp.status_code >= 400 or not data.get("success", False):
            raise DeyeError(f"HTTP {resp.status_code} code={data.get('code')} msg={data.get('msg')}")
        return data

    def _fetch_token(self):
        resp = self.http.post(
            f"{self.base}/account/token", params={"appId": self.app_id},
            json={"appSecret": self.app_secret, "email": self.email, "password": self.password},
            timeout=self.timeout)
        data = self._parse(resp)
        self._token = data["accessToken"]
        self._token_expiry = time.time() + int(data.get("expiresIn", 0)) - 300
        log.info("obtained Deye access token")

    def _request(self, method, path, body=None, _retry=True):
        if not self._token or time.time() >= self._token_expiry:
            self._fetch_token()
        resp = self.http.request(
            method, f"{self.base}{path}", json=body, timeout=self.timeout,
            headers={"Authorization": f"bearer {self._token}"})
        if resp.status_code == 401 and _retry:
            self._token = None
            return self._request(method, path, body, _retry=False)
        return self._parse(resp)

    # ---- queries --------------------------------------------------------
    def find_inverter(self) -> str:
        data = self._request("POST", "/station/listWithDevice", {"page": 1, "size": 10})
        for station in data.get("stationList", []):
            for dev in station.get("deviceListItems", []):
                if dev.get("deviceType") == "INVERTER":
                    return dev["deviceSn"]
        raise DeyeError("no INVERTER found on this account")

    def latest(self, device_sn: str) -> Snapshot:
        data = self._request("POST", "/device/latest", {"deviceList": [device_sn]})
        devices = data.get("deviceDataList") or []
        if not devices:
            raise DeyeError("device/latest returned no data")
        values = {p["key"]: p["value"] for p in devices[0]["dataList"]}
        return Snapshot(
            ts=int(devices[0].get("collectionTime") or time.time()),
            pv_w=_num(values, "TotalSolarPower"),
            load_w=_num(values, "TotalConsumptionPower"),
            grid_w=_num(values, "TotalGridPower"),
            battery_w=_num(values, "BatteryPower"),
            soc=_num(values, "SOC"),
        )

    # ---- orders ---------------------------------------------------------
    def wait_order(self, order_id, timeout=60.0, interval=1.0) -> dict:
        deadline = time.time() + timeout
        while True:
            data = self._request("GET", f"/order/{order_id}")
            if data.get("error"):
                raise DeyeError(f"order {order_id} failed: {data['error']}")
            if data.get("status") == ORDER_OK:
                return data
            if time.time() >= deadline:
                raise DeyeError(f"order {order_id} not finished after {timeout:.0f}s (status={data.get('status')})")
            time.sleep(interval)

    def read_holding(self, device_sn: str, address: int, quantity: int = 1, timeout=60.0) -> list[int]:
        """Read Modbus holding registers straight from the inverter (not from the cloud cache)."""
        sent = self._request("POST", "/order/customControl", {
            "deviceSn": device_sn, "content": read_holding_frame(address, quantity),
            "timeoutSeconds": int(timeout)})
        result = self.wait_order(sent["orderId"], timeout=timeout)
        return parse_read_response(result["analysisResult"], quantity)

    def switch_tou(self, device_sn: str, on: bool, days=None, timeout=60.0) -> dict:
        body = {"deviceSn": device_sn, "action": "on" if on else "off"}
        if on:
            body["days"] = list(days or ALL_DAYS)
        sent = self._request("POST", "/order/sys/tou/switch", body)
        return self.wait_order(sent["orderId"], timeout=timeout)


ALL_DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
