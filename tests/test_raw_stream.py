"""
Tests for Muse Raw Stream Binary Format
"""

import unittest
import tempfile
import os
import datetime
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_raw_stream import MuseRawStream, RawPacket
import muse_athena_protocol as proto


def build_tag_packet(first_tag, first_data):
    """Build a synthetic TAG-based packet for testing."""
    header = bytearray(14)
    header[9] = first_tag
    return bytes(header) + first_data


class TestMuseRawStream(unittest.TestCase):
    """Test binary stream storage and retrieval"""

    def setUp(self):
        """Create temporary file for testing"""
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.bin', delete=False)
        self.temp_file.close()
        self.filepath = self.temp_file.name

    def tearDown(self):
        """Clean up temporary file"""
        if os.path.exists(self.filepath):
            os.unlink(self.filepath)

    def test_write_and_read_single_packet(self):
        """Test writing and reading a single packet"""
        stream = MuseRawStream(self.filepath)

        test_data = build_tag_packet(proto.TAG_EEG_4CH, bytes(28))
        test_time = datetime.datetime.now()

        stream.open_write()
        stream.write_packet(test_data, test_time)
        stream.close()

        stream.open_read()
        packets = list(stream.read_packets())
        stream.close()

        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0].data, test_data)
        self.assertEqual(packets[0].packet_num, 0)

        time_diff = abs((packets[0].timestamp - test_time).total_seconds())
        self.assertLess(time_diff, 0.001)

    def test_write_and_read_multiple_packets(self):
        """Test writing and reading multiple packets"""
        stream = MuseRawStream(self.filepath)

        stream.open_write()
        test_packets = []

        for i in range(10):
            data = bytes([i, 0x00] + [i] * 50)
            timestamp = datetime.datetime.now()
            stream.write_packet(data, timestamp)
            test_packets.append((data, timestamp))

        stream.close()

        stream.open_read()
        read_packets = list(stream.read_packets())
        stream.close()

        self.assertEqual(len(read_packets), 10)

        for i, packet in enumerate(read_packets):
            self.assertEqual(packet.packet_num, i)
            self.assertEqual(packet.data, test_packets[i][0])

    def test_file_header_format(self):
        """Test that file header is correctly written and read"""
        stream = MuseRawStream(self.filepath)

        stream.open_write()
        self.assertIsNotNone(stream.session_start)
        original_start = stream.session_start
        stream.write_packet(b'\x00\x01\x02')
        stream.close()

        stream.open_read()
        self.assertIsNotNone(stream.session_start)

        time_diff = abs((stream.session_start - original_start).total_seconds())
        self.assertLess(time_diff, 1.0)
        stream.close()

    def test_relative_timestamps(self):
        """Test that relative timestamps work correctly"""
        stream = MuseRawStream(self.filepath)

        stream.open_write()
        base_time = stream.session_start

        for i in range(5):
            timestamp = base_time + datetime.timedelta(milliseconds=i * 100)
            stream.write_packet(bytes([i]), timestamp)

        stream.close()

        stream.open_read()
        packets = list(stream.read_packets())
        stream.close()

        for i, packet in enumerate(packets):
            expected_time = base_time + datetime.timedelta(milliseconds=i * 100)
            time_diff = abs((packet.timestamp - expected_time).total_seconds())
            self.assertLess(time_diff, 0.001)

    def test_file_info(self):
        """Test file info extraction"""
        stream = MuseRawStream(self.filepath)

        stream.open_write()
        for i in range(100):
            if i % 2 == 0:
                data = build_tag_packet(proto.TAG_EEG_4CH, bytes(28))
            else:
                data = build_tag_packet(proto.TAG_ACCGYRO, bytes(36))
            stream.write_packet(data)
        stream.close()

        info = stream.get_file_info()

        self.assertEqual(info['packet_count'], 100)
        self.assertEqual(info['format_version'], 2)
        self.assertIsNotNone(info['session_start'])
        self.assertGreater(info['file_size_bytes'], 0)
        self.assertGreater(info['average_packet_size'], 0)
        # Check TAG-based type names are present
        self.assertTrue(any('EEG' in k for k in info['packet_types']))

    def test_decode_packet(self):
        """Test decoding a packet using TAG-based protocol"""
        stream = MuseRawStream(self.filepath)

        eeg_data = build_tag_packet(proto.TAG_EEG_4CH, bytes(28))
        stream.open_write()
        stream.write_packet(eeg_data)
        stream.close()

        stream.open_read()
        packets = list(stream.read_packets())
        stream.close()

        decoded = stream.decode_packet(packets[0])
        self.assertIn('EEG', decoded['packet_type'])
        self.assertIn('eeg', decoded)

    def test_invalid_file_handling(self):
        """Test handling of invalid files"""
        with open(self.filepath, 'wb') as f:
            f.write(b'XXXX\x02')

        stream = MuseRawStream(self.filepath)

        with self.assertRaises(ValueError) as context:
            stream.open_read()

        self.assertIn("Invalid file format", str(context.exception))


class TestRawPacket(unittest.TestCase):
    """Test RawPacket dataclass"""

    def test_packet_creation(self):
        """Test creating RawPacket objects"""
        packet = RawPacket(
            timestamp=datetime.datetime.now(),
            packet_num=42,
            packet_type=0x00,
            data=b'\x00\x01\x02\x03'
        )

        self.assertEqual(packet.packet_num, 42)
        self.assertEqual(packet.data, b'\x00\x01\x02\x03')
        self.assertIsInstance(packet.timestamp, datetime.datetime)

if __name__ == '__main__':
    unittest.main()
