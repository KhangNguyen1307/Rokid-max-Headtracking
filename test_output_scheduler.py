# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
# See LICENSE; retained third-party notices apply to adapted portions.
"""Send cadence, thread independence, head controls and USB freshness behavior."""
import math
import time
import unittest
from motion_filter import MotionFilter
from output_scheduler import Cadence, RATE_CHOICES, TrackingOutput


class FakeReader:
    def __init__(self):
        self.state = dict(connection_session=1, center_generation=1, ready=True,
                          age_s=0., angles_deg=[12.,-3.,2.])

    def snapshot(self):
        return dict(self.state)


class FakeGame:
    def __init__(self):
        self.enabled = False
        self.packets = []
        self.fail = False

    def start(self):
        self.enabled = True

    def stop(self):
        self.enabled = False

    def update(self, pose, active=True):
        if self.fail:
            raise OSError('Simulated output failure')
        if self.enabled and active:
            self.packets.append(tuple(pose))
            return True
        return False

    def snapshot(self):
        return dict(enabled=self.enabled, registered_game_id=0, registered_game_name='',
                    frames_written=len(self.packets))


class SchedulingTests(unittest.TestCase):
    def test_all_levels_send_correct_counts(self):
        for name, frequency in RATE_CHOICES.items():
            with self.subTest(level=name):
                cadence = Cadence(frequency)
                count = sum(cadence.due(i/10000) for i in range(10000))
                self.assertLessEqual(abs(count-frequency), 1.)

    def test_delayed_loop_preserves_phase_and_discards_stale_backlog(self):
        cadence = Cadence(100.)
        self.assertTrue(cadence.due(0))
        self.assertTrue(cadence.due(.014))
        self.assertTrue(cadence.due(.020))  # Time spent sending is not added to every period.
        self.assertTrue(cadence.due(2.))
        self.assertFalse(cadence.due(2.))
        self.assertFalse(cadence.due(2.001))
        self.assertTrue(cadence.due(2.010))
        cadence.set_frequency(50.)
        self.assertTrue(cadence.due(2.015))
        self.assertFalse(cadence.due(2.025))
        self.assertTrue(cadence.due(2.035))

    def test_output_runs_above_100_without_gui_ticks_and_changes_live(self):
        reader, backend = FakeReader(), FakeGame()
        output = TrackingOutput(reader, backend, MotionFilter(smoothing=0, sensitivity=1),
                                [False]*3, 200.)
        output.set_enabled(True)
        output.thread.start()
        try:
            # The caller makes no GUI or output updates during these waits.
            start = len(backend.packets)
            time.sleep(.3)
            fast = len(backend.packets)-start
            self.assertGreater(fast, 40)
            self.assertLessEqual(fast, 64)
            output.configure(frequency=50.)
            start = len(backend.packets)
            time.sleep(.3)
            slow = len(backend.packets)-start
            self.assertGreater(slow, 10)
            self.assertLessEqual(slow, 17)
            self.assertGreater(fast, slow*2)
            self.assertEqual(output.snapshot()['target_hz'], 50.)
        finally:
            output.close()
        count = len(backend.packets)
        time.sleep(.02)
        self.assertEqual(len(backend.packets),count)
        self.assertFalse(backend.enabled)


class ControlsTests(unittest.TestCase):
    def setUp(self):
        self.reader, self.backend = FakeReader(), FakeGame()
        self.output = TrackingOutput(self.reader, self.backend,
                                     MotionFilter(smoothing=0, sensitivity=1), [True,False,False], 50.)
        self.output.set_enabled(True)
        self.output.step(self.reader.snapshot(), 0.)

    def tearDown(self):
        self.output.close()

    def test_pause_and_immediate_reset_wait_for_sensor_reference(self):
        self.assertEqual(self.backend.packets[-1],(-12.,-3.,2.))
        self.output.pause(True)
        self.reader.state['angles_deg'] = [80.,20.,10.]
        self.output.step(self.reader.snapshot(), .02)
        self.assertEqual(self.backend.packets[-1],(-12.,-3.,2.))
        count = len(self.backend.packets)
        self.output.center(1)
        self.assertEqual(len(self.backend.packets),count+1)
        self.assertEqual(self.backend.packets[-1],(0.,0.,0.))
        self.output.pause(False)
        self.output.step(self.reader.snapshot(), .04)
        self.assertEqual(self.backend.packets[-1],(0.,0.,0.))
        self.reader.state.update(center_generation=2, angles_deg=[0.,0.,0.])
        self.output.step(self.reader.snapshot(), .06)
        self.assertEqual(self.backend.packets[-1],(0.,0.,0.))
        self.reader.state['angles_deg'] = [15.,0.,0.]
        self.output.step(self.reader.snapshot(), .08)
        self.assertEqual(self.backend.packets[-1],(-15.,0.,0.))

    def test_stale_and_reconnected_glasses_do_not_send_old_pose(self):
        self.output.pause(True)
        count = len(self.backend.packets)
        self.reader.state['age_s'] = .6
        self.output.step(self.reader.snapshot(), .02)
        self.assertEqual(len(self.backend.packets),count)
        self.assertFalse(self.output.snapshot()['sending_to_game'])
        self.reader.state.update(connection_session=2, ready=False, age_s=0., angles_deg=[0.,0.,0.])
        self.output.step(self.reader.snapshot(), .04)
        self.assertFalse(self.output.snapshot()['paused'])
        self.reader.state['ready'] = True
        self.output.step(self.reader.snapshot(), .06)
        self.assertEqual(self.backend.packets[-1],(0.,0.,0.))
        self.output.set_enabled(False)
        count = len(self.backend.packets)
        self.output.step(self.reader.snapshot(), .08)
        self.assertEqual(len(self.backend.packets),count)

    def test_output_failure_is_reported_and_writer_stops(self):
        self.backend.fail = True
        self.output.center(1)
        self.assertIn('Simulated output failure', self.output.snapshot()['error'])
        self.assertFalse(self.output.snapshot()['sending_to_game'])
        self.assertFalse(self.backend.enabled)

    def test_filter_gain_and_inverse_change_are_applied_in_writer(self):
        self.output.configure(inverse=[False]*3, sensitivity=.8, smoothing=1.5)
        self.output.step(self.reader.snapshot(), .02)
        for actual,expected in zip(self.backend.packets[-1],(9.6,-2.4,1.6)):
            self.assertAlmostEqual(actual,expected)


if __name__ == '__main__':
    unittest.main()
