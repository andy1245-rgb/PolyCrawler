import hashlib
import json
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx

_secret = re.compile(r"(/v2/)[^/\s\"']+|(apikey=)[^&\s]+", re.IGNORECASE)


@dataclass
class JsonRequest:
    url: str
    params: dict[str, Any] = field(default_factory=dict)
    cacheKind: str | None = None
    cacheKey: str | None = None
    refresh: bool = False
    method: str = "GET"
    body: Any = None


@dataclass
class HttpStats:
    calls: dict[str, int] = field(default_factory=dict)
    cacheHits: dict[str, int] = field(default_factory=dict)
    rateLimits: dict[str, int] = field(default_factory=dict)

    def add(self, bucket: str, host: str) -> None:
        target = getattr(self, bucket)
        target[host] = target.get(host, 0) + 1


class HostLimiter:
    """Spaces request starts. penalize() widens the gap after a 429."""

    def __init__(self, requestsPerSec: float, clock: Callable[[], float] | None = None, sleep: Callable[[float], None] | None = None, maxInterval: float = 30.0) -> None:
        self.requestsPerSec = requestsPerSec
        self.minInterval = 1.0 / requestsPerSec if requestsPerSec > 0 else 0.0
        self.interval = self.minInterval
        self.maxInterval = maxInterval
        self.nextAt = 0.0
        self.clock = clock or time.monotonic
        self.sleep = sleep or time.sleep
        self.lock = threading.Lock()

    def acquire(self) -> None:
        if self.minInterval <= 0:
            return
        with self.lock:
            now = self.clock()
            wait = max(0.0, self.nextAt - now)
            self.nextAt = max(self.nextAt, now) + self.interval
        if wait:
            self.sleep(wait)

    def penalize(self) -> None:
        with self.lock:
            self.interval = min(self.maxInterval, max(self.minInterval, self.interval * 2))
            self.nextAt = max(self.nextAt, self.clock() + self.interval)

    def relax(self) -> None:
        # A burst of 429s must not leave the host at the slow cap after it recovers.
        with self.lock:
            self.interval = max(self.minInterval, (self.interval + self.minInterval) / 2)


def cachePath(dataDir: str, kind: str, key: str) -> Path:
    safe = key.replace("/", "_")
    if len(safe) > 180:
        safe = safe[:80] + "_" + hashlib.sha256(key.encode()).hexdigest()[:24]
    return Path(dataDir) / "raw" / kind / f"{safe}.json"


