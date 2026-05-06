"""Wire protocol for the PEK daemon.

Newline-delimited JSON over a Unix domain socket. One request per line,
one response per line, blocking call-and-response. The daemon serves
requests strictly serially (PEK models are not thread-safe).

Request shape::

    {"cmd": "parse", "pdf_path": "...", "output_dir": "..."}
    {"cmd": "ping"}
    {"cmd": "shutdown"}

Response shape::

    {"ok": true, "result": {...}}
    {"ok": false, "error": "...", "error_type": "..."}
"""

from __future__ import annotations

import json
import socket
from typing import Any, Dict


CMD_PARSE = "parse"
CMD_PING = "ping"
CMD_SHUTDOWN = "shutdown"

# 64 MiB hard cap on a single message — parsed_papers entries with very
# long markdown can be a few MB; this leaves a lot of headroom but
# protects us from a runaway producer.
MAX_MESSAGE_BYTES = 64 * 1024 * 1024


def send_message(sock: socket.socket, payload: Dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(data) > MAX_MESSAGE_BYTES:
        raise ValueError(
            f"Message too large: {len(data)} > {MAX_MESSAGE_BYTES} bytes"
        )
    sock.sendall(data + b"\n")


def recv_message(sock: socket.socket) -> Dict[str, Any]:
    """Read one newline-terminated JSON message from ``sock``.

    Raises ``ConnectionError`` if the peer closes before a newline.
    """
    chunks = bytearray()
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            if chunks:
                raise ConnectionError(
                    f"Peer closed mid-message after {len(chunks)} bytes"
                )
            raise ConnectionError("Peer closed before sending any data")
        chunks.extend(chunk)
        if b"\n" in chunk:
            break
        if len(chunks) > MAX_MESSAGE_BYTES:
            raise ValueError(
                f"Incoming message exceeds {MAX_MESSAGE_BYTES} bytes"
            )

    line, _, _rest = bytes(chunks).partition(b"\n")
    return json.loads(line.decode("utf-8"))
