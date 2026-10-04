# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
# See LICENSE; retained third-party notices apply to adapted portions.
"""Accela rotation filter adapted for Kariuss, without Qt or another application.

Algorithm/defaults: opentrack/filter-accela/{ftnoir_filter_accela.cpp,
accela-settings.hpp}. Catmull-Rom response: opentrack/spline/spline.cpp.
Copyright (c) 2012-2019 Stanislaw Halik.
Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.
THE SOFTWARE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND.

Kariuss uses the three rotation axes, keeps a bounded timestep and prevents
overshoot after a GUI stall. Sensitivity is a separate scale after filtering.
"""
import bisect
import math

SMOOTHING_CHOICES = {'Tắt': 0., 'Mượt nhẹ': .75, 'Mượt vừa': 1.5, 'Mượt nhiều': 2.0}
SMOOTHING_ALIASES = {'Phản hồi nhanh': 'Mượt nhẹ', 'Như OpenTrack': 'Mượt vừa',
                     'Mượt hơn': 'Mượt nhiều'}
SENSITIVITY_CHOICES = ('40%', '60%', '80%', '100%', '120%', '150%')
GAINS = ((0., 0.), (.5, .4), (1., 1.5), (1.5, 8.), (2.5, 35.),
         (5., 100.), (8., 200.), (9., 300.))


def wrap(angle):
    return (angle + 180.) % 360. - 180.


def catmull(a, b, c, d, t):
    return .5 * (2*b + (-a+c)*t + (2*a-5*b+4*c-d)*t*t + (-a+3*b-3*c+d)*t*t*t)


def response(distance):
    """Evaluate the Accela gain curve using its own x coordinates."""
    if distance <= 0:
        return 0.
    if distance >= GAINS[-1][0]:
        return GAINS[-1][1]
    index = bisect.bisect_right([p[0] for p in GAINS], distance) - 1
    a = GAINS[index-1] if index else (0., 0.)
    b, c = GAINS[index:index+2]
    d = GAINS[index+2] if index+2 < len(GAINS) else c
    low, high = 0., 1.
    for _ in range(32):
        t = (low+high) / 2
        if catmull(a[0], b[0], c[0], d[0], t) < distance:
            low = t
        else:
            high = t
    return min(300., max(0., catmull(a[1], b[1], c[1], d[1], (low+high)/2)))


class MotionFilter:
    def __init__(self, smoothing=1.5, sensitivity=.8, deadzone=.03):
        self.smoothing = smoothing
        self.sensitivity = sensitivity
        self.deadzone = deadzone
        self.last = None
        self.last_time = None

    def reset(self, pose=None):
        self.last = None if pose is None else list(pose)
        self.last_time = None

    def scaled(self, pose):
        return [max(-179.99, min(179.99, a * self.sensitivity)) for a in pose]

    def apply(self, pose, now):
        if len(pose) != 3 or not all(math.isfinite(a) for a in pose):
            raise ValueError('Invalid orientation')
        pose = [wrap(a) for a in pose]
        if self.last is None or self.smoothing <= 0:
            self.last = list(pose)
            self.last_time = now
            return self.scaled(self.last)
        dt = min(.05, max(0., now - self.last_time)) if self.last_time is not None else 0.
        self.last_time = now
        deltas = []
        for target, last in zip(pose, self.last):
            delta = wrap(target - last)
            delta = math.copysign(max(0., abs(delta)-self.deadzone), delta)
            deltas.append(delta / self.smoothing)
        distance = math.sqrt(sum(d*d for d in deltas))
        speed = response(distance)
        total = sum(abs(d) for d in deltas)
        if total > 1e-6:
            for index, delta in enumerate(deltas):
                step = speed * abs(delta) / total * dt
                step = min(step, abs(delta) * self.smoothing)
                self.last[index] = wrap(self.last[index] + math.copysign(step, delta))
        return self.scaled(self.last)
