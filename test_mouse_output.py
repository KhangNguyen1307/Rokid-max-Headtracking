# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
"""Mouse motion correctness without synthesizing input on the user's desktop."""
import ctypes
import unittest

from motion_filter import MotionFilter
from mouse_output import Input, MouseOutput, DEADZONE_CHOICES, TURN_ANGLE_CHOICES
from output_scheduler import TrackingOutput
from test_output_scheduler import FakeGame, FakeReader


class CaptureMouse:
    def __init__(self):
        self.moves = []
        self.centers = 0
        self.foreground = True
        self.fail = False
        self.held = False

    def available(self):
        return self.foreground

    def move(self, dx, dy):
        if self.fail:
            raise OSError('Mouse input blocked')
        self.moves.append((dx, dy))

    def center(self):
        self.centers += 1
        return (960, 540)

    def key_down(self, key):
        return self.held


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

    def test_reset_waits_for_new_glasses_reference_without_mouse_jump(self):
        for style in ('relative', 'continuous'):
            with self.subTest(style=style):
                self.output.set_mode('mouse')
                self.mouse.style = style
                self.output.set_enabled(True)
                self.reader.state.update(center_generation=1, angles_deg=[0., 0., 0.])
                self.output.step(self.reader.snapshot(), 0., force=True)
                self.reader.state['angles_deg'] = [-30., 10., 5.]
                self.output.step(self.reader.snapshot(), .01, force=True)
                count = len(self.sink.moves)
                centers = self.sink.centers
                self.output.center_mouse(1)
                self.assertEqual(self.sink.centers, centers + 1)
                # Old samples must not establish a fresh baseline before the
                # glasses have actually acknowledged their new reference.
                for now in (.02, .03):
                    self.output.step(self.reader.snapshot(), now, force=True)
                    self.assertEqual(self.output.pose, [0., 0., 0.])
                    self.assertIsNone(self.mouse.previous)
                self.reader.state.update(center_generation=2, angles_deg=[0., 0., 0.])
                self.output.step(self.reader.snapshot(), .04, force=True)
                self.output.step(self.reader.snapshot(), .05, force=True)
                self.assertEqual(len(self.sink.moves), count)
                self.assertIsNone(self.output.waiting_center)
                self.reader.state['angles_deg'] = [-1., 0., 0.]
                self.output.step(self.reader.snapshot(), .06, force=True)
                self.assertEqual(self.sink.moves[-1], (10, 0))

    def test_mouse_tab_reset_centers_cursor_without_switching_or_changing_headtracking(self):
        self.output.set_enabled(True)
        self.output.step(self.reader.snapshot(), 0.)
        pose = list(self.output.pose)
        count = len(self.game.packets)
        self.assertEqual(self.output.center_mouse(), (960, 540))
        self.assertEqual(self.sink.centers, 1)
        self.assertEqual(self.output.mode, 'headtracking')
        self.assertTrue(self.output.enabled and self.game.enabled)
        self.assertFalse(self.mouse.enabled)
        self.assertEqual(self.output.pose, pose)
        self.assertEqual(len(self.game.packets), count)

    def test_clutch_returns_head_without_moving_game_and_release_has_no_filter_tail(self):
        self.output.set_mode('mouse')
        self.output.configure(mouse_smoothing=1.5)
        self.output.set_enabled(True)
        self.reader.state['angles_deg'] = [0., 0., 0.]
        self.output.step(self.reader.snapshot(), 0.)
        self.sink.held = True
        for index, angle in enumerate((30., 15., 0.)):
            self.reader.state['angles_deg'] = [angle, 10., 0.]
            self.output.step(self.reader.snapshot(), (index + 1) * .01)
        self.assertEqual(self.sink.moves, [])
        self.assertTrue(self.output.snapshot()['mouse_output']['clutch_held'])
        self.sink.held = False
        for index in range(4, 20):
            self.output.step(self.reader.snapshot(), index * .01)
        self.assertEqual(self.sink.moves, [])
        self.assertFalse(self.output.snapshot()['mouse_output']['clutch_held'])
        self.assertEqual(self.sink.centers, 0)  # Clutch keeps its separate no-cursor-move behavior.
        self.reader.state['angles_deg'] = [-10., 10., 0.]
        self.output.step(self.reader.snapshot(), .21)
        self.assertGreater(self.sink.moves[-1][0], 0)

    def test_continuous_stops_on_clutch_and_rebases_on_release(self):
        self.output.set_mode('mouse')
        self.mouse.style = 'continuous'
        self.output.set_enabled(True)
        self.reader.state['angles_deg'] = [0., 0., 0.]
        self.output.step(self.reader.snapshot(), 0.)
        self.reader.state['angles_deg'] = [-30., 0., 0.]
        self.output.step(self.reader.snapshot(), .01)
        self.assertGreater(self.sink.moves[-1][0], 0)
        count = len(self.sink.moves)
        self.sink.held = True
        self.reader.state['angles_deg'] = [20., 0., 0.]
        self.output.step(self.reader.snapshot(), .02)
        self.sink.held = False
        self.output.step(self.reader.snapshot(), .03)
        self.output.step(self.reader.snapshot(), .04)
        self.assertEqual(len(self.sink.moves), count)


