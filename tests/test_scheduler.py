import random

from subliminal.model import Scene, TextLayer, default_config
from subliminal.scheduler import Scheduler, SchedulerState


class FakeTimers:
    def __init__(self) -> None:
        self.next_id = 1
        self.callbacks: dict[int, object] = {}

    def add(self, _ms, callback):
        ident = self.next_id
        self.next_id += 1
        self.callbacks[ident] = callback
        return ident

    def remove(self, ident):
        self.callbacks.pop(ident, None)

    def fire_next(self):
        ident = sorted(self.callbacks)[0]
        callback = self.callbacks.pop(ident)
        return callback()


def test_start_flash_hide_cycle() -> None:
    cfg = default_config()
    timers = FakeTimers()
    shown = []
    cleared = []
    scheduler = Scheduler(
        lambda: cfg,
        shown.append,
        lambda: cleared.append(True),
        timers.add,
        timers.remove,
        rng=random.Random(1),
    )
    scheduler.start()
    assert scheduler.state == SchedulerState.WAITING
    timers.fire_next()
    assert scheduler.state == SchedulerState.VISIBLE
    assert shown
    timers.fire_next()
    assert scheduler.state == SchedulerState.WAITING


def test_random_avoids_immediate_repeat() -> None:
    cfg = default_config()
    cfg.scenes = [Scene(name="A", layers=[TextLayer()]), Scene(name="B", layers=[TextLayer()])]
    timers = FakeTimers()
    shown = []
    scheduler = Scheduler(lambda: cfg, shown.append, lambda: None, timers.add, timers.remove, rng=random.Random(0))
    scheduler.start(immediate=True)
    first = shown[-1].id
    timers.fire_next()
    timers.fire_next()
    assert shown[-1].id != first
