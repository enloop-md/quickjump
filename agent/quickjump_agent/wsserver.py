"""
A deliberately small WebSocket server (RFC 6455) on top of QTcpServer.

The agent only ever exchanges short JSON text messages with a handful of
browser extensions on localhost, so this covers exactly that: the opening
handshake, text frames (fragmented or not), ping/pong and close. No
extensions, no compression, no binary payloads. Keeping it in-house means the
agent runs on a stock PyQt6 with nothing to pip-install.
"""

import base64
import hashlib
import json
import struct

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QHostAddress, QTcpServer

GUID = b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'

# Web pages can reach localhost too. Only browser extensions are let in; a page
# on some site sends its own origin and gets a 403.
ALLOWED_ORIGIN_PREFIXES = ('chrome-extension://', 'moz-extension://')

MAX_MESSAGE = 4 * 1024 * 1024
PROBE_PATH = '/quickjump'

OP_CONT, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


class WsClient(QObject):
    opened = pyqtSignal()
    message = pyqtSignal(dict)
    closed = pyqtSignal()

    def __init__(self, sock, parent=None):
        super().__init__(parent)
        self.sock = sock
        self.origin = ''
        self.open = False
        self._buf = b''
        self._frag = b''
        self._done = False
        sock.readyRead.connect(self._on_ready)
        sock.disconnected.connect(self._on_disconnected)

    # ----------------------------------------------------------------- send

    def send(self, obj):
        if not self.open:
            return
        self._send_frame(OP_TEXT, json.dumps(obj, separators=(',', ':')).encode())

    def close(self):
        if self.open:
            self._send_frame(OP_CLOSE, struct.pack('!H', 1000))
        self.sock.disconnectFromHost()

    def _send_frame(self, opcode, payload):
        n = len(payload)
        if n < 126:
            head = struct.pack('!BB', 0x80 | opcode, n)
        elif n < 1 << 16:
            head = struct.pack('!BBH', 0x80 | opcode, 126, n)
        else:
            head = struct.pack('!BBQ', 0x80 | opcode, 127, n)
        self.sock.write(head + payload)

    # -------------------------------------------------------------- receive

    def _on_ready(self):
        self._buf += bytes(self.sock.readAll())
        if not self.open:
            self._handshake()
        if self.open:
            self._parse_frames()

    def _handshake(self):
        end = self._buf.find(b'\r\n\r\n')
        if end < 0:
            if len(self._buf) > 16384:
                self.sock.abort()
            return
        head, self._buf = self._buf[:end].decode('latin-1'), self._buf[end + 4:]
        lines = head.split('\r\n')
        headers = {}
        for line in lines[1:]:
            name, _, value = line.partition(':')
            headers[name.strip().lower()] = value.strip()

        self.origin = headers.get('origin', '')
        if not self.origin.startswith(ALLOWED_ORIGIN_PREFIXES):
            self._reject(b'403 Forbidden')
            return
        key = headers.get('sec-websocket-key', '')
        if headers.get('upgrade', '').lower() != 'websocket' or not key:
            if lines[0].split(' ')[:2] == ['GET', PROBE_PATH]:
                self._probe_reply()
            else:
                self._reject(b'400 Bad Request')
            return

        accept = base64.b64encode(hashlib.sha1(key.encode() + GUID).digest())
        self.sock.write(
            b'HTTP/1.1 101 Switching Protocols\r\n'
            b'Upgrade: websocket\r\nConnection: Upgrade\r\n'
            b'Sec-WebSocket-Accept: ' + accept + b'\r\n\r\n'
        )
        self.open = True
        self.opened.emit()

    def _probe_reply(self):
        """
        Plain HTTP "is the agent here?" for extensions. Browsers log every failed
        WebSocket attempt as an extension error, but not a failed fetch() the
        code catches — so they ask here first and only then open the socket.
        """
        body = json.dumps({'agent': 'quickjump', 'v': 1}).encode()
        self.sock.write(
            b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nCache-Control: no-store\r\n'
            b'Access-Control-Allow-Origin: ' + self.origin.encode('latin-1') + b'\r\n'
            b'Content-Length: ' + str(len(body)).encode() + b'\r\nConnection: close\r\n\r\n' + body
        )
        self.sock.disconnectFromHost()

    def _reject(self, status):
        self.sock.write(b'HTTP/1.1 ' + status + b'\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
        self.sock.disconnectFromHost()

    def _parse_frames(self):
        while True:
            buf = self._buf
            if len(buf) < 2:
                return
            b0, b1 = buf[0], buf[1]
            fin, opcode = b0 & 0x80, b0 & 0x0F
            masked, n = b1 & 0x80, b1 & 0x7F
            pos = 2
            if n == 126:
                if len(buf) < 4:
                    return
                n = struct.unpack_from('!H', buf, 2)[0]
                pos = 4
            elif n == 127:
                if len(buf) < 10:
                    return
                n = struct.unpack_from('!Q', buf, 2)[0]
                pos = 10
            if n > MAX_MESSAGE:
                self.sock.abort()
                return
            mask = b''
            if masked:
                if len(buf) < pos + 4:
                    return
                mask = buf[pos:pos + 4]
                pos += 4
            if len(buf) < pos + n:
                return
            payload = buf[pos:pos + n]
            self._buf = buf[pos + n:]
            if mask:
                payload = bytes(c ^ mask[i & 3] for i, c in enumerate(payload))
            self._on_frame(fin, opcode, payload)
            if not self.open:
                return

    def _on_frame(self, fin, opcode, payload):
        if opcode == OP_PING:
            self._send_frame(OP_PONG, payload)
        elif opcode == OP_CLOSE:
            self.close()
            self.open = False
        elif opcode in (OP_TEXT, OP_CONT):
            self._frag += payload
            if len(self._frag) > MAX_MESSAGE:
                self.sock.abort()
                return
            if fin:
                data, self._frag = self._frag, b''
                try:
                    obj = json.loads(data.decode('utf-8'))
                except (UnicodeDecodeError, ValueError):
                    return
                if isinstance(obj, dict):
                    self.message.emit(obj)

    def _on_disconnected(self):
        self.open = False
        if not self._done:
            self._done = True
            self.closed.emit()
        self.sock.deleteLater()
        self.deleteLater()


class WsServer(QObject):
    connected = pyqtSignal(object)  # WsClient

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server = QTcpServer(self)
        self._server.newConnection.connect(self._on_new)

    def listen(self, port):
        if self._server.isListening():
            self._server.close()
        # 127.0.0.1 only — never reachable from the network.
        return self._server.listen(QHostAddress(QHostAddress.SpecialAddress.LocalHost), port)

    def error(self):
        return self._server.errorString()

    def _on_new(self):
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            client = WsClient(sock, self)
            # Announce only after the handshake, so rejected pages never show
            # up as clients.
            client.opened.connect(lambda c=client: self.connected.emit(c))
