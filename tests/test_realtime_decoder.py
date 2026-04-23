"""
Tests for Muse Real-time Decoder
"""

import unittest
import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_realtime_decoder import MuseRealtimeDecoder, DecodedData
import muse_athena_protocol as proto


def build_tag_packet(first_tag, first_data, extra_subpackets=None):
    """Build a synthetic TAG-based packet for testing."""
    header = bytearray(14)
    header[9] = first_tag
    packet = bytes(header) + first_data
    if extra_subpackets:
        for tag, data in extra_subpackets:
            sub_header = bytearray(4)
            packet += bytes([tag]) + bytes(sub_header) + data
    return packet


class TestRealtimeDecoder(unittest.TestCase):
    """Test real-time packet decoding"""

    def setUp(self):
        """Set up test fixtures"""
        self.decoder = MuseRealtimeDecoder()

    def test_eeg_packet_decoding(self):
        """Test EEG packet decoding with TAG-based format"""
        eeg_packet = build_tag_packet(proto.TAG_EEG_4CH, bytes(28))

        decoded = self.decoder.decode(eeg_packet)

        self.assertIsNotNone(decoded.eeg)
        # Should have 4 channels
        self.assertEqual(len(decoded.eeg), 4)
        # Should use proper channel names
        for name in proto.EEG_CHANNELS_4:
            self.assertIn(name, decoded.eeg)
        # Each channel should have 4 samples (4ch mode)
        self.assertEqual(len(decoded.eeg['TP9']), 4)

    def test_imu_packet_decoding(self):
        """Test IMU packet decoding with TAG-based format"""
        imu_packet = build_tag_packet(proto.TAG_ACCGYRO, bytes(36))

        decoded = self.decoder.decode(imu_packet)

        self.assertIsNotNone(decoded.imu)
        self.assertIn('accel', decoded.imu)
        self.assertIn('gyro', decoded.imu)
        # 3 samples x 3 accel channels
        self.assertEqual(len(decoded.imu['accel']), 3)
        self.assertEqual(len(decoded.imu['gyro']), 3)

    def test_optics_packet_decoding(self):
        """Test optics/PPG packet decoding with TAG-based format"""
        optics_packet = build_tag_packet(proto.TAG_OPTICS_8CH, bytes(40))

        decoded = self.decoder.decode(optics_packet)

        self.assertIsNotNone(decoded.ppg)
        # Should have 8 optics channels
        self.assertEqual(len(decoded.ppg), 8)
        for name in proto.OPTICS_CHANNELS_8:
            self.assertIn(name, decoded.ppg)

    def test_multi_subpacket(self):
        """Test packet with multiple subpacket types"""
        packet = build_tag_packet(
            proto.TAG_EEG_4CH, bytes(28),
            extra_subpackets=[
                (proto.TAG_ACCGYRO, bytes(36)),
                (proto.TAG_OPTICS_8CH, bytes(40)),
            ]
        )

        decoded = self.decoder.decode(packet)

        self.assertIsNotNone(decoded.eeg)
        self.assertIsNotNone(decoded.imu)
        self.assertIsNotNone(decoded.ppg)
        self.assertEqual(decoded.packet_type, 'MULTI')

    def test_callback_system(self):
        """Test callback registration and triggering"""
        eeg_called = False
        packet_data = None

        def on_eeg(data: DecodedData):
            nonlocal eeg_called, packet_data
            eeg_called = True
            packet_data = data

        self.decoder.register_callback('eeg', on_eeg)

        eeg_packet = build_tag_packet(proto.TAG_EEG_4CH, bytes(28))
        self.decoder.decode(eeg_packet)

        self.assertTrue(eeg_called)
        self.assertIsNotNone(packet_data)
        self.assertIsNotNone(packet_data.eeg)

    def test_statistics_tracking(self):
        """Test statistics tracking"""
        self.decoder.reset_stats()

        eeg_packet = build_tag_packet(proto.TAG_EEG_4CH, bytes(28))
        imu_packet = build_tag_packet(proto.TAG_ACCGYRO, bytes(36))

        self.decoder.decode(eeg_packet)
        self.decoder.decode(imu_packet)

        stats = self.decoder.get_stats()

        self.assertEqual(stats['packets_decoded'], 2)
        self.assertGreater(stats['eeg_samples'], 0)
        self.assertGreater(stats['imu_samples'], 0)
        self.assertEqual(stats['decode_errors'], 0)

    def test_error_handling(self):
        """Test error handling for malformed packets"""
        # Empty packet
        decoded = self.decoder.decode(b'')
        self.assertEqual(decoded.packet_type, 'EMPTY')

        # Very short packet
        decoded = self.decoder.decode(b'\x00')
        self.assertIsNotNone(decoded)

        # Malformed packet shouldn't crash
        decoded = self.decoder.decode(b'\xFF\xFF\xFF')
        self.assertIsNotNone(decoded)

        stats = self.decoder.get_stats()
        self.assertGreaterEqual(stats['packets_decoded'], 3)


class TestDecodedData(unittest.TestCase):
    """Test DecodedData dataclass"""

    def test_decoded_data_creation(self):
        """Test creating DecodedData objects"""
        data = DecodedData(
            timestamp=datetime.datetime.now(),
            packet_type='TEST',
            eeg={'TP9': [1, 2, 3]},
            ppg={'LO_NIR': [100, 200]},
            imu={'accel': [[0, 0, 1]], 'gyro': [[0, 0, 0]]},
            heart_rate=72.5,
            battery=85,
            raw_bytes=b'\x00\x01\x02'
        )

        self.assertEqual(data.packet_type, 'TEST')
        self.assertEqual(len(data.eeg['TP9']), 3)
        self.assertEqual(data.heart_rate, 72.5)
        self.assertEqual(data.battery, 85)

if __name__ == '__main__':
    unittest.main()
