"""
OrbitGuard - precomputed watchlist alerts + WebSocket push
------------------------------------------------------------
Polling /watchlist/alerts costs a full catalog screening (about 9 s) per request. Instead a
background job screens ahead of time and pushes the result:

    * One screening pass per cycle covers EVERY interested user's satellites (alert_service.screen),
      then each user's feed is cut from it. Ten users cost about the same as one.
    * "Interested" = has an open WebSocket, hit /watchlist/alerts/latest recently, or just
      changed their watchlist. Nobody else is computed, so an idle server does no work.
    * A new connection gets the last snapshot immediately (milliseconds); only a user with no
      snapshot yet waits for a computation.
    * After each cycle the new snapshot is diffed against the previous one, so clients can show
      "NEW close approach" without comparing lists themselves.

Protocol on /ws/alerts (JSON text frames)
    client -> server   {"type":"auth","token":"<JWT>"}   first message, within 10 s (a token in the
                                                         URL would end up in access logs)
                       {"type":"refresh"}                ask for a recompute (rate limited)
                       {"type":"pong"}                   optional reply to a ping
    server -> client   {"type":"hello", ...}             after auth: refresh interval, window
                       {"type":"computing"}              no snapshot yet; one is on its way
                       {"type":"snapshot","snapshot":S}  first snapshot of this connection
                       {"type":"update","snapshot":S,"changes":C}   something changed
                       {"type":"ping","computed_at_utc":...}        a cycle ran, nothing at all changed
                       {"type":"error","code":...,"detail":...}
    close codes        4401 not authenticated / token expired, 4403 bad origin,
                       4429 too many connections

Limits: the state lives in this process's memory, like the rate limiters. Run ONE worker
(the Dockerfile already does); with several, move snapshots and fan-out to Redis.
"""

import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi import HTTPException

import alert_service as svc_alerts
import auth
import config
from alert_service import RISK_RANK, Params
from ratelimit import SlidingWindowLimiter

log = logging.getLogger("uvicorn.error")
router = APIRouter()

AUTH_TIMEOUT_S = 10.0
HEARTBEAT_S = 30.0
SEND_TIMEOUT_S = 5.0
MAX_CONNECTIONS_PER_USER = 5
MAX_CONNECTIONS_TOTAL = 200
MATCH_WINDOW_S = 30 * 60        # same pair, TCA within 30 min = the same event seen again

_refresh_limiter = SlidingWindowLimiter(max_events=2, window_seconds=60)


def reset_rate_limits() -> None:
    _refresh_limiter.reset()


# ============================ diffing two snapshots ============================

def _pair(c: dict) -> tuple[int, int]:
    return tuple(sorted((c["object_1"]["norad_id"], c["object_2"]["norad_id"])))


def _t(c: dict) -> float:
    return datetime.fromisoformat(c["tca_utc"]).timestamp()


def _fingerprint(c: dict) -> tuple:
    """What a user would see change: the numbers are rounded so numerical noise is not a change."""
    return (round(c["miss_distance_km"], 1), c["risk_level"], c["tca_utc"][:16])


def _brief(c: dict) -> dict:
    return {"norad_ids": list(_pair(c)), "tca_utc": c["tca_utc"], "miss_distance_km": c["miss_distance_km"]}


