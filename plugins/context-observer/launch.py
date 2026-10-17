#!/usr/bin/env python3
"""Bootstrap an isolated Python runtime, then replace this process with MCP stdio."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import venv

ROOT = Path(__file__).resolve().parent

def data_directory():
    override = os.environ.get('CONTEXT_OBSERVER_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Caches/codex-context-observer'
    return Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'codex-context-observer'

def ensure_runtime(root=ROOT):
    requirements = root / 'requirements.txt'
    identity = (sys.version + '\n' + sys.executable).encode() + requirements.read_bytes()
    runtime = data_directory() / ('python-' + hashlib.sha256(identity).hexdigest()[:16])
    python = runtime / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    marker = runtime / '.ready'
    if python.is_file() and marker.is_file():
        return python
    runtime.parent.mkdir(parents=True, exist_ok=True)
    lock = runtime.with_suffix('.lock')
    deadline = time.monotonic() + 150
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if python.is_file() and marker.is_file():
                return python
            if time.monotonic() >= deadline:
                raise RuntimeError(f'Outro processo está preparando o Python. Se ele já terminou, remova somente o bloqueio vazio {lock} e tente novamente.')
            time.sleep(0.25)
    try:
        if python.is_file() and marker.is_file():
            return python
        if runtime.exists():
            shutil.rmtree(runtime)
        print('Context Observer: preparando dependências Python na primeira abertura…', file=sys.stderr, flush=True)
        venv.EnvBuilder(with_pip=True).create(runtime)
        subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input',
                        '-r', str(requirements)], check=True, stdout=sys.stderr, stderr=sys.stderr, timeout=120)
        subprocess.run([str(python), '-c', 'import tiktoken; tiktoken.get_encoding("o200k_base")'],
                       env={**os.environ,'TIKTOKEN_CACHE_DIR':str(root/'tokenizer-cache')},
                       check=True, stdout=sys.stderr, stderr=sys.stderr, timeout=15)
        marker.touch()
        return python
    finally:
        lock.rmdir()

def main():
    if sys.version_info < (3, 10):
        raise RuntimeError('Instale Python 3.10 ou posterior e deixe python3 no PATH do Codex.')
    python = ensure_runtime()
    os.execv(str(python), [str(python), str(ROOT / 'mcp_server.py')])

if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'Context Observer: não foi possível iniciar: {error}', file=sys.stderr)
        sys.exit(1)
