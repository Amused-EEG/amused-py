"""
Tests for Muse Athena Protocol module
Validates correct bit-level decoding of EEG, IMU, and optics data.
"""

import unittest
import numpy as np
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import muse_athena_protocol as proto


def build_tag_packet(first_tag, first_data, extra_subpackets=None):
    """Build a synthetic TAG-based packet for testing.

    Args:
        first_tag: TAG byte for the first subpacket (goes in header byte 9).
        first_data: Data bytes for the first subpacket.
        extra_subpackets: List of (tag, data) tuples for additional subpackets.

    Returns:
        Complete packet bytes with 14-byte header.
    """
    header = bytearray(14)
    header[9] = first_tag
    packet = bytes(header) + first_data

    if extra_subpackets:
        for tag, data in extra_subpackets:
            # Each extra subpacket: [TAG(1)] [header(4)] [data(N)]
            sub_header = bytearray(4)  # 4 bytes of subpacket header
            packet += bytes([tag]) + bytes(sub_header) + data

    return packet


class TestEEGDecoding(unittest.TestCase):
    """Test 14-bit LSB-first EEG decoding"""

    def test_all_zeros(self):
        """All-zero data should decode to all zeros"""
        data = bytes(28)
        result = proto.decode_eeg(data, n_channels=4)
        self.assertEqual(result.shape, (4, 4))
        np.testing.assert_array_equal(result, np.zeros((4, 4)))

    def test_known_14bit_values(self):
        """Test decoding a known 14-bit LSB-first packed value"""
        # Pack a single 14-bit value = 1 (0b00000000000001) at position 0
        # LSB-first: bit0=1, bits1-13=0
        # In the first byte: bit0=1, rest 0 → byte = 0x01
        # Remaining bytes all zero
        data = bytearray(28)
        data[0] = 0x01  # bit0 of first value = 1

        result = proto.decode_eeg(data, n_channels=4)
        # First value (sample 0, channel 0) should be 1 * EEG_SCALE
        expected = 1.0 * proto.EEG_SCALE
        self.assertAlmostEqual(result[0, 0], expected, places=5)

    def test_max_14bit_value(self):
        """Test maximum 14-bit value (16383 = 0x3FFF)"""
        # All 14 bits set for first value
        # LSB-first: bits 0-7 all set → byte0 = 0xFF
        # bits 8-13 all set → byte1 bits 0-5 set = 0x3F
        data = bytearray(28)
        data[0] = 0xFF
        data[1] = 0x3F  # bits 8-13 of first value

        result = proto.decode_eeg(data, n_channels=4)
        expected = 16383.0 * proto.EEG_SCALE
        self.assertAlmostEqual(result[0, 0], expected, places=3)

    def test_4ch_shape(self):
        """4-channel mode produces (4, 4) array"""
        result = proto.decode_eeg(bytes(28), n_channels=4)
        self.assertEqual(result.shape, (4, 4))

    def test_8ch_shape(self):
        """8-channel mode produces (2, 8) array"""
        result = proto.decode_eeg(bytes(28), n_channels=8)
        self.assertEqual(result.shape, (2, 8))

    def test_scale_factor(self):
        """EEG scale factor should convert to microvolts"""
        # At full scale (16383), output should be ~1450 uV
        self.assertAlmostEqual(proto.EEG_SCALE * 16383, 1450.0, places=0)


