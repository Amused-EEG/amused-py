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
        
        # Write a packet
        test_data = bytes([0xDF, 0x00, 0x00] + [0x80] * 100)
        test_time = datetime.datetime.now()
        
        stream.open_write()
        stream.write_packet(test_data, test_time)
        stream.close()
        
        # Read it back
        stream.open_read()
        packets = list(stream.read_packets())
        stream.close()
        
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0].data, test_data)
        self.assertEqual(packets[0].packet_num, 0)
        self.assertEqual(packets[0].packet_type, 0xDF)
        
        # Timestamp should be close to original (within 1ms)
        time_diff = abs((packets[0].timestamp - test_time).total_seconds())
        self.assertLess(time_diff, 0.001)
    
    def test_write_and_read_multiple_packets(self):
        """Test writing and reading multiple packets"""
        stream = MuseRawStream(self.filepath)
        
        # Write multiple packets
        stream.open_write()
        test_packets = []
        
        for i in range(10):
            data = bytes([i, 0x00] + [i] * 50)
            timestamp = datetime.datetime.now()
            stream.write_packet(data, timestamp)
            test_packets.append((data, timestamp))
        
        stream.close()
        
        # Read them back
        stream.open_read()
        read_packets = list(stream.read_packets())
        stream.close()
        
        self.assertEqual(len(read_packets), 10)
        
        for i, packet in enumerate(read_packets):
            self.assertEqual(packet.packet_num, i)
            self.assertEqual(packet.data, test_packets[i][0])
            self.assertEqual(packet.packet_type, i)
    
    def test_file_header_format(self):
        """Test that file header is correctly written and read"""
        stream = MuseRawStream(self.filepath)
        
        # Write with header
        stream.open_write()
        self.assertIsNotNone(stream.session_start)
        original_start = stream.session_start
        stream.write_packet(b'\x00\x01\x02')
        stream.close()
        
        # Read and verify header
        stream.open_read()
        self.assertIsNotNone(stream.session_start)
        
        # Session start times should match (within 1 second)
        time_diff = abs((stream.session_start - original_start).total_seconds())
        self.assertLess(time_diff, 1.0)
        stream.close()
    
    def test_relative_timestamps(self):
        """Test that relative timestamps work correctly"""
        stream = MuseRawStream(self.filepath)
        
        stream.open_write()
        base_time = stream.session_start
        
        # Write packets at specific intervals
        for i in range(5):
            # Each packet 100ms after the previous
            timestamp = base_time + datetime.timedelta(milliseconds=i * 100)
            stream.write_packet(bytes([i]), timestamp)
        
        stream.close()
        
        # Read and verify timing
        stream.open_read()
        packets = list(stream.read_packets())
        stream.close()
        
        for i, packet in enumerate(packets):
            expected_time = base_time + datetime.timedelta(milliseconds=i * 100)
            time_diff = abs((packet.timestamp - expected_time).total_seconds())
            self.assertLess(time_diff, 0.001)  # Within 1ms
    
    def test_file_info(self):
        """Test file info extraction"""
        stream = MuseRawStream(self.filepath)
        
        # Write some test data
        stream.open_write()
        for i in range(100):
            data = bytes([0xDF if i % 2 == 0 else 0xF4] + [0x00] * 50)
            stream.write_packet(data)
        stream.close()
        
        # Get file info
        info = stream.get_file_info()
        
        self.assertEqual(info['packet_count'], 100)
        self.assertIn('MULTI_EEG_PPG', info['packet_types'])
        self.assertIn('MULTI_IMU', info['packet_types'])
        self.assertEqual(info['format_version'], 2)
        self.assertIsNotNone(info['session_start'])
        self.assertGreater(info['file_size_bytes'], 0)
        self.assertGreater(info['average_packet_size'], 0)
    
    def test_invalid_file_handling(self):
        """Test handling of invalid files"""
        # Write invalid magic number
        with open(self.filepath, 'wb') as f:
            f.write(b'XXXX\x02')  # Wrong magic
        
        stream = MuseRawStream(self.filepath)
        
        with self.assertRaises(ValueError) as context:
            stream.open_read()
        
        self.assertIn("Invalid file format", str(context.exception))
    
    def test_packet_type_detection(self):
        """Test packet type detection"""
        stream = MuseRawStream(self.filepath)
        
        # Test different packet types
        packet_types = {
            0xDF: 'MULTI_EEG_PPG',
            0xF4: 'MULTI_IMU',
            0xDB: 'MULTI_MIXED_1',
            0xD9: 'MULTI_MIXED_2',
            0xFF: 'UNKNOWN'
        }
        
        stream.open_write()
        for type_byte in packet_types.keys():
            stream.write_packet(bytes([type_byte, 0x00, 0x00]))
        stream.close()
        
        # Read and verify types
        stream.open_read()
        packets = list(stream.read_packets())
        stream.close()
        
        for i, (type_byte, type_name) in enumerate(packet_types.items()):
            self.assertEqual(packets[i].packet_type, type_byte)

class TestRawPacket(unittest.TestCase):
    """Test RawPacket dataclass"""
    
    def test_packet_creation(self):
        """Test creating RawPacket objects"""
        packet = RawPacket(
            timestamp=datetime.datetime.now(),
            packet_num=42,
            packet_type=0xDF,
            data=b'\x00\x01\x02\x03'
        )
        
        self.assertEqual(packet.packet_num, 42)
        self.assertEqual(packet.packet_type, 0xDF)
        self.assertEqual(packet.data, b'\x00\x01\x02\x03')
        self.assertIsInstance(packet.timestamp, datetime.datetime)

if __name__ == '__main__':
    unittest.main()