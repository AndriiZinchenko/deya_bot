import hashlib

import pytest

from deye_bot.deye import DeyeClient, DeyeError, ORDER_OK


class FakeResp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status

    def json(self):
        return self._d


class FakeSession:
    """Routes (method, path-suffix) to canned replies and records every call."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def _answer(self, method, url, **kw):
        self.calls.append((method, url, kw))
        for (m, suffix), reply in self.routes.items():
            if m == method and url.endswith(suffix):
                r = reply.pop(0) if isinstance(reply, list) else reply
                return r if isinstance(r, FakeResp) else FakeResp(r)
        raise AssertionError(f"unexpected {method} {url}")

    post = lambda self, url, **kw: self._answer("POST", url, **kw)  # noqa: E731
    request = lambda self, method, url, **kw: self._answer(method, url, **kw)  # noqa: E731


TOKEN = {"success": True, "code": "1000000", "accessToken": "tok", "expiresIn": "5183999"}


def client(routes):
    s = FakeSession({("POST", "/account/token"): TOKEN, **routes})
    return DeyeClient("app", "secret", "me@example.com", "pw", session=s), s


def test_token_request_hashes_password_and_sends_bearer():
    c, s = client({("POST", "/device/latest"): {"success": True, "deviceDataList": [
        {"collectionTime": 1, "dataList": [{"key": k, "value": v} for k, v in [
            ("TotalSolarPower", "419.00"), ("TotalConsumptionPower", "533"), ("TotalGridPower", "2345"),
            ("BatteryPower", "-2266"), ("SOC", "93")]]}]}})
    snap = c.latest("SN")
    assert (snap.pv_w, snap.load_w, snap.grid_w, snap.battery_w, snap.soc) == (419, 533, 2345, -2266, 93)
    token_call = s.calls[0]
    assert token_call[2]["params"] == {"appId": "app"}
    assert token_call[2]["json"]["password"] == hashlib.sha256(b"pw").hexdigest()
    assert s.calls[1][2]["headers"]["Authorization"] == "bearer tok"
    assert s.calls[1][2]["json"] == {"deviceList": ["SN"]}


def test_api_error_raises():
    c, _ = client({("POST", "/device/latest"): {"success": False, "code": "2101", "msg": "nope"}})
    with pytest.raises(DeyeError, match="nope"):
        c.latest("SN")


def test_missing_field_raises():
    c, _ = client({("POST", "/device/latest"): {"success": True, "deviceDataList": [
        {"collectionTime": 1, "dataList": [{"key": "SOC", "value": "1"}]}]}})
    with pytest.raises(DeyeError, match="TotalSolarPower"):
        c.latest("SN")


def test_find_inverter_skips_loggers_and_batteries():
    c, _ = client({("POST", "/station/listWithDevice"): {"success": True, "stationList": [{"deviceListItems": [
        {"deviceType": "COLLECTOR", "deviceSn": "A"}, {"deviceType": "INVERTER", "deviceSn": "B"},
        {"deviceType": "BATTERY", "deviceSn": "C"}]}]}})
    assert c.find_inverter() == "B"


def test_read_holding_goes_through_custom_control_and_parses_reply():
    c, s = client({
        ("POST", "/order/customControl"): {"success": True, "orderId": 123},
        ("GET", "/order/123"): {"success": True, "status": ORDER_OK, "error": None,
                                "analysisResult": "01030200FFF804"}})
    assert c.read_holding("SN", 146) == [0x00FF]
    sent = s.calls[1][2]["json"]
    assert sent["content"] == "01030092000125E7" and sent["deviceSn"] == "SN"


def test_wait_order_polls_until_done(monkeypatch):
    monkeypatch.setattr("deye_bot.deye.time.sleep", lambda _: None)
    c, _ = client({("GET", "/order/9"): [
        {"success": True, "status": 1, "error": None}, {"success": True, "status": ORDER_OK, "error": None}]})
    assert c.wait_order(9)["status"] == ORDER_OK


def test_wait_order_failure_and_timeout(monkeypatch):
    monkeypatch.setattr("deye_bot.deye.time.sleep", lambda _: None)
    c, _ = client({("GET", "/order/9"): {"success": True, "status": 5, "error": "device offline"}})
    with pytest.raises(DeyeError, match="device offline"):
        c.wait_order(9)
    c, _ = client({("GET", "/order/9"): {"success": True, "status": 1, "error": None}})
    with pytest.raises(DeyeError, match="not finished"):
        c.wait_order(9, timeout=0)


def test_switch_on_sends_all_days_off_sends_none():
    c, s = client({("POST", "/order/sys/tou/switch"): {"success": True, "orderId": 7},
                   ("GET", "/order/7"): {"success": True, "status": ORDER_OK, "error": None}})
    c.switch_tou("SN", True)
    c.switch_tou("SN", False)
    on, off = [call[2]["json"] for call in s.calls if call[1].endswith("/switch")]
    assert on["action"] == "on" and len(on["days"]) == 7
    assert off == {"deviceSn": "SN", "action": "off"}


def test_expired_token_is_refreshed():
    c, s = client({("POST", "/device/latest"): [FakeResp({"success": False}, 401), {"success": True, "deviceDataList": [
        {"collectionTime": 1, "dataList": [{"key": k, "value": "1"} for k in [
            "TotalSolarPower", "TotalConsumptionPower", "TotalGridPower", "BatteryPower", "SOC"]]}]}]})
    c.latest("SN")
    assert sum(1 for call in s.calls if call[1].endswith("/account/token")) == 2