class ContinuousTests(unittest.TestCase):
    def make_mouse(self):
        sink = CaptureMouse()
        mouse = MouseOutput(sink, sensitivity=1.)
        mouse.style = 'continuous'
        mouse.deadzone = 0.  # Pure continuous turning; hybrid-zone cases below.
        mouse.start()
        mouse.update((0., 0., 0.), now=0.)
        return mouse, sink

    def test_stationary_off_center_turns_neutral_stops_and_direction_reverses(self):
        mouse, sink = self.make_mouse()
        mouse.update((30., 0., 0.), now=.01)
        mouse.update((30., 0., 0.), now=.02)
        self.assertEqual(sink.moves, [(16, 0), (16, 0)])
        mouse.update((0., 0., 0.), now=.03)
        self.assertEqual(len(sink.moves), 2)
        mouse.update((-30., 0., 0.), now=.04)
        self.assertEqual(sink.moves[-1], (-16, 0))
        mouse.center()
        mouse.update((-30., 0., 0.), now=.05)
        mouse.update((-30., 0., 0.), now=.06)
        self.assertEqual(len(sink.moves), 3)
        self.assertEqual(sink.centers, 1)

    def test_full_angle_ranges_zero_equal_reversed_and_180_degree_start(self):
        self.assertEqual(DEADZONE_CHOICES, tuple(f'{a}°' for a in range(181)))
        self.assertEqual(TURN_ANGLE_CHOICES, tuple(f'{a}°' for a in range(0, 181, 15)))
        for start, maximum in ((0, 0), (15, 15), (30, 15), (179, 180), (180, 0), (180, 180)):
            mouse, sink = self.make_mouse()
            mouse.configure(style='continuous', clutch_key=0x75, deadzone=start,
                            turn_angle=maximum, turn_speed=1600., continuous_vertical=False)
            mouse.update((0., 0., 0.), now=0.)
            mouse.update((float(start), 0., 0.), now=.01)
            if start:
                self.assertEqual(abs(sink.moves[-1][0]), start * mouse.units_per_degree)
            count = len(sink.moves)
            mouse.update((float(start), 0., 0.), now=.02)
            self.assertEqual(len(sink.moves), count)  # Inner zone moves only with the head.
            mouse.update((min(180., start + 1.), 0., 0.), now=.03)
            count = len(sink.moves)
            mouse.update((min(180., start + 1.), 0., 0.), now=.04)
            if start == 180:
                self.assertEqual(len(sink.moves), count)
            else:
                self.assertLessEqual(abs(abs(sink.moves[-1][0]) - 16), 1)
        mouse, sink = self.make_mouse()
        mouse.configure(style='continuous', clutch_key=0x75, deadzone=0, turn_angle=180,
                        turn_speed=1600., continuous_vertical=False)
        mouse.update((0., 0., 0.), now=0.)
        mouse.update((90., 0., 0.), now=.01)
        self.assertEqual(sink.moves[-1], (8, 0))

    def test_180_degree_threshold_keeps_normal_mouse_control_in_full_range(self):
        mouse, sink = self.make_mouse()
        mouse.deadzone = 180.
        mouse.turn_angle = 0.  # Lower maximum angle must not freeze the inner zone.
        for index, pose in enumerate(((90., 5., 0.), (179., 5., 0.), (-179., 5., 0.),
                                      (-90., 5., 0.), (0., 0., 0.)), 1):
            mouse.update(pose, now=index * .01)
        self.assertEqual(sink.moves, [(1800, -100), (1780, 0), (40, 0), (1780, 0), (1800, 100)])
        mouse.update((0., 0., 0.), now=.06)
        self.assertEqual(len(sink.moves), 5)

    def test_hybrid_inner_mouse_outer_continuous_and_return_counts_only_inner_motion(self):
        mouse, sink = self.make_mouse()
        mouse.deadzone, mouse.turn_angle = 30., 60.
        mouse.update((10., 0., 0.), now=.01)
        self.assertEqual(sink.moves[-1], (200, 0))
        mouse.update((10., 0., 0.), now=.02)
        self.assertEqual(len(sink.moves), 1)
        mouse.update((30., 0., 0.), now=.03)
        self.assertEqual(sink.moves[-1], (400, 0))
        mouse.update((45., 0., 0.), now=.04)
        mouse.update((45., 0., 0.), now=.05)
        self.assertEqual(sink.moves[-2:], [(8, 0), (8, 0)])
        mouse.update((20., 0., 0.), now=.06)
        self.assertEqual(sink.moves[-1], (-200, 0))  # Only 30 -> 20 is inside the zone.
        count = len(sink.moves)
        mouse.update((20., 0., 0.), now=.07)
        self.assertEqual(len(sink.moves), count)
        mouse.center()
        mouse.update((0., 0., 0.), now=.08)
        mouse.update((-45., 0., 0.), now=.09)
        self.assertEqual(sink.moves[-1], (-608, 0))  # Preserve outgoing 0 -> -30 then turn continuously.

    def test_turn_speed_is_independent_of_send_frequency_and_stalls_are_bounded(self):
        totals = []
        for rate in (50, 100, 200):
            mouse, sink = self.make_mouse()
            for index in range(1, rate + 1):
                mouse.update((30., 0., 0.), now=index / rate)
            totals.append(sum(x for x, _ in sink.moves))
        self.assertTrue(all(abs(total - 1600) <= 1 for total in totals), totals)
        mouse.update((30., 0., 0.), now=10.)
        self.assertLessEqual(sink.moves[-1][0], 80)

    def test_vertical_is_relative_unless_enabled_and_stops_on_focus_or_usb_loss(self):
        mouse, sink = self.make_mouse()
        mouse.update((0., 10., 0.), now=.01)
        self.assertEqual(sink.moves[-1][1], -200)
        mouse.update((0., 10., 80.), now=.02)
        self.assertEqual(len(sink.moves), 1)
        mouse.continuous_vertical = True
        mouse.reset()
        mouse.update((0., 0., 0.), now=.03)
        mouse.update((0., 30., 0.), now=.04)
        self.assertEqual(sink.moves[-1], (0, -16))
        count = len(sink.moves)
        mouse.update((90., 90., 0.), active=False, now=.05)
        mouse.update((90., 90., 0.), now=.06)
        sink.foreground = False
        mouse.update((100., 90., 0.), now=.07)
        sink.foreground = True
        mouse.update((120., 90., 0.), now=.08)
        self.assertEqual(len(sink.moves), count)


if __name__ == '__main__':
    unittest.main()
