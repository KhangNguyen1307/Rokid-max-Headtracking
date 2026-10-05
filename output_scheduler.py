# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
# See LICENSE; retained third-party notices apply to adapted portions.
"""Clocked game output independent of Tk drawing, USB sampling and frame rate."""
from collections import deque
import threading
import time

RATE_CHOICES = {'44,4 Hz': 1000 / 22.5, '50 Hz': 50., '80 Hz': 80.,
                '100 Hz': 100., '140 Hz': 140., '200 Hz': 200.}


class Cadence:
    def __init__(self, frequency=100.):
        self.set_frequency(frequency)

    def set_frequency(self, frequency):
        if frequency not in RATE_CHOICES.values():
            raise ValueError('Unsupported output frequency')
        self.frequency = frequency
        self.period = 1. / frequency
        self.deadline = None

    def due(self, now):
        if self.deadline is None:
            self.deadline = now
        if now + 1e-9 < self.deadline:
            return False
        # Keep the clock's phase during normal scheduling delays. After a long
        # stall discard missed frames; never burst-send a backlog of old poses.
        if now - self.deadline >= self.period:
            self.deadline = now + self.period
        else:
            self.deadline += self.period
        return True


class TrackingOutput:
    def __init__(self, reader, backend, motion, inverse, frequency=100., *, mouse=None, mouse_motion=None):
        self.reader = reader
        self.backend = backend
        self.motion = motion
        self.mouse = mouse
        self.mouse_motion = mouse_motion
        self.mode = 'headtracking'
        self.inverse = list(inverse)
        self.cadence = Cadence(frequency)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True, name='Kariuss-game-output')
        self.enabled = False
        self.paused = False
        self.active = False
        self.pose = [0.,0.,0.]
        self.held = [0.,0.,0.]
        self.waiting_center = None
        self.session = None
        self.error = ''
        self.sent_times = deque(maxlen=500)

    def configure(self, *, frequency=None, inverse=None, smoothing=None, sensitivity=None,
                  mouse_smoothing=None, mouse_sensitivity=None, mouse_controls=None):
        with self.lock:
            if frequency is not None:
                self.cadence.set_frequency(frequency)
                self.sent_times.clear()
            if inverse is not None:
                self.inverse = list(inverse)
                self.motion.reset()
                if self.mouse_motion is not None:
                    self.mouse_motion.reset()
                    self.mouse.reset()
            if smoothing is not None:
                self.motion.smoothing = smoothing
            if sensitivity is not None:
                self.motion.sensitivity = sensitivity
            if mouse_smoothing is not None:
                self.mouse_motion.smoothing = mouse_smoothing
                self.mouse_motion.reset()
                self.mouse.reset()
            if mouse_sensitivity is not None:
                self.mouse.sensitivity = mouse_sensitivity
                self.mouse.reset()
            if mouse_controls is not None:
                self.mouse.configure(**mouse_controls)
                self.mouse_motion.reset()

    def destination(self):
        return self.mouse if self.mode == 'mouse' else self.backend if self.mode == 'headtracking' else None

    def set_mode(self, mode):
        if mode not in ('headtracking', 'mouse', None) or (mode == 'mouse' and self.mouse is None):
            raise ValueError('Unsupported tracking mode')
        with self.lock:
            was_enabled = self.enabled
            self.set_enabled(False)
            self.mode = mode
            self.pose = self.held = [0., 0., 0.]
            self.paused = False
            self.waiting_center = None
            self.motion.reset()
            if self.mouse_motion is not None:
                self.mouse_motion.reset()
                self.mouse.reset()
            if was_enabled and mode is not None:
                self.set_enabled(True)

    def set_enabled(self, enabled):
        with self.lock:
            self.enabled = False
            if enabled:
                self.error = ''
                destination = self.destination()
                if destination is None:
                    raise ValueError('Chọn chế độ trước khi kết nối game.')
                destination.start()
                self.cadence.deadline = None
                self.sent_times.clear()
                self.enabled = True
            else:
                self.backend.stop()
                if self.mouse is not None:
                    self.mouse.stop()

    def center(self, generation):
        with self.lock:
            self.waiting_center = generation
            self.pose = self.held = [0.,0.,0.]
            self.motion.reset((0.,0.,0.))
            if self.mode == 'mouse':
                self.center_mouse(generation)
                return
            # Reset is a control action; it must not wait for a low-rate slot.
            if self.enabled:
                self.write(time.perf_counter())

    def center_mouse(self, generation=None):
        with self.lock:
            self.mouse_motion.reset()
            result = self.mouse.center()
            if self.mode == 'mouse' and generation is not None:
                self.waiting_center = generation
                self.pose = self.held = [0., 0., 0.]
            return result

    def write(self, now):
        try:
            destination = self.destination()
            if destination is None:
                return False
            if self.mode == 'mouse':
                written = destination.update(self.pose, active=self.active and not self.paused
                                             and not self.mouse.clutch_held and self.waiting_center is None, now=now)
            else:
                written = destination.update(self.pose, active=self.active)
            if written:
                self.sent_times.append(now)
            return bool(written)
        except Exception as exc:
            self.error = str(exc)
            self.enabled = False
            try:
                self.set_enabled(False)
            except Exception as cleanup:
                self.error += '; ' + str(cleanup)
            return False

    def pause(self, paused):
        with self.lock:
            if paused:
                self.held = list(self.pose)
            self.paused = paused
            if self.mouse is not None:
                self.mouse.reset()
                if not paused:
                    self.mouse_motion.reset()
            return list(self.held)

    def step(self, state, now, *, force=False):
        with self.lock:
            if not force and not self.cadence.due(now):
                return False
            if state['connection_session'] != self.session:
                self.session = state['connection_session']
                self.motion.reset()
                if self.mouse_motion is not None:
                    self.mouse_motion.reset()
                    self.mouse.reset()
                self.waiting_center = None
                self.paused = False
                self.held = [0.,0.,0.]
            self.active = bool(state['ready'] and state['age_s'] is not None and state['age_s'] < .5)
            if self.waiting_center is not None and state['center_generation'] > self.waiting_center:
                self.waiting_center = None
                self.motion.reset((0.,0.,0.))
                if self.mouse_motion is not None:
                    self.mouse_motion.reset((0.,0.,0.))
                    self.mouse.reset()
            raw = [a * (-1 if inv else 1) for a,inv in zip(state['angles_deg'], self.inverse)]
            if self.mode == 'mouse':
                raw[2] = 0.  # Tilting must not change the mouse smoothing response.
                held = self.enabled and self.active and self.mouse.held_key()
                if held != self.mouse.clutch_held or held:
                    # Follow the physical head during a clutch and flush the
                    # filter on release: never replay the return-to-center move.
                    self.mouse_motion.reset(raw)
                    self.mouse.reset()
                self.mouse.clutch_held = bool(held)
            if self.paused:
                self.pose = list(self.held)
            elif self.waiting_center is not None:
                self.pose = [0.,0.,0.]
            elif self.active:
                selected_filter = self.mouse_motion if self.mode == 'mouse' else self.motion
                self.pose = selected_filter.apply(raw, now)
            else:
                self.pose = [0.,0.,0.]
                self.motion.reset()
                if self.mouse_motion is not None:
                    self.mouse_motion.reset()
            if not self.enabled:
                return False
            return self.write(now)

    def snapshot(self):
        with self.lock:
            times = self.sent_times
            measured = ((len(times)-1)/(times[-1]-times[0])
                        if len(times)>1 and times[-1]>times[0] else 0.)
            return {'game_output': self.backend.snapshot(),
                    'mouse_output': self.mouse.snapshot() if self.mouse is not None else {},
                    'output_mode': self.mode, 'output_angles_deg': list(self.pose),
                    'sending_to_game': self.enabled and self.active and self.mode is not None,
                    'paused': self.paused, 'error': self.error,
                    'target_hz': self.cadence.frequency, 'measured_hz': round(measured,1)}

    def run(self):
        while not self.stop_event.is_set():
            try:
                # Python 3.12 monotonic() on Windows can advance in ~15.6 ms
                # steps; perf_counter() is the high-resolution clock here.
                self.step(self.reader.snapshot(), time.perf_counter())
            except Exception as exc:
                with self.lock:
                    self.error = str(exc)
                    self.enabled = False
                    try:
                        self.set_enabled(False)
                    except Exception as cleanup:
                        self.error += '; ' + str(cleanup)
            with self.lock:
                now = time.perf_counter()
                delay = (self.cadence.deadline or now) - now
            # Python 3.12 uses the Windows high-resolution sleep timer. Keeping
            # each sleep short also makes shutdown/configuration responsive.
            time.sleep(min(.004, max(.0001, delay)))

    def close(self):
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=1)
        with self.lock:
            self.set_enabled(False)