def diff_snapshots(prev: dict | None, new: dict) -> dict | None:
    """
    What changed between two alert feeds (None when there is no previous feed to compare).
      new        close approaches that were not predicted before (full records)
      escalated  the same event, now at a higher risk level (full record + previous_risk)
      cleared    predicted before, still in the future, no longer predicted (new TLE data)
      expired    predicted before and its time of closest approach has now passed (normal)
      updated    still predicted, but its miss distance or TCA moved noticeably (new TLE data)
      notable    True when a user should be alerted: new, escalated, cleared or a satellite
                 became (un)available. Expiry and small refinements are not "notable".
      changed    True when the feed differs AT ALL from the previous one. The server pushes a full
                 snapshot whenever this is true, so a client never keeps showing stale rows
                 (e.g. alerts of a satellite the user just removed from the watchlist).
    Events are matched by object pair and a TCA within 30 minutes, so the small drift of a
    refined TCA between cycles is not reported as "one cleared, one new".
    """
    if prev is None:
        return None
    old_by_pair = defaultdict(list)
    for c in prev["conjunctions"]:
        old_by_pair[_pair(c)].append(c)
    matched_ids = set()
    changes = {"new": [], "escalated": [], "cleared": [], "expired": [], "updated": []}
    for c in new["conjunctions"]:
        best = None
        for o in old_by_pair.get(_pair(c), []):
            if id(o) in matched_ids:
                continue
            gap = abs(_t(o) - _t(c))
            if gap <= MATCH_WINDOW_S and (best is None or gap < best[0]):
                best = (gap, o)
        if best is None:
            changes["new"].append(c)
            continue
        o = best[1]
        matched_ids.add(id(o))
        if RISK_RANK[c["risk_level"]] > RISK_RANK[o["risk_level"]]:
            changes["escalated"].append({**c, "previous_risk": o["risk_level"]})
        elif _fingerprint(c) != _fingerprint(o):
            changes["updated"].append(_brief(c))
    now = datetime.fromisoformat(new["computed_at_utc"]).timestamp()
    for o in prev["conjunctions"]:
        if id(o) in matched_ids:
            continue
        changes["expired" if _t(o) <= now else "cleared"].append(_brief(o))

    old_status = {s["norad_id"]: s["status"] for s in prev["satellites"]}
    changes["status_changed"] = [{"norad_id": s["norad_id"], "from": old_status[s["norad_id"]], "to": s["status"]}
                                 for s in new["satellites"]
                                 if s["norad_id"] in old_status and old_status[s["norad_id"]] != s["status"]]
    changes["notable"] = bool(changes["new"] or changes["escalated"] or changes["cleared"]
                              or changes["status_changed"])
    changes["changed"] = bool(changes["notable"] or changes["expired"] or changes["updated"]
                              or new["watchlist_count"] != prev["watchlist_count"])
    return changes


# ============================ the hub ============================

class _Conn:
    """A WebSocket plus a lock, so the job's pushes and the handler's pings never interleave."""

    def __init__(self, ws: WebSocket, user_id: int):
        self.ws, self.user_id, self._lock = ws, user_id, asyncio.Lock()

    async def send(self, message: dict) -> bool:
        try:
            async with self._lock:
                await asyncio.wait_for(self.ws.send_text(json.dumps(message)), SEND_TIMEOUT_S)
            return True
        except Exception:            # closed, reset, or too slow: the handler cleans up
            return False


