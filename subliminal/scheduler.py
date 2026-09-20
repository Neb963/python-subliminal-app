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
    """Schedules breaks; the overlay owns frame-synchronized flash lifetime."""

    def __init__(
        self,
        get_config: Callable[[], AppConfig],
        present_scene: Callable[[Scene, int, Callable[[], None]], None],
        cancel_presentation: Callable[[], None],
        timer_add: Callable[[int, Callable[[], bool]], int],
        source_remove: Callable[[int], None],
        on_state_changed: Callable[[SchedulerState], None] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._get_config = get_config
        self._present_scene = present_scene
        self._cancel_presentation = cancel_presentation
        self._timer_add = timer_add
        self._source_remove = source_remove
        self._on_state_changed = on_state_changed or (lambda _state: None)
        self._rng = rng or random.Random()
        self._state = SchedulerState.STOPPED
        self._timer_id: int | None = None
        self._sequence_index = 0
        self._last_scene_id: str | None = None
        self._presentation_generation = 0

    @property
    def state(self) -> SchedulerState:
        return self._state

    @property
    def running(self) -> bool:
        return self._state in {SchedulerState.WAITING, SchedulerState.VISIBLE}

    def start(self, immediate: bool = False) -> None:
        self._cancel_timer()
        self._cancel_active_presentation()
        self._set_state(SchedulerState.WAITING)
        if immediate:
            self._begin_flash()
        else:
            self._schedule_break()

    def pause(self) -> None:
        if self._state in {SchedulerState.STOPPED, SchedulerState.PAUSED}:
            return
        self._cancel_timer()
        self._cancel_active_presentation()
        self._set_state(SchedulerState.PAUSED)

    def stop(self) -> None:
        self._cancel_timer()
        self._cancel_active_presentation()
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
        self._cancel_active_presentation()
        chosen = scene or self._choose_scene()
        if chosen is None:
            return
        self._set_state(SchedulerState.VISIBLE)
        generation = self._presentation_generation
        frames = max(1, self._get_config().schedule.visible_frames)
        self._present_scene(
            chosen,
            frames,
            lambda: self._finish_test_flash(generation),
        )

    def _finish_test_flash(self, generation: int) -> None:
        if generation != self._presentation_generation:
            return
        if self._state == SchedulerState.VISIBLE:
            self._set_state(SchedulerState.PAUSED)

    def _schedule_break(self) -> None:
        if self._state != SchedulerState.WAITING:
            return
        delay = max(100, self._get_config().schedule.break_ms)
        self._timer_id = self._timer_add(delay, self._on_break_elapsed)

    def _on_break_elapsed(self) -> bool:
        self._timer_id = None
        self._begin_flash()
        return False

    def _begin_flash(self) -> None:
        if self._state not in {SchedulerState.WAITING, SchedulerState.VISIBLE}:
            return
        scene = self._choose_scene()
        if scene is None:
            self._set_state(SchedulerState.WAITING)
            self._schedule_break()
            return
        self._set_state(SchedulerState.VISIBLE)
        generation = self._presentation_generation
        frames = max(1, self._get_config().schedule.visible_frames)
        self._present_scene(
            scene,
            frames,
            lambda: self._on_flash_finished(generation),
        )

    def _on_flash_finished(self, generation: int) -> None:
        if generation != self._presentation_generation:
            return
        if self._state != SchedulerState.VISIBLE:
            return
        self._set_state(SchedulerState.WAITING)
        self._schedule_break()

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

    def _cancel_active_presentation(self) -> None:
        self._presentation_generation += 1
        self._cancel_presentation()

    def _set_state(self, state: SchedulerState) -> None:
        if state == self._state:
            return
        self._state = state
        self._on_state_changed(state)
