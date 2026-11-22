import re

import pytest

from arkstream import audit
from arkstream.config import ROOT, assert_no_live_trading


@pytest.mark.data
def test_headline_counts_reproduce_exactly(full_build):
    rows = audit.check(full_build, audit.load_expected(ROOT / "provenance" / "expected_counts.yaml"))
    failed = [r for r in rows if not r[3]]
    assert not failed, audit.format_rows(failed)


def test_live_trading_disabled():
    assert_no_live_trading()


def test_no_order_sending_code_path():
    pat = re.compile(r"(requests\.|httpx|websocket|aiohttp|urllib\.request|\.order\(|place_order|Exchange\()")
    for p in (ROOT / "src" / "arkstream").rglob("*.py"):
        assert not pat.search(p.read_text(encoding="utf-8")), p


WS_RECORDER = "hl_ws_latency.py"  # the one file allowed to use a WebSocket (ADR-0044, ADR-0100)
SIGNING = re.compile(r"(eth_account|sign_l1_action|sign_typed_data|signTypedData|private_key|secret_key)")


def test_fetcher_has_no_order_path_and_one_host():
    """src/arkstream_fetch may download market data, only from data.binance.vision and the Hyperliquid info
    endpoint (ADR-0011) and stream (ADR-0100), and never trade or sign."""
    order = re.compile(r"(\.order\(|place_order|Exchange\(|/exchange|fapi\.binance)")
    ws = re.compile(r"websocket", re.I)
    url = re.compile(r"(?:https?|wss?)://([A-Za-z0-9.-]+)")  # f"https://{ALLOWED_HOST}/" is checked in _check_url
    for p in (ROOT / "src" / "arkstream_fetch").rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        assert not order.search(text), p
        assert not SIGNING.search(text), p
        assert p.name == WS_RECORDER or not ws.search(text), p
        assert set(url.findall(text)) <= {"data.binance.vision", "api.hyperliquid.xyz"}, (p, set(url.findall(text)))
    rec = (ROOT / "src" / "arkstream_fetch" / WS_RECORDER).read_text(encoding="utf-8")
    assert set(re.findall(r"wss?://([A-Za-z0-9.-]+)", rec)) == {"api.hyperliquid.xyz"}
    imp = re.compile(r"^\s*(from|import)\s+arkstream_fetch", re.M)
    for p in (ROOT / "src" / "arkstream").rglob("*.py"):
        assert not imp.search(p.read_text(encoding="utf-8")), p  # the pipeline never imports the fetcher
        assert not SIGNING.search(p.read_text(encoding="utf-8")), p


def test_ws_recorder_sends_only_from_known_places():
    """Every socket send in the recorder is in one of three functions: the guarded frame sender, the HTTP
    upgrade request, and the NTP client. No other fetcher file opens a raw socket."""
    import ast

    tree = ast.parse((ROOT / "src" / "arkstream_fetch" / WS_RECORDER).read_text(encoding="utf-8"))
    senders = set()
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for n in ast.walk(fn):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in (
                        "send", "sendall", "sendto", "write") and _is_socket_call(n):
                    senders.add(fn.name)
    assert senders == {"_send_frame", "_handshake", "query_ntp"}, senders
    for p in (ROOT / "src" / "arkstream_fetch").rglob("*.py"):
        if p.name != WS_RECORDER:
            assert "import socket" not in p.read_text(encoding="utf-8"), p


def _is_socket_call(n) -> bool:
    import ast

    v = n.func.value
    name = v.attr if isinstance(v, ast.Attribute) else getattr(v, "id", "")
    return name in ("sock", "s")


def test_ws_guard_refuses_everything_but_subscribe():
    import json

    from arkstream_fetch import hl_ws_latency as w

    ok = [{"method": "subscribe", "subscription": {"type": "trades", "coin": "BTC"}},
          {"method": "subscribe", "subscription": {"type": "userFills", "user": "0x" + "ab" * 20}}]
    for m in ok:
        w._guard_outgoing(json.dumps(m).encode())
    bad = [{"method": "post", "id": 1, "request": {"type": "action", "payload": {"action": {"type": "order"}}}},
           {"method": "post", "id": 1, "request": {"type": "info", "payload": {"type": "meta"}}},
           {"method": "ping"},
           {"method": "unsubscribe", "subscription": {"type": "trades", "coin": "BTC"}},
           {"method": "subscribe", "subscription": {"type": "orderUpdates", "user": "0x" + "ab" * 20}},
           {"method": "subscribe", "subscription": {"type": "trades", "coin": "BTC", "extra": 1}},
           {"method": "subscribe", "subscription": {"type": "userFills", "user": "not-an-address"}},
           {"method": "subscribe", "subscription": {"type": "trades", "coin": "BTC"}, "action": {"type": "order"}}]
    for m in bad:
        with pytest.raises(PermissionError):
            w._guard_outgoing(json.dumps(m).encode())
    for raw in (b"not json", b"[]"):
        with pytest.raises(PermissionError):
            w._guard_outgoing(raw)
    with pytest.raises(PermissionError):
        w.encode_frame(w.OP_TEXT, json.dumps(bad[0]).encode())
    for op in (w.OP_PING, w.OP_BIN, w.OP_CONT):
        with pytest.raises(PermissionError):
            w.encode_frame(op, b"{}")


def test_ws_host_allowlist():
    from arkstream_fetch import hl_ws_latency as w

    def no_socket(*a):
        raise AssertionError("a socket was opened for a refused URL")

    for url in ("wss://api.hyperliquid.xyz/exchange", "wss://api.hyperliquid-testnet.xyz/ws",
                "wss://evil.example/ws", "ws://api.hyperliquid.xyz/ws", "wss://api.hyperliquid.xyz.evil/ws"):
        with pytest.raises(ValueError):
            w.WsConnection(url, opener=no_socket)
    with pytest.raises(ValueError):
        w.query_ntp("pool.evil.example")