class AlertHub:
    def __init__(self, params: Params, interval_seconds: float = 300.0, idle_ttl_seconds: float = 900.0,
                 min_gap_seconds: float = 2.0, debounce_seconds: float = 0.5):
        self.params = params
        self.interval = interval_seconds
        self.idle_ttl = idle_ttl_seconds
        self.min_gap = min_gap_seconds
        self.debounce = debounce_seconds
        self.running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._wake: asyncio.Event | None = None
        self._conns: dict[int, set[_Conn]] = {}
        self._snapshots: dict[int, dict] = {}
        self._last_seen: dict[int, float] = {}
        self._dirty: set[int] = set()
        self.last_error: str | None = None
        self.cycles = 0

    # ---------- lifecycle ----------
    async def start(self) -> None:
        if self.running:
            return
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        self.running = True
        self._task = asyncio.create_task(self._run(), name="alert-hub")

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        for conns in list(self._conns.values()):
            for c in list(conns):
                try:
                    await c.ws.close(code=1001)
                except Exception:
                    pass
        self._conns.clear()

    # ---------- called from request handlers ----------
    def _interested(self, user_id: int) -> bool:
        return (user_id in self._conns
                or time.monotonic() - self._last_seen.get(user_id, float("-inf")) < self.idle_ttl)

    def latest(self, user_id: int) -> dict | None:
        return self._snapshots.get(user_id)

    def touch(self, user_id: int) -> None:
        """Mark a user as interested (REST callers). Safe to call from a worker thread."""
        if self.running and self._loop is not None:
            self._loop.call_soon_threadsafe(self._touch, user_id)

    def _touch(self, user_id: int) -> None:
        self._last_seen[user_id] = time.monotonic()
        if user_id not in self._snapshots:
            self._dirty.add(user_id)
            self._wake.set()

    def mark_dirty(self, user_id: int) -> None:
        """The user's watchlist changed. Safe to call from a worker thread (sync endpoints)."""
        if not self.running or self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._mark_dirty, user_id)

    def _mark_dirty(self, user_id: int) -> None:
        if self._interested(user_id):
            self._dirty.add(user_id)
            self._wake.set()
        else:
            self._snapshots.pop(user_id, None)         # never serve a feed for an outdated watchlist

    def request_refresh(self, user_id: int) -> None:
        self._dirty.add(user_id)
        self._wake.set()

    def connection_count(self, user_id: int | None = None) -> int:
        if user_id is None:
            return sum(len(s) for s in self._conns.values())
        return len(self._conns.get(user_id, ()))

    async def register(self, user_id: int, ws: WebSocket) -> "_Conn | None":
        if (self.connection_count() >= MAX_CONNECTIONS_TOTAL
                or self.connection_count(user_id) >= MAX_CONNECTIONS_PER_USER):
            return None
        conn = _Conn(ws, user_id)
        self._conns.setdefault(user_id, set()).add(conn)
        self._last_seen[user_id] = time.monotonic()
        return conn

    def unregister(self, conn: "_Conn") -> None:
        conns = self._conns.get(conn.user_id)
        if conns:
            conns.discard(conn)
            if not conns:
                del self._conns[conn.user_id]
        self._last_seen[conn.user_id] = time.monotonic()    # grace period before it is forgotten

    # ---------- the job ----------
    async def _run(self) -> None:
        last_end = float("-inf")
        while self.running:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.interval)
                await asyncio.sleep(self.debounce)         # batch a burst of changes into one cycle
            except asyncio.TimeoutError:
                pass
            # leading-edge throttle: an idle job reacts at once, but back-to-back cycles
            # (someone adding satellites in a loop) are spaced at least min_gap apart
            pause = self.min_gap - (time.monotonic() - last_end)
            if pause > 0:
                await asyncio.sleep(pause)
            self._wake.clear()
            try:
                await self._cycle()
                self.last_error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:                       # keep the job alive; retry next cycle
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.exception("alert cycle failed")
                await self._broadcast_error(self.last_error)
            self.cycles += 1
            last_end = time.monotonic()

    def _forget_idle(self) -> None:
        now = time.monotonic()
        for uid in [u for u in self._snapshots if u not in self._conns
                    and now - self._last_seen.get(u, float("-inf")) >= self.idle_ttl]:
            del self._snapshots[uid]
        for uid in [u for u, t in self._last_seen.items()
                    if u not in self._conns and now - t >= self.idle_ttl]:
            del self._last_seen[uid]

    async def _cycle(self) -> None:
        self._forget_idle()
        now = time.monotonic()
        users = {u for u in self._conns} | set(self._dirty) | {
            u for u, t in self._last_seen.items() if now - t < self.idle_ttl}
        self._dirty.clear()
        if not users:
            return
        started = time.perf_counter()
        snapshots = await asyncio.to_thread(self._compute, sorted(users))
        took = time.perf_counter() - started
        for uid, snap in snapshots.items():
            snap["compute_seconds"] = round(took, 2)
            changes = diff_snapshots(self._snapshots.get(uid), snap)
            first = uid not in self._snapshots
            self._snapshots[uid] = snap
            await self._push(uid, snap, changes, first)

    def _compute(self, user_ids: list[int]) -> dict[int, dict]:
        """Blocking part, run in a thread: load watchlists, ONE screening pass, per-user feeds."""
        watched = {uid: _load_watchlist(uid) for uid in user_ids}
        union = {w["norad_id"] for ws_ in watched.values() for w in ws_}
        scr = svc_alerts.screen(union, self.params) if union else None
        computed = datetime.now(timezone.utc).isoformat()
        out = {}
        for uid, w in watched.items():
            snap = svc_alerts.build_response(w, scr, self.params)
            snap["computed_at_utc"] = computed
            out[uid] = snap
        return out

    async def _push(self, uid: int, snap: dict, changes: dict | None, first: bool) -> None:
        conns = list(self._conns.get(uid, ()))
        if not conns:
            return
        if changes is None or first:
            msg = {"type": "snapshot", "snapshot": snap}
        elif changes["changed"]:
            msg = {"type": "update", "snapshot": snap, "changes": changes}
        else:
            msg = {"type": "ping", "computed_at_utc": snap["computed_at_utc"]}
        await asyncio.gather(*(c.send(msg) for c in conns))

    async def _broadcast_error(self, detail: str) -> None:
        msg = {"type": "error", "code": "compute_failed", "detail": detail}
        for conns in list(self._conns.values()):
            await asyncio.gather(*(c.send(msg) for c in list(conns)))


