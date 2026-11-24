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


class FakePresenter:
    def __init__(self) -> None:
        self.calls = []
        self.done = None
        self.cancelled = 0

    def present(self, scene, frames, done):
        self.calls.append((scene, frames))
        self.done = done

    def cancel(self):
        self.cancelled += 1
        self.done = None

    def finish(self):
        done = self.done
        self.done = None
        assert done is not None
        done()


def test_start_flash_frame_completion_break_cycle() -> None:
    cfg = default_config()
    cfg.schedule.visible_frames = 3
    timers = FakeTimers()
    presenter = FakePresenter()
    scheduler = Scheduler(
        lambda: cfg,
        presenter.present,
        presenter.cancel,
        timers.add,
        timers.remove,
        rng=random.Random(1),
    )
    scheduler.start()
    assert scheduler.state == SchedulerState.WAITING
    timers.fire_next()
    assert scheduler.state == SchedulerState.VISIBLE
    assert presenter.calls[-1][1] == 3
    assert not timers.callbacks
    presenter.finish()
    assert scheduler.state == SchedulerState.WAITING
    assert timers.callbacks


def test_random_avoids_immediate_repeat() -> None:
    cfg = default_config()
    cfg.scenes = [Scene(name="A", layers=[TextLayer()]), Scene(name="B", layers=[TextLayer()])]
    timers = FakeTimers()
    presenter = FakePresenter()
    scheduler = Scheduler(
        lambda: cfg,
        presenter.present,
        presenter.cancel,
        timers.add,
        timers.remove,
        rng=random.Random(0),
    )
    scheduler.start(immediate=True)
    first = presenter.calls[-1][0].id
    presenter.finish()
    timers.fire_next()
    assert presenter.calls[-1][0].id != first


def test_pause_cancels_active_frame_presentation() -> None:
    cfg = default_config()
    timers = FakeTimers()
    presenter = FakePresenter()
    scheduler = Scheduler(
        lambda: cfg,
        presenter.present,
        presenter.cancel,
        timers.add,
        timers.remove,
    )
    scheduler.start(immediate=True)
    assert scheduler.state == SchedulerState.VISIBLE
    scheduler.pause()
    assert scheduler.state == SchedulerState.PAUSED
    assert presenter.done is None


def test_test_flash_does_not_count_as_running_and_restores_stopped() -> None:
    cfg = default_config()
    timers = FakeTimers()
    presenter = FakePresenter()
    scheduler = Scheduler(
        lambda: cfg,
        presenter.present,
        presenter.cancel,
        timers.add,
        timers.remove,
    )
    assert scheduler.state == SchedulerState.STOPPED
    scheduler.test_flash()
    assert scheduler.state == SchedulerState.VISIBLE
    assert scheduler.testing is True
    assert scheduler.running is False

    # Timing/config reload during a test flash must not start continuous scheduling.
    scheduler.reload_config()
    assert scheduler.state == SchedulerState.VISIBLE
    assert scheduler.running is False
    assert not timers.callbacks

    presenter.finish()
    assert scheduler.testing is False
    assert scheduler.state == SchedulerState.STOPPED


def test_test_flash_restores_paused_when_triggered_from_paused() -> None:
    cfg = default_config()
    timers = FakeTimers()
    presenter = FakePresenter()
    scheduler = Scheduler(
        lambda: cfg,
        presenter.present,
        presenter.cancel,
        timers.add,
        timers.remove,
    )
    scheduler.start()
    scheduler.pause()
    assert scheduler.state == SchedulerState.PAUSED

    scheduler.test_flash()
    assert scheduler.running is False
    presenter.finish()
    assert scheduler.state == SchedulerState.PAUSED
