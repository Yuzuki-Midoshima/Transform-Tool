import unittest

from transform_tool.naming import transform_group_name


class NamingTests(unittest.TestCase):
    def test_plain_name(self):
        self.assertEqual(transform_group_name("CTRL", "ZERO"), "CTRL_ZERO")

    def test_controller_suffix_is_replaced(self):
        self.assertEqual(transform_group_name("L_hand_anim", "ZERO"), "L_hand_ZERO")

    def test_namespace_is_preserved(self):
        self.assertEqual(transform_group_name("|rig|hero:L_hand_anim", "OFFSET"),
                         "hero:L_hand_OFFSET")

    def test_existing_suffix_is_replaced(self):
        self.assertEqual(transform_group_name("CTRL_ZERO", "OFFSET"), "CTRL_OFFSET")

    def test_custom_suffix(self):
        self.assertEqual(transform_group_name("L_hand_anim", "Zro"), "L_hand_Zro")

    def test_empty_suffix_is_rejected(self):
        with self.assertRaises(ValueError):
            transform_group_name("CTRL", "")


if __name__ == "__main__":
    unittest.main()