class TestAccGyroDecoding(unittest.TestCase):
    """Test 16-bit little-endian IMU decoding"""

    def test_all_zeros(self):
        """All-zero data should decode to all zeros"""
        data = bytes(36)
        result = proto.decode_accgyro(data)
        self.assertEqual(result.shape, (3, 6))
        np.testing.assert_array_equal(result, np.zeros((3, 6)))

    def test_known_values(self):
        """Test decoding known 16-bit LE values"""
        # Create data with known int16 LE values
        # First sample, first channel (accel_x) = 100
        values = np.array([[100, 0, 0, 0, 0, 0],
                          [0, 0, 0, 0, 0, 0],
                          [0, 0, 0, 0, 0, 0]], dtype=np.int16)
        data = values.tobytes()  # numpy int16 is native, but on most systems LE

        result = proto.decode_accgyro(data)
        # First accel value should be 100 * ACC_SCALE
        self.assertAlmostEqual(result[0, 0], 100.0 * proto.ACC_SCALE, places=6)

    def test_scale_separation(self):
        """Accel and gyro should use different scale factors"""
        values = np.array([[1000, 1000, 1000, 1000, 1000, 1000],
                          [0, 0, 0, 0, 0, 0],
                          [0, 0, 0, 0, 0, 0]], dtype='<i2')
        data = values.tobytes()

        result = proto.decode_accgyro(data)
        accel_val = result[0, 0]
        gyro_val = result[0, 3]

        # They should be different due to different scales
        self.assertNotAlmostEqual(accel_val, gyro_val, places=3)


class TestOpticsDecoding(unittest.TestCase):
    """Test 20-bit LSB-first optics decoding"""

    def test_all_zeros(self):
        """All-zero data should decode to all zeros"""
        result = proto.decode_optics(bytes(40), n_channels=8)
        self.assertEqual(result.shape, (2, 8))
        np.testing.assert_array_equal(result, np.zeros((2, 8)))

    def test_4ch_shape(self):
        """4-channel mode produces (3, 4) from 30 bytes"""
        result = proto.decode_optics(bytes(30), n_channels=4)
        self.assertEqual(result.shape, (3, 4))

    def test_8ch_shape(self):
        """8-channel mode produces (2, 8) from 40 bytes"""
        result = proto.decode_optics(bytes(40), n_channels=8)
        self.assertEqual(result.shape, (2, 8))

    def test_16ch_shape(self):
        """16-channel mode produces (1, 16) from 40 bytes"""
        result = proto.decode_optics(bytes(40), n_channels=16)
        self.assertEqual(result.shape, (1, 16))

    def test_known_20bit_value(self):
        """Test decoding a known 20-bit LSB-first value"""
        # Pack value = 1 at position 0
        data = bytearray(40)
        data[0] = 0x01  # bit0 of first value = 1

        result = proto.decode_optics(data, n_channels=8)
        expected = 1.0 * proto.OPTICS_SCALE
        self.assertAlmostEqual(result[0, 0], expected, places=8)


class TestPayloadParsing(unittest.TestCase):
    """Test full payload parsing with TAG-based subpackets"""

    def test_eeg_only_packet(self):
        """Parse packet with only EEG subpacket"""
        packet = build_tag_packet(proto.TAG_EEG_4CH, bytes(28))
        result = proto.parse_payload(packet)

        self.assertEqual(len(result["EEG"]), 1)
        self.assertEqual(len(result["ACCGYRO"]), 0)
        self.assertEqual(len(result["OPTICS"]), 0)

        eeg = result["EEG"][0]
        self.assertEqual(eeg["type"], "EEG")
        self.assertEqual(eeg["tag"], proto.TAG_EEG_4CH)
        self.assertEqual(eeg["n_channels"], 4)
        self.assertEqual(eeg["n_samples"], 4)
        self.assertEqual(eeg["data"].shape, (4, 4))

    def test_multi_subpacket(self):
        """Parse packet with EEG + ACCGYRO + OPTICS"""
        packet = build_tag_packet(
            proto.TAG_EEG_4CH, bytes(28),
            extra_subpackets=[
                (proto.TAG_ACCGYRO, bytes(36)),
                (proto.TAG_OPTICS_8CH, bytes(40)),
            ]
        )
        result = proto.parse_payload(packet)

        self.assertEqual(len(result["EEG"]), 1)
        self.assertEqual(len(result["ACCGYRO"]), 1)
        self.assertEqual(len(result["OPTICS"]), 1)

    def test_short_payload_returns_empty(self):
        """Payload shorter than header returns empty result"""
        result = proto.parse_payload(bytes(10))
        self.assertEqual(len(result["EEG"]), 0)

    def test_unknown_first_tag(self):
        """Unknown first TAG returns empty result"""
        header = bytearray(14)
        header[9] = 0x99  # Unknown TAG
        result = proto.parse_payload(bytes(header) + bytes(28))
        self.assertEqual(len(result["EEG"]), 0)


