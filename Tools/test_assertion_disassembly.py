import unittest
from disassemble_assertion import branch_target


class BranchTargets(unittest.TestCase):
    def test_forward_and_backward_calls(self):
        self.assertEqual(branch_target(0x94000010, 0x1000), 0x1040)
        self.assertEqual(branch_target(0x97fffff0, 0x1000), 0xfc0)

    def test_condition_and_test_bit_branches(self):
        self.assertEqual(branch_target(0x54000080, 0x1000), 0x1010)
        self.assertEqual(branch_target(0x34000080, 0x1000), 0x1010)
        self.assertEqual(branch_target(0x36000080, 0x1000), 0x1010)
        self.assertIsNone(branch_target(0xd503201f, 0x1000))
