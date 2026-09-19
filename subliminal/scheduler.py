from __future__ import annotations

import random
from collections.abc import Callable
from enum import Enum

from .model import AppConfig, Scene


class SchedulerState(str, Enum):
    STOPPED = "stopped"
    WAITING = "waiting"
    VISIBLE = "visible"
    PAUSED = "paused"


class Scheduler:
    """GLib-compatible scheduler with injectable timer functions for unit tests."""

    def __init__(
        self,
        get_config: Callable[[], AppConfig],
        show_scene: Callable[[Scene], None],
        clear_scene: Callable[[], None],
        timer_add: Callable[[int, Callable[[], bool]], int],
        source_remove: Callable[[int], None],
        on_state_changed: Callable[[SchedulerState], None] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._get_config = get_config
        self._show_scene = show_scene
        self._clear_scene = clear_scene
        self._timer_add = timer_add
        self._source_remove = source_remove
        self._on_state_changed = on_state_changed or (lambda _state: None)
        self._rng = rng or random.Random()
        self._state = SchedulerState.STOPPED
        self._timer_id: int | None = None
        self._sequence_index = 0
        self._last_scene_id: str | None = None

    @property
    def state(self) -> SchedulerState:
        return self._state

    @property
    def running(self) -> bool:
        return self._state in {SchedulerState.WAITING, SchedulerState.VISIBLE}

    def start(self, immediate: bool = False) -> None:
        self._cancel_timer()
        self._clear_scene()
        self._set_state(SchedulerState.WAITING)
        if immediate:
            self._begin_flash()
        else:
            self._schedule_wait()

    def pause(self) -> None:
        if self._state in {SchedulerState.STOPPED, SchedulerState.PAUSED}:
            return
        self._cancel_timer()
        self._clear_scene()
        self._set_state(SchedulerState.PAUSED)

    def stop(self) -> None:
        self._cancel_timer()
        self._clear_scene()
        self._sequence_index = 0
        self._last_scene_id = None
        self._set_state(SchedulerState.STOPPED)

    def reload_config(self) -> None:
        if self.running:
            self.start(immediate=False)

    def test_flash(self, scene: Scene | None = None) -> None:
        if self.running:
            return
        self._cancel_timer()
        chosen = scene or self._choose_scene()
        if chosen is None:
            return
        self._show_scene(chosen)
        self._set_state(SchedulerState.VISIBLE)
        duration = max(1, self._get_config().schedule.duration_ms)
        self._timer_id = self._timer_add(duration, self._finish_test_flash)

    def _finish_test_flash(self) -> bool:
        self._timer_id = None
        self._clear_scene()
        self._set_state(SchedulerState.PAUSED)
        return False

    def _schedule_wait(self) -> None:
        if self._state != SchedulerState.WAITING:
            return
        interval = max(100, self._get_config().schedule.interval_ms)
        self._timer_id = self._timer_add(interval, self._on_wait_elapsed)

    def _on_wait_elapsed(self) -> bool:
        self._timer_id = None
        self._begin_flash()
        return False

    def _begin_flash(self) -> None:
        if self._state not in {SchedulerState.WAITING, SchedulerState.VISIBLE}:
            return
        scene = self._choose_scene()
        if scene is None:
            self._set_state(SchedulerState.WAITING)
            self._schedule_wait()
            return
        self._show_scene(scene)
        self._set_state(SchedulerState.VISIBLE)
        duration = max(1, self._get_config().schedule.duration_ms)
        self._timer_id = self._timer_add(duration, self._on_flash_elapsed)

    def _on_flash_elapsed(self) -> bool:
        self._timer_id = None
        self._clear_scene()
        self._set_state(SchedulerState.WAITING)
        self._schedule_wait()
        return False

    def _choose_scene(self) -> Scene | None:
        config = self._get_config()
        scenes = config.enabled_scenes()
        if not scenes:
            return None
        if config.schedule.selection == "sequential":
            scene = scenes[self._sequence_index % len(scenes)]
            self._sequence_index = (self._sequence_index + 1) % len(scenes)
        elif len(scenes) == 1:
            scene = scenes[0]
        else:
            candidates = [item for item in scenes if item.id != self._last_scene_id]
            scene = self._rng.choice(candidates or scenes)
        self._last_scene_id = scene.id
        return scene

    def _cancel_timer(self) -> None:
        if self._timer_id is not None:
            try:
                self._source_remove(self._timer_id)
            finally:
                self._timer_id = None

    def _set_state(self, state: SchedulerState) -> None:
        if state == self._state:
            return
        self._state = state
        self._on_state_changed(state)
