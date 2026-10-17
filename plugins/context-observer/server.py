#!/usr/bin/env python3
"""Local, read-only session collector. No model calls."""
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from composition import Composition
from costs import UsageLedger

ROOT = Path(__file__).resolve().parent

class Collector:
    def __init__(self, path, thread_id, name=None, model=None):
        self.path = Path(path)
        self.thread_id = thread_id
        self.name = name or 'This conversation'
        self.model = model
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        self.offset = 0
        self.inode = None
        self.pending = b''
        self.verified = False
        self.last = None
        self.total = None
        self.window = None
        self.timestamp = None
        self.state = 'unknown'
        self.samples = []
        self.namespaces = []
        self.mcp_catalog = []
        self.skills_catalog = []
        self.composition = Composition()
        self.costs = UsageLedger(self.thread_id)
        self.skills_count = None
        self.compactions = 0
        self.compaction_history = []
        self.pending_compaction = None
        self.invalid_lines = 0
        self.event_count = 0

    def consume(self, event):
        kind, p = event.get('type'), event.get('payload', {})
        if not isinstance(p, dict):
            return
        if kind == 'session_meta':
            if p.get('id') != self.thread_id:
                raise ValueError('The file belongs to a different conversation.')
            self.verified = True
        if not self.verified:
            return
        self.composition.consume(kind, p)
        self.costs.consume(kind, p)
        if kind == 'turn_context' and p.get('model'):
            self.model = p['model']
        if kind == 'world_state':
            state = p.get('state', {})
            if 'tools' in state and isinstance(state['tools'], dict):
                self.namespaces = sorted(state['tools'])
                self.mcp_catalog = [{'name':k,'description':v} for k,v in sorted(state['tools'].items())]
            body = state.get('host_skills', {}).get('body', '')
            if body:
                roots = dict(re.findall(r'^- `(r\d+)` = `([^`]+)`', body, re.M))
                self.skills_catalog = []
                for match in re.finditer(r'^- (.+?): (.*?) \(file: (.+?)\)\s*$', body, re.M):
                    name, description, path = match.groups()
                    prefix, _, suffix = path.partition('/')
                    path = roots.get(prefix, prefix) + ('/' + suffix if suffix else '')
                    self.skills_catalog.append({'name':name,'description':description,'path':path})
                self.skills_count = len(self.skills_catalog)
        if kind == 'compacted' or (kind == 'event_msg' and p.get('type') in ('context_compaction', 'context_compacted')):
            # The canonical record may be followed by a legacy completion marker.
            if kind != 'compacted' and self.pending_compaction is not None:
                return
            self.compactions += 1
            before = {'at':self.timestamp,'input':(self.last or {}).get('input_tokens'),
                      'window':self.window,'accumulated':(self.total or {}).get('total_tokens')}
            entry = {'number':self.compactions,'at':event.get('timestamp'),'before':before,
                     'after':None,'differenceTokens':None,
                     'readableHistoryAvailable':isinstance(p.get('replacement_history'),list)}
            self.compaction_history.append(entry)
            self.compaction_history = self.compaction_history[-100:]
            self.pending_compaction = entry
            self.last = None
            self.composition.rebuild_after_compaction(p if kind == 'compacted' else {})
        if kind != 'event_msg':
            return
        subtype = p.get('type')
        if subtype == 'task_started':
            self.state = 'running'
            if p.get('model_context_window'):
                self.window = p['model_context_window']
        elif subtype in ('task_complete', 'turn_aborted'):
            self.state = 'idle'
        elif subtype == 'token_count' and isinstance(p.get('info'), dict):
            info = p['info']
            if info.get('last_token_usage') is None:
                return
            if self.pending_compaction is not None:
                before = self.pending_compaction['before']
                accumulated = (info.get('total_token_usage') or {}).get('total_tokens')
                inp = info['last_token_usage'].get('input_tokens')
                # Re-emitted snapshots of the old call are not a post-compaction measurement.
                if accumulated is not None and before['accumulated'] is not None:
                    if accumulated <= before['accumulated']:
                        return
                elif inp == before['input']:
                    return
                after = {'at':event.get('timestamp'),'input':inp,
                         'window':info.get('model_context_window') or self.window,'accumulated':accumulated}
                self.pending_compaction['after'] = after
                if isinstance(before['input'], (int,float)) and isinstance(inp, (int,float)):
                    self.pending_compaction['differenceTokens'] = before['input'] - inp
                self.pending_compaction = None
            self.last = info['last_token_usage']
            self.total = info.get('total_token_usage')
            self.window = info.get('model_context_window') or self.window
            self.timestamp = event.get('timestamp')
            self.event_count += 1
            sample = {'at': self.timestamp, 'input': self.last.get('input_tokens'),
                      'accumulated': (self.total or {}).get('total_tokens'), 'window':self.window,
                      'compactionNumber':self.compactions}
            # Repeated snapshots must not be added as new model calls.
            if not self.samples or sample['accumulated'] != self.samples[-1]['accumulated']:
                self.samples.append(sample)
                self.samples = self.samples[-60:]

    def snapshot(self):
        with self.lock:
            stat = self.path.stat()
            if self.inode is not None and (stat.st_ino != self.inode or stat.st_size < self.offset):
                self.reset()
            self.inode = stat.st_ino
            with self.path.open('rb') as source:
                source.seek(self.offset)
                data = source.read()
                self.offset = source.tell()
            lines = (self.pending + data).split(b'\n')
            self.pending = lines.pop()
            for line in lines:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    self.invalid_lines += 1
                    continue
                self.consume(event)
            inp = (self.last or {}).get('input_tokens')
            percent = (100 * inp / self.window) if inp is not None and self.window else None
            inventory = json.loads((ROOT / 'inventory.json').read_text())
            return {
                'threadId': self.thread_id, 'name': self.name, 'model': self.model,
                'verified': self.verified, 'state': self.state,
                'polledAt': datetime.now(timezone.utc).isoformat(),
                'measuredAt': self.timestamp, 'window': self.window,
                'last': self.last, 'accumulated': self.total,
                'inputWindowPercentEstimate': percent,
                'remainingInputWindowEstimate': max(0, self.window - inp) if self.window and inp is not None else None,
                'samples': list(self.samples), 'namespaces': self.namespaces,
                'skillsCount': self.skills_count, 'catalogSnapshot': inventory,
                'mcpCatalog': self.mcp_catalog, 'skillsCatalog': self.skills_catalog,
                'composition': self.composition.snapshot(),
                'costs': self.costs.snapshot(),
                'compactionsObserved': self.compactions,
                'compactionHistory': self.compaction_history,
                'diagnostics': {'tokenEventsObserved': self.event_count, 'invalidLines': self.invalid_lines,
                                'pendingBytes': len(self.pending)},
                'source': {'kind': 'local-session-jsonl', 'path': str(self.path), 'stableApi': False},
                'categoryBreakdownAvailable': False,
            }

def resolve(thread_id, codex_home):
    dbpath = codex_home / 'state_5.sqlite'
    with sqlite3.connect(dbpath.as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT rollout_path, name, model FROM threads WHERE id=?', (thread_id,)).fetchone()
    if not row:
        raise ValueError('Conversation not found in the local index.')
    path = Path(row[0]).resolve()
    if not path.is_relative_to(codex_home.resolve() / 'sessions'):
        raise ValueError('File is outside the active sessions directory.')
    return Collector(path, thread_id, row[1], row[2])