def _load_watchlist(user_id: int) -> list[dict]:
    conn = auth._get_conn()
    try:
        rows = conn.execute("SELECT norad_id, name FROM watchlist WHERE user_id = ? ORDER BY added_at",
                            (user_id,)).fetchall()
    except Exception:            # table is created on first watchlist use
        return []
    finally:
        conn.close()
    return [dict(r) for r in rows]


def default_params() -> Params:
    j = config.ALERT_JOB
    return Params(group=j["group"], hours=j["hours"], threshold_km=j["threshold_km"])


hub = AlertHub(default_params(), interval_seconds=config.ALERT_JOB["interval_seconds"])


# ============================ WebSocket endpoint ============================

def _origin_allowed(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    if origin is None or "*" in config.CORS_ORIGINS:     # non-browser clients send no Origin
        return True
    return origin.rstrip("/") in config.CORS_ORIGINS


async def _authenticate(ws: WebSocket):
    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), AUTH_TIMEOUT_S))
        if not isinstance(first, dict) or first.get("type") != "auth" or not isinstance(first.get("token"), str):
            raise ValueError("first message must be {\"type\":\"auth\",\"token\":...}")
        return await asyncio.to_thread(auth.user_from_token, first["token"])
    except (asyncio.TimeoutError, WebSocketDisconnect):
        raise
    except HTTPException as exc:
        raise PermissionError(exc.detail)
    except (ValueError, KeyError, TypeError) as exc:
        raise PermissionError(str(exc))


@router.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    h = hub
    if not h.running:
        await ws.close(code=1013)                       # try again later: the job is off
        return
    if not _origin_allowed(ws):
        await ws.close(code=4403)
        return
    await ws.accept()
    try:
        user, exp = await _authenticate(ws)
    except WebSocketDisconnect:
        return
    except asyncio.TimeoutError:
        await ws.close(code=4401, reason="auth timeout")
        return
    except PermissionError as exc:
        await ws.close(code=4401, reason=str(exc)[:100])
        return

    conn = await h.register(user["id"], ws)
    if conn is None:
        await ws.close(code=4429, reason="too many connections")
        return
    try:
        await conn.send({"type": "hello", "refresh_interval_seconds": h.interval,
                         "hours": h.params.hours, "threshold_km": h.params.threshold_km,
                         "group": h.params.group, "token_expires_at": exp})
        snap = h.latest(user["id"])
        if snap is not None:
            await conn.send({"type": "snapshot", "snapshot": snap})
        else:
            await conn.send({"type": "computing"})
            h.request_refresh(user["id"])
        while True:
            left = exp - time.time()
            if left <= 0:
                await conn.send({"type": "error", "code": "token_expired", "detail": "log in again"})
                await ws.close(code=4401, reason="token expired")
                return
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=min(HEARTBEAT_S, left))
            except asyncio.TimeoutError:
                if not await conn.send({"type": "ping", "ts": time.time()}):
                    return
                continue
            try:
                msg = json.loads(raw)
                kind = msg.get("type") if isinstance(msg, dict) else None
            except ValueError:
                kind = None
            if kind == "refresh":
                wait = _refresh_limiter.hit(f"user:{user['id']}")
                if wait:
                    await conn.send({"type": "error", "code": "rate_limited",
                                     "detail": f"try again in {int(wait) + 1} s"})
                else:
                    h.request_refresh(user["id"])
                    await conn.send({"type": "computing"})
            elif kind != "pong":
                await conn.send({"type": "error", "code": "bad_message",
                                 "detail": "expected {\"type\":\"refresh\"} or {\"type\":\"pong\"}"})
    except WebSocketDisconnect:
        pass
    finally:
        h.unregister(conn)