class TestCommandEncoding(unittest.TestCase):
    """Test command encoding"""

    def test_encode_v6(self):
        """v6 command should encode correctly"""
        result = proto.encode_cmd("v6")
        # Length = len("v6\n") + 1 = 4
        self.assertEqual(result[0], 4)
        self.assertEqual(result[1:3], b"v6")
        self.assertEqual(result[3], ord("\n"))

    def test_encode_dc001(self):
        """dc001 command should encode correctly"""
        result = proto.encode_cmd("dc001")
        self.assertEqual(result[0], 7)  # len("dc001\n") + 1
        self.assertEqual(result[1:6], b"dc001")

    def test_preencoded_commands_match(self):
        """Pre-encoded COMMANDS dict should match encode_cmd output"""
        for name, expected in proto.COMMANDS.items():
            with self.subTest(cmd=name):
                self.assertEqual(proto.encode_cmd(name), expected)


class TestInitSequence(unittest.TestCase):
    """Test init sequence generation"""

    def test_default_sequence_length(self):
        """Default sequence should have correct number of steps"""
        seq = proto.get_init_sequence()
        self.assertEqual(len(seq), 12)

    def test_sequence_has_double_dc001(self):
        """Sequence must send dc001 twice"""
        seq = proto.get_init_sequence()
        dc001_count = sum(1 for desc, cmd, _ in seq if cmd == proto.COMMANDS["dc001"])
        self.assertEqual(dc001_count, 2)

    def test_sequence_has_halt_between(self):
        """There must be a halt between the two dc001 commands"""
        seq = proto.get_init_sequence()
        dc001_indices = [i for i, (_, cmd, _) in enumerate(seq) if cmd == proto.COMMANDS["dc001"]]
        self.assertEqual(len(dc001_indices), 2)

        # Check there's a halt between them
        halt_indices = [i for i, (_, cmd, _) in enumerate(seq) if cmd == proto.COMMANDS["h"]]
        between_halts = [i for i in halt_indices if dc001_indices[0] < i < dc001_indices[1]]
        self.assertGreater(len(between_halts), 0)

    def test_custom_preset(self):
        """Custom preset should appear in the sequence"""
        seq = proto.get_init_sequence("p1035")
        preset_cmds = [cmd for _, cmd, _ in seq if cmd == proto.COMMANDS["p1035"]]
        self.assertGreater(len(preset_cmds), 0)


class TestSensorConfig(unittest.TestCase):
    """Test sensor configuration constants"""

    def test_all_tags_have_config(self):
        """All defined TAGs should have sensor config"""
        tags = [proto.TAG_EEG_4CH, proto.TAG_EEG_8CH, proto.TAG_ACCGYRO,
                proto.TAG_OPTICS_4CH, proto.TAG_OPTICS_8CH, proto.TAG_OPTICS_16CH,
                proto.TAG_BATTERY_1, proto.TAG_BATTERY_2]
        for tag in tags:
            self.assertIn(tag, proto.SENSOR_CONFIG)

    def test_eeg_data_lengths(self):
        """EEG data length should be 28 bytes for both modes"""
        self.assertEqual(proto.SENSOR_CONFIG[proto.TAG_EEG_4CH][3], 28)
        self.assertEqual(proto.SENSOR_CONFIG[proto.TAG_EEG_8CH][3], 28)

    def test_accgyro_data_length(self):
        """ACCGYRO data length should be 36 bytes"""
        self.assertEqual(proto.SENSOR_CONFIG[proto.TAG_ACCGYRO][3], 36)


if __name__ == '__main__':
    unittest.main()
