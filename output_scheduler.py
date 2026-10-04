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
    def __init__(self, reader, backend, motion, inverse, frequency=100.):
        self.reader = reader
        self.backend = backend
        self.motion = motion
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

    def configure(self, *, frequency=None, inverse=None, smoothing=None, sensitivity=None):
        with self.lock:
            if frequency is not None:
                self.cadence.set_frequency(frequency)
                self.sent_times.clear()
            if inverse is not None:
                self.inverse = list(inverse)
                self.motion.reset()
            if smoothing is not None:
                self.motion.smoothing = smoothing
            if sensitivity is not None:
                self.motion.sensitivity = sensitivity

    def set_enabled(self, enabled):
        with self.lock:
            self.enabled = False
            if enabled:
                self.error = ''
                self.backend.start()
                self.cadence.deadline = None
                self.sent_times.clear()
                self.enabled = True
            else:
                self.backend.stop()

    def center(self, generation):
        with self.lock:
            self.waiting_center = generation
            self.pose = self.held = [0.,0.,0.]
            self.motion.reset((0.,0.,0.))
            # Reset is a control action; it must not wait for a low-rate slot.
            if self.enabled:
                self.write(time.perf_counter())

    def write(self, now):
        try:
            written = self.backend.update(self.pose, active=self.active)
            if written:
                self.sent_times.append(now)
            return bool(written)
        except Exception as exc:
            self.error = str(exc)
            self.enabled = False
            try:
                self.backend.stop()
            except Exception as cleanup:
                self.error += '; ' + str(cleanup)
            return False

    def pause(self, paused):
        with self.lock:
            if paused:
                self.held = list(self.pose)
            self.paused = paused
            return list(self.held)

    def step(self, state, now, *, force=False):
        with self.lock:
            if not force and not self.cadence.due(now):
                return False
            if state['connection_session'] != self.session:
                self.session = state['connection_session']
                self.motion.reset()
                self.waiting_center = None
                self.paused = False
                self.held = [0.,0.,0.]
            self.active = bool(state['ready'] and state['age_s'] is not None and state['age_s'] < .5)
            if self.waiting_center is not None and state['center_generation'] > self.waiting_center:
                self.waiting_center = None
                self.motion.reset((0.,0.,0.))
            raw = [a * (-1 if inv else 1) for a,inv in zip(state['angles_deg'], self.inverse)]
            if self.paused:
                self.pose = list(self.held)
            elif self.waiting_center is not None:
                self.pose = [0.,0.,0.]
            elif self.active:
                self.pose = self.motion.apply(raw, now)
            else:
                self.pose = [0.,0.,0.]
                self.motion.reset()
            if not self.enabled:
                return False
            return self.write(now)

    def snapshot(self):
        with self.lock:
            times = self.sent_times
            measured = ((len(times)-1)/(times[-1]-times[0])
                        if len(times)>1 and times[-1]>times[0] else 0.)
            return {'game_output': self.backend.snapshot(), 'output_angles_deg': list(self.pose),
                    'sending_to_game': self.enabled and self.active,
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
                        self.backend.stop()
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
            self.enabled = False
            self.backend.stop()
