from app.security import client_ip


class _FakeReq:
    def __init__(self, headers, host):
        self.headers = headers
        self.client = type("C", (), {"host": host})()


def test_uses_xff_first_hop():
    req = _FakeReq({"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}, "10.0.0.1")
    assert client_ip(req) == "203.0.113.7"


def test_falls_back_to_client_host():
    req = _FakeReq({}, "192.168.1.5")
    assert client_ip(req) == "192.168.1.5"