def writeJson(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def redactSecrets(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return (match.group(2) or "/v2/") + "***"

    return _secret.sub(repl, text)


def rateLimitMessage(payload: Any) -> bool:
    # Relay's success body has a deprecation note that mentions "rate limit".
    # Only a top-level message, or a string `result`, with no data payload counts.
    if not isinstance(payload, dict):
        return False
    if isinstance(payload.get("requests"), list) or isinstance(payload.get("result"), list):
        return False
    result = payload.get("result")
    text = f"{payload.get('message') or ''} {result if isinstance(result, str) else ''}".lower()
    return "rate limit" in text or "max rate" in text


class HttpSession:
    def __init__(self, client: httpx.Client, hostRates: dict[str, float] | None = None, defaultRate: float = 0.0, dataDir: str | None = None, maxAttempts: int = 6, clock: Callable[[], float] | None = None, sleep: Callable[[float], None] | None = None, rng: Callable[[], float] | None = None) -> None:
        self.client = client
        self.hostRates = dict(hostRates or {})
        self.defaultRate = defaultRate
        self.dataDir = dataDir
        self.maxAttempts = maxAttempts
        self.clock = clock or time.monotonic
        self.sleep = sleep or time.sleep
        self.rng = rng or random.random
        self.stats = HttpStats()
        self.limiters: dict[str, HostLimiter] = {}
        self.gates: dict[str, threading.Semaphore] = {}
        self.lock = threading.Lock()

    def limiterFor(self, url: str) -> HostLimiter | None:
        host = urlsplit(url).hostname or ""
        rate = self.hostRates.get(host, self.defaultRate)
        if rate <= 0:
            return None
        with self.lock:
            found = self.limiters.get(host)
            if found is None:
                found = HostLimiter(rate, self.clock, self.sleep)
                self.limiters[host] = found
            return found

    def getJson(self, url: str, params: dict[str, Any] | None = None, cacheKind: str | None = None, cacheKey: str | None = None, refresh: bool = False) -> Any:
        return self._cached(url, params or {}, None, cacheKind, cacheKey, refresh)

    def postJson(self, url: str, body: Any, cacheKind: str | None = None, cacheKey: str | None = None, refresh: bool = False) -> Any:
        return self._cached(url, {}, body, cacheKind, cacheKey, refresh)

    def fetchMany(self, requests: list[JsonRequest], maxWorkers: int = 8) -> list[Any]:
        if not requests:
            return []

        def one(req: JsonRequest) -> Any:
            if req.method.upper() == "POST":
                return self.postJson(req.url, req.body, req.cacheKind, req.cacheKey, req.refresh)
            return self.getJson(req.url, req.params, req.cacheKind, req.cacheKey, req.refresh)

        workers = max(1, min(maxWorkers, len(requests)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(one, requests))

    def _cached(self, url: str, params: dict[str, Any], body: Any, cacheKind: str | None, cacheKey: str | None, refresh: bool) -> Any:
        host = urlsplit(url).hostname or ""
        path = cachePath(self.dataDir, cacheKind, cacheKey) if self.dataDir and cacheKind and cacheKey else None
        if path is not None and path.exists() and not refresh:
            self.stats.add("cacheHits", host)
            return json.loads(path.read_text())
        payload = self._fetch(url, params, body, host)
        if path is not None:
            writeJson(path, payload)
        return payload

    def _gate(self, url: str) -> threading.Semaphore | None:
        host = urlsplit(url).hostname or ""
        rate = self.hostRates.get(host, self.defaultRate)
        if rate <= 0:
            return None
        with self.lock:
            gate = self.gates.get(host)
            if gate is None:
                gate = threading.Semaphore(1)
                self.gates[host] = gate
            return gate

    def _fetch(self, url: str, params: dict[str, Any], body: Any, host: str) -> Any:
        # One in-flight request per limited host so a worker pool cannot burst ahead of a 429.
        gate = self._gate(url)
        if gate is not None:
            gate.acquire()
        try:
            return self._fetchLimited(url, params, body, host)
        finally:
            if gate is not None:
                gate.release()

    def _fetchLimited(self, url: str, params: dict[str, Any], body: Any, host: str) -> Any:
        delay = 0.5
        last = "request failed"
        for _attempt in range(self.maxAttempts):
            limiter = self.limiterFor(url)
            if limiter is not None:
                limiter.acquire()
            try:
                response = self.client.get(url, params=params) if body is None else self.client.post(url, json=body)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = redactSecrets(str(exc))[:300]
                self.sleep(delay * (1.0 + self.rng() * 0.25))
                delay *= 2
                continue
            self.stats.add("calls", host)
            payload = _readJson(response)
            limited = response.status_code == 429 or rateLimitMessage(payload)
            if limited or response.status_code >= 500:
                if limited:
                    self.stats.add("rateLimits", host)
                    if limiter is not None:
                        limiter.penalize()
                last = redactSecrets(f"{response.status_code} {url}")[:300]
                self.sleep(delay * (1.0 + self.rng() * 0.25))
                delay *= 2
                continue
            if response.status_code >= 400:
                raise RuntimeError(redactSecrets(f"{response.status_code} {url} {response.text[:300]}"))
            if payload is None:
                raise RuntimeError(redactSecrets(f"non-json {response.status_code} {url}"))
            if limiter is not None:
                limiter.relax()
            return payload
        raise RuntimeError(last)


def _readJson(response: httpx.Response) -> Any:
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError):
        return None
