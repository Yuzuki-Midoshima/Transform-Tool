import unittest

import maya.standalone

maya.standalone.initialize(name="python")

from maya import cmds

from transform_tool import operations


class OperationsTests(unittest.TestCase):
    def setUp(self):
        cmds.file(new=True, force=True)

    def assertIdentity(self, node):
        self.assertEqual(tuple(round(v, 6) for v in cmds.getAttr(node + ".translate")[0]),
                         (0.0, 0.0, 0.0))
        self.assertEqual(tuple(round(v, 6) for v in cmds.getAttr(node + ".rotate")[0]),
                         (0.0, 0.0, 0.0))
        self.assertEqual(tuple(round(v, 6) for v in cmds.getAttr(node + ".scale")[0]),
                         (1.0, 1.0, 1.0))

    def test_zero_under_existing_parent_preserves_world_transform(self):
        parent = cmds.group(empty=True, name="Parent")
        node = cmds.group(empty=True, name="CTRL", parent=parent)
        cmds.setAttr(node + ".translate", 2, 3, 4)
        cmds.setAttr(node + ".rotate", 10, 20, 30)
        before = cmds.xform(node, query=True, matrix=True, worldSpace=True)
        cmds.select(node)

        operations.create_zero()

        self.assertEqual(cmds.listRelatives("CTRL_ZERO", parent=True), ["Parent"])
        self.assertEqual(cmds.listRelatives("CTRL", parent=True), ["CTRL_ZERO"])
        self.assertIdentity("CTRL")
        after = cmds.xform("CTRL", query=True, matrix=True, worldSpace=True)
        self.assertTrue(all(abs(a - b) < operations.TOLERANCE
                            for a, b in zip(before, after)))

    def test_zero_offset_order_and_single_undo(self):
        node = cmds.group(empty=True, name="hand_anim")
        cmds.setAttr(node + ".translateX", 8)
        cmds.select(node)

        operations.create_zero_offset()

        self.assertEqual(cmds.listRelatives("hand_anim", parent=True), ["hand_ZERO"])
        self.assertEqual(cmds.listRelatives("hand_ZERO", parent=True), ["hand_OFFSET"])
        self.assertIdentity("hand_anim")
        cmds.undo()
        self.assertTrue(cmds.objExists("hand_anim"))
        self.assertFalse(cmds.objExists("hand_ZERO"))
        self.assertFalse(cmds.objExists("hand_OFFSET"))

    def test_multiple_selection(self):
        nodes = [cmds.group(empty=True, name=name) for name in ("left_anim", "right_anim")]
        cmds.select(nodes)
        operations.create_zero()
        for name in ("left", "right"):
            self.assertTrue(cmds.objExists(name + "_ZERO"))
            self.assertIdentity(name + "_anim")

    def test_joint_is_skipped(self):
        joint = cmds.createNode("joint", name="arm_jnt")
        cmds.select(joint)
        self.assertEqual(operations.create_zero(), [])
        self.assertFalse(cmds.objExists("arm_jnt_ZERO"))

    def test_curve_shaped_joint_controller_preserves_joint_orientation(self):
        parent = cmds.group(empty=True, name="rig_GRP")
        joint = cmds.createNode("joint", name="wrist_anim", parent=parent)
        curve = cmds.circle(name="temporary_curve", normal=(1, 0, 0))[0]
        shape = cmds.listRelatives(curve, shapes=True, fullPath=True)[0]
        cmds.parent(shape, joint, shape=True, relative=True)
        cmds.delete(curve)
        cmds.setAttr(joint + ".jointOrient", 12.0, 23.0, -7.0)
        cmds.setAttr(joint + ".rotateAxis", 2.0, -4.0, 1.0)
        cmds.setAttr(joint + ".translate", 3.0, 5.0, 7.0)
        cmds.setAttr(joint + ".rotate", 9.0, -11.0, 18.0)
        before_world = cmds.xform(joint, query=True, matrix=True, worldSpace=True)
        before_orient = cmds.getAttr(joint + ".jointOrient")[0]
        before_axis = cmds.getAttr(joint + ".rotateAxis")[0]
        cmds.select(joint)

        operations.create_zero(allow_joint_controllers=True)

        self.assertEqual(cmds.listRelatives("wrist_anim", parent=True),
                         ["wrist_ZERO"])
        self.assertIdentity("wrist_anim")
        self.assertEqual(cmds.getAttr("wrist_anim.jointOrient")[0], before_orient)
        self.assertEqual(cmds.getAttr("wrist_anim.rotateAxis")[0], before_axis)
        after_world = cmds.xform("wrist_anim", query=True, matrix=True, worldSpace=True)
        self.assertTrue(all(abs(a - b) < operations.TOLERANCE
                            for a, b in zip(before_world, after_world)))

    def test_plain_skeleton_joint_remains_blocked_in_joint_controller_mode(self):
        joint = cmds.createNode("joint", name="spine_jnt")
        cmds.select(joint)
        self.assertEqual(
            operations.create_zero(allow_joint_controllers=True), []
        )
        self.assertFalse(cmds.objExists("spine_jnt_ZERO"))

    def test_connection_and_lock_are_preserved_during_group_creation(self):
        source = cmds.group(empty=True, name="driver")
        connected = cmds.group(empty=True, name="connected")
        locked = cmds.group(empty=True, name="locked")
        cmds.connectAttr(source + ".translateX", connected + ".translateX")
        cmds.setAttr(locked + ".rotateY", lock=True)
        before = cmds.xform(connected, query=True, matrix=True, worldSpace=True)
        cmds.select(connected, locked)
        operations.create_offset()

        self.assertTrue(cmds.objExists("connected_OFFSET"))
        self.assertTrue(cmds.objExists("locked_OFFSET"))
        self.assertTrue(cmds.isConnected(
            source + ".translateX", "connected_OFFSET.translateX"
        ))
        self.assertIdentity("connected")
        after = cmds.xform(connected, query=True, matrix=True, worldSpace=True)
        self.assertTrue(all(abs(a - b) < operations.TOLERANCE
                            for a, b in zip(before, after)))
        self.assertTrue(cmds.getAttr("locked.rotateY", lock=True))

    def test_parent_constrained_controller_can_receive_zero_group(self):
        target = cmds.group(empty=True, name="constraint_target")
        controller = cmds.circle(name="constrained_CTRL")[0]
        cmds.setAttr(target + ".translate", 3.0, 4.0, 5.0, type="double3")
        constraint = cmds.parentConstraint(target, controller)[0]
        before = cmds.xform(controller, query=True, matrix=True, worldSpace=True)
        cmds.select(controller)

        operations.create_zero()

        self.assertTrue(cmds.objExists("constrained_ZERO"))
        self.assertEqual(cmds.listRelatives(controller, parent=True),
                         ["constrained_ZERO"])
        after = cmds.xform(controller, query=True, matrix=True, worldSpace=True)
        self.assertTrue(all(abs(a - b) < operations.TOLERANCE
                            for a, b in zip(before, after)))
        self.assertIdentity(controller)
        self.assertIn(constraint, cmds.listConnections(
            "constrained_ZERO.translateX", source=True, destination=False
        ))

    def test_parent_constraint_moves_to_outer_offset_group(self):
        target = cmds.group(empty=True, name="outer_target")
        controller = cmds.circle(name="outer_CTRL")[0]
        cmds.setAttr(target + ".translate", 2.0, 3.0, 4.0, type="double3")
        cmds.setAttr(target + ".rotate", 10.0, 20.0, 30.0, type="double3")
        constraint = cmds.parentConstraint(target, controller)[0]
        before = cmds.xform(controller, query=True, matrix=True, worldSpace=True)
        cmds.select(controller)

        operations.create_zero_offset()

        self.assertIdentity("outer_CTRL")
        self.assertIdentity("outer_ZERO")
        self.assertIn(constraint, cmds.listConnections(
            "outer_OFFSET.rotateX", source=True, destination=False
        ))
        after = cmds.xform(controller, query=True, matrix=True, worldSpace=True)
        self.assertTrue(all(abs(a - b) < operations.TOLERANCE
                            for a, b in zip(before, after)))

    def test_locked_channel_can_be_temporarily_unlocked_and_restored(self):
        node = cmds.group(empty=True, name="locked_anim")
        cmds.setAttr(node + ".translateY", lock=True)
        cmds.select(node)
        operations.create_zero("HOME", unlock_locked=True)
        self.assertTrue(cmds.objExists("locked_HOME"))
        self.assertIdentity("locked_anim")
        self.assertTrue(cmds.getAttr("locked_anim.translateY", lock=True))

    def test_hidden_locked_channels_are_automatically_supported(self):
        node = cmds.group(empty=True, name="hidden_locked_anim")
        cmds.setAttr(node + ".translateX", 4.0)
        cmds.setAttr(node + ".translateX", keyable=False, channelBox=False)
        cmds.setAttr(node + ".translateX", lock=True)
        cmds.select(node)

        operations.create_zero()

        self.assertTrue(cmds.objExists("hidden_locked_ZERO"))
        self.assertIdentity("hidden_locked_anim")
        self.assertTrue(cmds.getAttr("hidden_locked_anim.translateX", lock=True))
        self.assertFalse(cmds.getAttr("hidden_locked_anim.translateX", keyable=True))
        self.assertFalse(cmds.getAttr("hidden_locked_anim.translateX", channelBox=True))

    def test_delete_all_controller_animation(self):
        controller = cmds.circle(name="hand_CTRL")[0]
        other = cmds.group(empty=True, name="not_a_controller")
        cmds.setKeyframe(controller, attribute="translateX", time=(1, 10))
        cmds.setKeyframe(other, attribute="translateX", time=(1, 10))

        self.assertEqual(operations.delete_all_controller_animation(), 2)

        self.assertEqual(cmds.keyframe(controller, query=True, keyframeCount=True), 0)
        self.assertEqual(cmds.keyframe(other, query=True, keyframeCount=True), 2)

    def test_delete_animation_can_target_one_controller(self):
        first = cmds.circle(name="first_CTRL")[0]
        second = cmds.circle(name="second_CTRL")[0]
        cmds.setKeyframe(first, attribute="translateX", time=(1, 10))
        cmds.setKeyframe(second, attribute="translateX", time=(1, 10))

        operations.delete_all_controller_animation([first])

        self.assertEqual(cmds.keyframe(first, query=True, keyframeCount=True), 0)
        self.assertEqual(cmds.keyframe(second, query=True, keyframeCount=True), 2)

    def test_reset_visible_controllers_respects_safety_filters(self):
        visible = cmds.circle(name="visible_CTRL")[0]
        hidden = cmds.circle(name="hidden_CTRL")[0]
        cmds.setAttr(hidden + ".visibility", False)
        cmds.setAttr(visible + ".translate", 3.0, 4.0, 5.0, type="double3")
        cmds.setAttr(visible + ".rotateX", 25.0)
        cmds.setAttr(visible + ".scale", 2.0, 3.0, 4.0, type="double3")
        cmds.setAttr(visible + ".translateY", lock=True)
        driver = cmds.createNode("multiplyDivide", name="driver")
        cmds.setAttr(driver + ".input1X", 7.0)
        cmds.connectAttr(driver + ".outputX", visible + ".rotateX")
        cmds.setAttr(hidden + ".translateX", 9.0)

        changed, skipped = operations.reset_all_visible_controllers()

        self.assertIn("|visible_CTRL", changed)
        self.assertEqual(skipped, [])
        self.assertEqual(cmds.getAttr(visible + ".translateX"), 0.0)
        self.assertEqual(cmds.getAttr(visible + ".translateY"), 4.0)
        self.assertEqual(cmds.getAttr(visible + ".rotateX"), 7.0)
        self.assertEqual(cmds.getAttr(visible + ".scale")[0], (1.0, 1.0, 1.0))
        self.assertEqual(cmds.getAttr(hidden + ".translateX"), 9.0)

    def test_reset_plan_can_apply_translate_only(self):
        controller = cmds.circle(name="partial_CTRL")[0]
        cmds.setAttr(controller + ".translateX", 5.0)
        cmds.setAttr(controller + ".rotateY", 25.0)
        plan, unused_skipped = operations.controller_reset_plan()
        controller_plan = next(row for row in plan if row[0].endswith("partial_CTRL"))
        node, changes = controller_plan
        translate_changes = [row for row in changes if row[0].startswith("t")]

        operations.reset_all_visible_controllers([(node, translate_changes)])

        self.assertEqual(cmds.getAttr(controller + ".translateX"), 0.0)
        self.assertEqual(cmds.getAttr(controller + ".rotateY"), 25.0)


if __name__ == "__main__":
    unittest.main()
