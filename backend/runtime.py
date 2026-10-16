"""One bounded USB worker, shared snapshots and automatic connection recovery."""
import copy
import queue
import subprocess
import threading
import time
from concurrent.futures import Future, TimeoutError as FutureTimeout

from backend.service import Evo16Service
from backend.health_state import state_for


class Unavailable(RuntimeError):
    pass


class DeviceRuntime:
    def __init__(self, factory=Evo16Service, interval=2.0):
        self.factory = factory
        self.interval = interval
        self.jobs = queue.Queue(maxsize=32)
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.service = None
        self.snapshot = None
        self.snapshot_at = 0.0
        self.meters = None
        self.meters_at = 0.0
        self.last_demand = -float("inf")
        self.next_retry = 0.0
        self.retry_delay = 2.0
        self.last_failure = {}
        self.health_data = {"device": {"connected": False}, "state": "not_ready", "ok": False}
        self.health_at = 0.0
        self.thread = threading.Thread(target=self._run, name="evo16-usb", daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.service:
            self.service._deadline = min(getattr(self.service, "_deadline", float("inf")), time.monotonic() + 1)
        self.thread.join(timeout=5)

    def submit(self, action, timeout=10):
        future = Future()
        deadline = time.monotonic() + timeout
        try:
            self.jobs.put_nowait((future, action, deadline))
        except queue.Full:
            raise Unavailable("Servicio ocupado; reintentar")
        try:
            return future.result(timeout=timeout)
        except FutureTimeout:
            future.cancel()  # A queued write must never execute after its caller timed out.
            raise Unavailable("Tiempo de espera agotado; consultar estado antes de reintentar")

    def health(self):
        with self.lock:
            data = copy.deepcopy(self.health_data)
            age = time.monotonic() - self.health_at if self.health_at else None
        data["sampleAgeSeconds"] = round(age, 3) if age is not None else None
        if age is None or age > 6:
            data.update(ok=False, state="not_ready", stateDetail="Esperando una sonda reciente del equipo")
        return data

    def status(self):
        self.last_demand = time.monotonic()
        return self.submit(self._status)

    def _status(self):
        self._require()
        if self.snapshot is None or time.monotonic() - self.snapshot_at >= self.interval:
            self.snapshot = self.service.get_all_status()
            self.snapshot_at = time.monotonic()
            self.snapshot_epoch = time.time()
        return {**copy.deepcopy(self.snapshot), "status": "ok",
                "sampledAtEpoch": self.snapshot_epoch,
                "sampleAgeSeconds": round(time.monotonic() - self.snapshot_at, 3)}

    def call(self, method, *args, write=False):
        def operation():
            self._require()
            try:
                return getattr(self.service, method)(*args)
            finally:
                if write:
                    self.snapshot = None
                    self.meters = None
        return self.submit(operation)

    def meter_values(self):
        def operation():
            self._require()
            if self.meters is None or time.monotonic() - self.meters_at >= 0.15:
                self.meters = self.service.get_meters()
                self.meters_at = time.monotonic()
            return {**copy.deepcopy(self.meters), "status": "ok",
                    "sampleAgeSeconds": round(time.monotonic() - self.meters_at, 3)}
        return self.submit(operation)

    def reconnect(self):
        def operation():
            self._publish({"connected": False, "helper": False, "reconnecting": True}, False)
            if self.service:
                self.service.disconnect()
            self.service = None
            self.snapshot = None
            self.meters = None
            self.next_retry = 0
            self._refresh()
            return self.health()
        return self.submit(operation)

    def _require(self):
        if not self.service or not self.service._connected:
            raise Unavailable("EVO 16 no disponible; consultar /api/health")

    def _publish(self, dev, official):
        with self.lock:
            self.health_data = {"device": dev, "audientAppRunning": official,
                                **state_for(dev, official)}
            self.health_at = time.monotonic()

    def _refresh(self):
        try:
            official = subprocess.run(["pgrep", "-f", "EVO.app/Contents/MacOS/EVO"],
                                      capture_output=True, timeout=1).returncode == 0
        except Exception:
            official = False
        now = time.monotonic()
        dev = {"connected": False, "helper": False, **self.last_failure}
        try:
            if (not self.service or not self.service._connected) and not official and now >= self.next_retry:
                if self.service:
                    self.service.disconnect()
                self.service = self.factory()
                self.service.connect()
            if self.service and self.service._connected:
                self.service._deadline = time.monotonic() + 5
                dev = self.service.health()
            if not dev.get("connected"):
                if self.service:
                    self.service.disconnect()
                self.snapshot = None
                self.meters = None
                if now >= self.next_retry:
                    self.next_retry = now + self.retry_delay
                    self.retry_delay = min(30, self.retry_delay * 2)
            else:
                self.retry_delay = 2
                if now - self.last_demand < 10:
                    self._status()
        except Exception as e:
            dev = {"connected": False, "helper": False, "error": str(e),
                   "reason": getattr(e, "reason", "helper_error")}
            if self.service:
                self.service.disconnect()
            self.snapshot = None
            self.meters = None
            self.next_retry = now + self.retry_delay
            self.retry_delay = min(30, self.retry_delay * 2)
        self.last_failure = {} if dev.get("connected") else {
            key: dev[key] for key in ("reason", "error") if key in dev}
        self._publish(dev, official)

    def _run(self):
        next_poll = 0
        try:
            while not self.stop_event.is_set():
                if time.monotonic() >= next_poll:
                    self._refresh()
                    next_poll = time.monotonic() + self.interval
                try:
                    future, action, deadline = self.jobs.get(timeout=0.1)
                except queue.Empty:
                    continue
                if time.monotonic() >= deadline or not future.set_running_or_notify_cancel():
                    if not future.done():
                        future.set_exception(Unavailable("Solicitud vencida en la cola"))
                    continue
                try:
                    if self.service:
                        self.service._deadline = deadline
                    future.set_result(action())
                except Exception as e:
                    future.set_exception(e if isinstance(e, (Unavailable, ValueError)) else Unavailable(str(e)))
        finally:
            if self.service:
                self.service.disconnect()
            while not self.jobs.empty():
                future, _, _ = self.jobs.get_nowait()
                if not future.done():
                    future.set_exception(Unavailable("Servicio detenido"))
