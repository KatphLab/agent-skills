"""Minimal local Orca RPC transport, matching src/cli/runtime/transport.ts."""
import json
import os
from pathlib import Path
import socket
import sys
import uuid


class RpcError(RuntimeError):
    def __init__(self, method, receipt):
        self.receipt = receipt
        error = receipt.get('error', {})
        super().__init__(f'{method}: {error.get("code", "error")}: {error.get("message", "request refused")}')


def metadata_path():
    if os.environ.get('ORCA_USER_DATA_PATH'):
        root = Path(os.environ['ORCA_USER_DATA_PATH'])
    elif sys.platform == 'darwin':
        root = Path.home() / 'Library/Application Support/orca'
    elif sys.platform == 'linux':
        root = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'orca'
    else:
        raise RuntimeError('This local helper supports Linux/macOS Unix sockets, not Windows/WSL.')
    return root / 'orca-runtime.json'


class LocalRuntime:
    def __init__(self):
        for key in ('ORCA_ENVIRONMENT', 'ORCA_PAIRING_CODE', 'ORCA_REMOTE_PAIRING', 'WSL_DISTRO_NAME'):
            if os.environ.get(key):
                raise RuntimeError('Local native Orca only; remote/WSL routing is unsupported.')
        path = metadata_path()
        try:
            self.metadata = json.loads(path.read_text())
        except (OSError, ValueError):
            raise RuntimeError(f'Cannot read Orca runtime metadata at {path}. Start Orca first.') from None
        transports = self.metadata.get('transports') or [self.metadata.get('transport', {})]
        transport = next((t for t in transports if t.get('kind') == 'unix'), None)
        if not transport or not self.metadata.get('authToken') or not self.metadata.get('runtimeId'):
            raise RuntimeError('Orca metadata has no authenticated local Unix transport.')
        self.endpoint = transport['endpoint']

    def call(self, method, params=None, timeout=180):
        request_id = str(uuid.uuid4())
        request = {'id': request_id, 'authToken': self.metadata['authToken'],
                   'method': method, 'params': params or {}}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(self.endpoint)
            connection.sendall((json.dumps(request) + '\n').encode())
            with connection.makefile('rb') as stream:
                while True:
                    line = stream.readline(8_000_001)
                    if not line:
                        raise RuntimeError(f'{method}: connection closed before receipt; outcome unknown. Do not relaunch blindly.')
                    if len(line) > 8_000_000 or not line.endswith(b'\n'):
                        raise RuntimeError(f'{method}: oversized/incomplete response')
                    frame = json.loads(line)
                    if frame.get('_keepalive') is True:
                        continue
                    if frame.get('id') != request_id or type(frame.get('ok')) is not bool:
                        raise RuntimeError(f'{method}: invalid/mismatched response')
                    runtime_id = frame.get('_meta', {}).get('runtimeId')
                    if runtime_id and runtime_id != self.metadata['runtimeId']:
                        raise RuntimeError(f'{method}: runtime changed; outcome unknown')
                    if not frame['ok']:
                        raise RpcError(method, frame)
                    return frame['result']

    def preflight(self):
        status = self.call('status.get')
        capabilities = status.get('capabilities', [])
        required = ('agent.launch.v2', 'agent.launch.replay.v1')
        missing = [cap for cap in required if cap not in capabilities]
        if missing:
            raise RuntimeError('Update Orca: required launch API capabilities missing: ' + ', '.join(missing))
        return status
