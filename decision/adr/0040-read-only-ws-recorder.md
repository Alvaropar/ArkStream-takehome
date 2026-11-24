# ADR-0040: Read-only Hyperliquid stream recorder, standard library, subscribe-only

- Status: Accepted
- Date: 2026-11-20
- Phase: Phase 3 / Phase 6 (latency measurement, ADR-0038 item 1)
- Brief: `decision/briefs/latency-hl-receive.md`

## Context
ADR-0038 needs the receive leg (leader fill on Hyperliquid -> our process) measured without trading. The project
forbids any order path (`config/execution.yaml`, `tests/test_audit_and_safety.py`), and the safety test forbade
the word `websocket` anywhere in `src/arkstream_fetch`. A WebSocket client is needed, either as a new dependency
or written in the standard library.

## Decision
1. **Recorder `src/arkstream_fetch/hl_ws_latency.py`**, standard library only (`socket`, `ssl`, `json`): a minimal
   RFC 6455 client (upgrade handshake with `Sec-WebSocket-Accept` checked, no extensions negotiated so frames
   are not compressed, incremental frame decoder). **No new dependency.** A hand-written synchronous client also
   gives the tightest arrival stamp: `time.time_ns()` (and a monotonic stamp) is taken right after the socket
   read that completes a frame, before parsing. With a library client the stamp is taken when the message
   leaves its queue.
2. **One host.** `WsConnection` refuses any URL except `wss://api.hyperliquid.xyz/ws` before opening a socket.
   NTP is queried only from `NTP_SERVERS` (ADR-0041).
3. **What may be sent**, enforced in code:
   - data frames only through `encode_frame`, which calls `_guard_outgoing`. That accepts exactly
     `{"method": "subscribe", "subscription": {"type": "userFills", "user": <0x address>}}` or
     `{... {"type": "trades", "coin": <symbol>}}` and refuses everything else, including `post`, `ping`,
     `unsubscribe`, other subscription types, extra keys and non-JSON;
   - the protocol's own control frames: a **pong** that echoes a server ping (RFC 6455 5.5.2 requires it; it
     carries only the server's bytes) and **close**. Ping and binary frames cannot be built;
   - no application `{"method": "ping"}` heartbeat. Two smoke runs (3.7 and 4 min) stayed connected without one
     while trades kept flowing. If the venue drops an idle connection, the recorder reconnects and logs the gap.
4. **Output per run** in `data/reference/latency/hyperliquid/<run_id>/`: `raw.jsonl` (each payload byte for byte),
   `arrivals.csv`, `events.csv`, `gaps.csv`, `run.json` (subscriptions, machine without host name or address,
   user-supplied network description, NTP before/after, gaps, counts, recorder SHA-256) and `MANIFEST.csv`
   (bytes, SHA-256 of every file). The analysis refuses a run whose files do not match the manifest.
5. **Reconnects** with exponential backoff from 1 s, capped at 60 s, reset after a connection that lasted more than
   60 s. A connection with no bytes for 90 s counts as dead. Every disconnection is a row in `gaps.csv`. The run ends at
   the set duration or Ctrl-C, and the closing clock measurement and the manifest are always written.
6. **Safety tests** (`tests/test_audit_and_safety.py`): the word `websocket` is allowed only in `hl_ws_latency.py`,
   whose only `ws(s)://` host must be `api.hyperliquid.xyz`. `/exchange`, order placement and signing names
   (`eth_account`, `sign_l1_action`, `sign_typed_data`, `private_key`, ...) are forbidden in both packages. An AST
   test pins every socket send to `_send_frame`, `_handshake` and `query_ntp`. Behavioural tests check that the
   guard refuses order, info-post, ping, unsubscribe and malformed messages, and that refused URLs never open a socket.
   `src/arkstream` still has no network code: the analysis is `src/arkstream/latency.py`.

## Consequences
The recorder adds about 500 lines that this project must maintain, and no third-party code. Its correctness is
tested offline with a fake transport: framing at every length class, fragments, byte-by-byte feeds, pong echo,
close, refused extensions, a stale connection, and raw bytes kept unchanged. The recorder imports
`arkstream.latency` (a pure parser). The reverse import stays forbidden.
