"""Ephemeral HOST-only presence; no files, source writes, or edit synchronization."""
from __future__ import annotations

import json
import re
import secrets
import threading
from collections import deque

PRESENCE_PATH = "/_presence"


def user_identity(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise ValueError("user identity must be 1-64 letters, digits, underscores or hyphens")
    return value


class Presence:
    def __init__(self):
        self.token = secrets.token_urlsafe(24)
        self.condition = threading.Condition()
        self.users = {}
        self.events = deque(maxlen=64)
        self.sequence = 0

    def _broadcast(self, kind, user):
        self.sequence += 1
        data = json.dumps({"type": kind, "user": user, "users": list(self.users.values()),
                           "scope": "preview-only"}, ensure_ascii=True)
        self.events.append((self.sequence, f"event: {kind}\ndata: {data}\n\n".encode()))
        self.condition.notify_all()

    def join(self, identity, name):
        user_identity(identity)
        if not isinstance(name, str) or not 1 <= len(name) <= 64 or any(ord(c) < 32 for c in name):
            raise ValueError("presence name must be 1-64 printable characters")
        with self.condition:
            if identity in self.users:
                raise ValueError("presence user already connected")
            if len(self.users) >= 8:
                raise ValueError("fixture presence supports at most eight connections")
            cursor = self.sequence
            self.users[identity] = {"userId": identity, "name": name, "selector": "", "property": ""}
            self._broadcast("user-join", self.users[identity])
            return cursor

    def leave(self, identity):
        with self.condition:
            user = self.users.pop(identity)
            self._broadcast("user-leave", user)

    def edit(self, event):
        if not isinstance(event, dict) or set(event) != {"userId", "type", "selector", "property"}:
            raise ValueError("presence edit requires userId, type, selector and property only")
        if event["type"] not in ("user-editing-element", "user-committed-edit"):
            raise ValueError("unsupported presence event")
        user_identity(event["userId"])
        for key, limit in (("selector", 512), ("property", 64)):
            value = event[key]
            if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
                raise ValueError(f"invalid presence {key}")
        with self.condition:
            if event["userId"] not in self.users:
                raise ValueError("presence user is not connected")
            user = {**self.users[event["userId"]], "selector": event["selector"],
                    "property": event["property"]}
            self.users[event["userId"]] = user
            self._broadcast(event["type"], user)

    def after(self, cursor):
        with self.condition:
            self.condition.wait_for(lambda: self.sequence > cursor, timeout=1)
            if self.events and cursor < self.events[0][0] - 1:
                raise ValueError("presence subscriber fell behind; reconnect required")
            return [(number, data) for number, data in self.events if number > cursor]
