"""Read the current CLI auth method only; never return credentials or raw CLI output."""
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone

class AccountStatus:
    def __init__(self,home):
        self.home=home
        self.cached=None
        self.checked=0

    def read(self):
        if self.cached is not None and time.monotonic()-self.checked<60:return self.cached
        mode='unknown'
        executable=os.environ.get('CONTEXT_OBSERVER_CODEX') or shutil.which('codex')
        if executable:
            try:
                result=subprocess.run([executable,'login','status'],capture_output=True,text=True,timeout=4,
                    env={**os.environ,'CODEX_HOME':str(self.home)})
                output=(result.stdout+result.stderr).lower()
                if result.returncode==0:
                    if 'logged in using chatgpt' in output:mode='subscription'
                    elif 'logged in using an api key' in output or 'logged in using api key' in output:mode='api'
            except (OSError,subprocess.TimeoutExpired):pass
        self.cached={'mode':mode,'scope':'current-cli-only','checkedAt':datetime.now(timezone.utc).isoformat()}
        self.checked=time.monotonic()
        return self.cached
