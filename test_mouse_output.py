# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
"""Mouse motion correctness without synthesizing input on the user's desktop."""
import ctypes
import unittest

from motion_filter import MotionFilter
from mouse_output import Input, MouseOutput
from output_scheduler import TrackingOutput
from test_output_scheduler import FakeGame, FakeReader


class CaptureMouse:
    def __init__(self):
        self.moves = []
        self.centers = 0
        self.foreground = True
        self.fail = False

    def available(self):
        return self.foreground

    def move(self, dx, dy):
        if self.fail:
            raise OSError('Mouse input blocked')
        self.moves.append((dx, dy))

    def center(self):
        self.centers += 1
        return (960, 540)


class MouseTests(unittest.TestCase):
    def setUp(self):
        self.sink = CaptureMouse()
        self.mouse = MouseOutput(self.sink, sensitivity=1., units_per_degree=10.)
        self.mouse.start()

    def test_windows_input_abi(self):
        self.assertEqual(ctypes.sizeof(Input), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
        self.assertEqual(Input.data.offset, 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 4)

    def test_relative_movement_pitch_direction_roll_ignored_and_stationary(self):
        self.assertFalse(self.mouse.update((45., 0., 0.)))
        self.mouse.update((47., 3., 90.))
        self.assertEqual(self.sink.moves, [(20, -30)])
        self.mouse.update((47., 3., -90.))
        self.assertEqual(len(self.sink.moves), 1)
        self.mouse.update((45., 0., 0.))
        self.assertEqual(self.sink.moves[-1], (-20, 30))

    def test_angle_wrap_does_not_cause_full_turn_jump(self):
        self.mouse.update((179., 0., 0.))
        self.mouse.update((-179., 0., 0.))
        self.assertEqual(self.sink.moves[-1], (20, 0))

    def test_fractional_motion_accumulates_and_sensitivity_scales(self):
        self.mouse.sensitivity = .5
        self.mouse.update((0., 0., 0.))
        for i in range(1, 21):
            self.mouse.update((i * .05, 0., 0.))
        self.assertLessEqual(abs(sum(x for x, _ in self.sink.moves) - 5), 1)

    def test_reset_inactivity_focus_and_reenable_discard_old_motion(self):
        self.mouse.update((0., 0., 0.))
        self.mouse.update((1., 0., 0.))
        count = len(self.sink.moves)
        self.assertEqual(self.mouse.center(), (960, 540))
        self.assertEqual(self.sink.centers, 1)
        self.mouse.update((90., 0., 0.))
        self.assertEqual(len(self.sink.moves), count)
        self.mouse.update((120., 0., 0.), active=False)
        self.mouse.update((150., 0., 0.))
        self.assertEqual(len(self.sink.moves), count)
        self.sink.foreground = False
        self.mouse.update((160., 0., 0.))
        self.sink.foreground = True
        self.mouse.update((170., 0., 0.))
        self.assertEqual(len(self.sink.moves), count)
        self.mouse.stop()
        self.mouse.update((175., 0., 0.))
        self.mouse.start()
        self.mouse.update((179., 0., 0.))
        self.assertEqual(len(self.sink.moves), count)


class ModeTests(unittest.TestCase):
    def setUp(self):
        self.reader, self.game, self.sink = FakeReader(), FakeGame(), CaptureMouse()
        self.mouse = MouseOutput(self.sink, sensitivity=1., units_per_degree=10.)
        self.output = TrackingOutput(self.reader, self.game, MotionFilter(0, 1), [True, False, False],
                                     mouse=self.mouse, mouse_motion=MotionFilter(0, 1))

    def tearDown(self):
        self.output.close()

    def test_default_rocker_and_live_connection_is_exclusive(self):
        self.assertEqual(self.output.mode, 'headtracking')
        self.output.set_enabled(True)
        self.output.step(self.reader.snapshot(), 0.)
        count = len(self.game.packets)
        self.output.set_mode('mouse')
        self.assertTrue(self.mouse.enabled)
        self.assertFalse(self.game.enabled)
        self.output.step(self.reader.snapshot(), .01)
        self.reader.state['angles_deg'] = [10., 0., 90.]
        self.output.step(self.reader.snapshot(), .02)
        self.assertEqual(self.sink.moves[-1], (20, -30))
        self.assertEqual(len(self.game.packets), count)
        mouse_count = len(self.sink.moves)
        self.output.set_mode('headtracking')
        self.assertTrue(self.game.enabled)
        self.assertFalse(self.mouse.enabled)
        self.output.step(self.reader.snapshot(), .03)
        self.assertEqual(len(self.sink.moves), mouse_count)
        self.output.set_enabled(False)
        self.assertFalse(self.game.enabled or self.mouse.enabled)

    def test_mouse_pause_reset_resume_and_usb_loss_do_not_jump(self):
        self.output.set_mode('mouse')
        self.output.set_enabled(True)
        self.output.step(self.reader.snapshot(), 0.)
        self.output.pause(True)
        self.reader.state['angles_deg'] = [90., 45., 0.]
        self.output.step(self.reader.snapshot(), .01)
        self.assertEqual(self.sink.moves, [])
        self.output.center(1)
        self.assertEqual(self.sink.centers, 1)
        self.output.pause(False)
        self.reader.state.update(center_generation=2, angles_deg=[0., 0., 0.])
        self.output.step(self.reader.snapshot(), .02)
        self.assertEqual(self.sink.moves, [])
        self.reader.state['angles_deg'] = [-1., 0., 0.]
        self.output.step(self.reader.snapshot(), .03)
        self.assertEqual(self.sink.moves[-1], (10, 0))
        count = len(self.sink.moves)
        self.reader.state.update(age_s=.6, angles_deg=[100., 45., 0.])
        self.output.step(self.reader.snapshot(), .04)
        self.reader.state.update(connection_session=2, age_s=0.)
        self.output.step(self.reader.snapshot(), .05)
        self.assertEqual(len(self.sink.moves), count)

    def test_mouse_settings_do_not_modify_head_filter_and_failures_stop_output(self):
        old = self.output.motion.smoothing, self.output.motion.sensitivity
        self.output.configure(mouse_smoothing=2., mouse_sensitivity=1.5)
        self.assertEqual((self.output.motion.smoothing, self.output.motion.sensitivity), old)
        self.assertEqual(self.output.mouse_motion.smoothing, 2.)
        self.output.configure(mouse_smoothing=0.)
        self.output.set_mode('mouse')
        self.output.set_enabled(True)
        self.output.step(self.reader.snapshot(), 0.)
        self.sink.fail = True
        self.reader.state['angles_deg'] = [20., 0., 0.]
        self.output.step(self.reader.snapshot(), .01)
        self.assertFalse(self.output.enabled or self.game.enabled or self.mouse.enabled)
        self.assertIn('Mouse input blocked', self.output.snapshot()['error'])


if __name__ == '__main__':
    unittest.main()
