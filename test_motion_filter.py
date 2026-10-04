# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
# See LICENSE; retained third-party notices apply to adapted portions.
"""Behavior checks: jitter, reaction speed, timing, centering and angle wrap."""
import math
import statistics
import unittest
from motion_filter import MotionFilter, wrap


class MotionTests(unittest.TestCase):
    def test_still_head_noise_is_attenuated(self):
        motion = MotionFilter(sensitivity=1.)
        motion.apply((0, 0, 0), 0)
        raw, filtered = [], []
        for index in range(1, 501):
            noise = .2 * math.sin(index*.5)
            raw.append(noise)
            filtered.append(motion.apply((noise, 0, 0), index*.01)[0])
        self.assertLess(statistics.pstdev(filtered), statistics.pstdev(raw)*.1)

    def test_small_deadzone_does_not_wander(self):
        motion = MotionFilter(sensitivity=1.)
        motion.apply((0, 0, 0), 0)
        for index in range(1, 201):
            self.assertEqual(motion.apply((.02 * (-1)**index, .01, -.02), index*.01), [0.,0.,0.])

    def test_large_turn_catches_up_and_never_overshoots(self):
        motion = MotionFilter(sensitivity=1.)
        motion.apply((0, 0, 0), 0)
        output = [motion.apply((90.,0.,0.), index*.01)[0] for index in range(1,101)]
        self.assertGreater(output[29], 81.)  # At least 90% of a large turn within 300 ms.
        self.assertGreater(output[49], 87.)
        self.assertTrue(all(0 <= value <= 90 for value in output))
        self.assertTrue(all(a <= b for a,b in zip(output,output[1:])))

    def test_update_rate_is_not_a_sensitivity_change(self):
        results = []
        for rate in (100, 200):
            motion = MotionFilter(sensitivity=1.)
            motion.apply((0,0,0),0)
            for index in range(1, int(rate*.5)+1):
                out = motion.apply((90.,0.,0.), index/rate)
            results.append(out[0])
        self.assertLess(abs(results[0]-results[1]), 1.)

    def test_reset_clears_old_pose_without_slow_return(self):
        motion = MotionFilter()
        motion.apply((50.,20.,-10.),0)
        motion.reset((0.,0.,0.))
        self.assertEqual(motion.apply((0.,0.,0.),1.), [0.,0.,0.])
        self.assertEqual(motion.apply((0.,0.,0.),1.01), [0.,0.,0.])

    def test_shortest_rotation_across_180_and_stall_bound(self):
        motion = MotionFilter(sensitivity=1.)
        motion.apply((179.,0.,0.),0)
        result = motion.apply((-179.,0.,0.),.01)[0]
        self.assertLess(abs(wrap(result-179)), 2.)
        self.assertGreater(abs(result), 170.)
        motion.reset((0,0,0))
        motion.apply((0,0,0),1)
        result = motion.apply((90,0,0),5)[0]
        self.assertLessEqual(result, 15.)  # A delayed UI tick cannot cause a large jump.

    def test_sensitivity_is_separate_from_smoothing_and_sign(self):
        motion = MotionFilter(smoothing=0., sensitivity=.8)
        output = motion.apply((30.,-20.,10.),0)
        for actual,expected in zip(output,(24.,-16.,8.)):
            self.assertAlmostEqual(actual,expected)
        motion.sensitivity = 1.
        self.assertEqual(motion.apply((30.,-20.,10.),.01), [30.,-20.,10.])


if __name__ == '__main__':
    unittest.main()
