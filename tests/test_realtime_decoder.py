"""
Tests for Muse Real-time Decoder
"""

import unittest
import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_realtime_decoder import MuseRealtimeDecoder, DecodedData

class TestRealtimeDecoder(unittest.TestCase):
    """Test real-time packet decoding"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.decoder = MuseRealtimeDecoder()
    
    def test_eeg_packet_decoding(self):
        """Test EEG packet decoding"""
        # Create a mock EEG packet (0xDF type)
        # Header + 18 bytes of EEG data (represents 12 samples)
        eeg_packet = bytes([0xDF, 0x00, 0x00, 0x00] + [0x80, 0x08] * 9)
        
        decoded = self.decoder.decode(eeg_packet)
        
        self.assertEqual(decoded.packet_type, 'EEG_PPG')
        self.assertIsNotNone(decoded.eeg)
        self.assertIn('ch0', decoded.eeg)
        self.assertEqual(len(decoded.eeg['ch0']), 12)  # 12 samples
        
        # Check that samples are in valid range
        for sample in decoded.eeg['ch0']:
            self.assertGreaterEqual(sample, -1000)  # Min μV
            self.assertLessEqual(sample, 1000)      # Max μV
    
    def test_imu_packet_decoding(self):
        """Test IMU packet decoding"""
        # Create a mock IMU packet (0xF4 type)
        imu_packet = bytes([0xF4, 0x00, 0x00, 0x00] + 
                          [0x00, 0x64, 0x00, 0xC8, 0x01, 0x2C,  # Accel
                           0x00, 0x32, 0x00, 0x64, 0x00, 0x96])  # Gyro
        
        decoded = self.decoder.decode(imu_packet)
        
        self.assertEqual(decoded.packet_type, 'IMU')
        self.assertIsNotNone(decoded.imu)
        self.assertIn('accel', decoded.imu)
        self.assertIn('gyro', decoded.imu)
        self.assertEqual(len(decoded.imu['accel']), 3)
        self.assertEqual(len(decoded.imu['gyro']), 3)
    
    def test_callback_system(self):
        """Test callback registration and triggering"""
        eeg_called = False
        packet_data = None
        
        def on_eeg(data: DecodedData):
            nonlocal eeg_called, packet_data
            eeg_called = True
            packet_data = data
        
        self.decoder.register_callback('eeg', on_eeg)
        
        # Decode an EEG packet
        eeg_packet = bytes([0xDF, 0x00, 0x00, 0x00] + [0x80, 0x08] * 9)
        self.decoder.decode(eeg_packet)
        
        self.assertTrue(eeg_called)
        self.assertIsNotNone(packet_data)
        self.assertIsNotNone(packet_data.eeg)
    
    def test_statistics_tracking(self):
        """Test statistics tracking"""
        # Reset stats
        self.decoder.reset_stats()
        
        # Decode some packets
        eeg_packet = bytes([0xDF, 0x00, 0x00, 0x00] + [0x80, 0x08] * 9)
        imu_packet = bytes([0xF4, 0x00, 0x00, 0x00] + [0x00] * 12)
        
        self.decoder.decode(eeg_packet)
        self.decoder.decode(imu_packet)
        
        stats = self.decoder.get_stats()
        
        self.assertEqual(stats['packets_decoded'], 2)
        self.assertGreater(stats['eeg_samples'], 0)
        self.assertEqual(stats['decode_errors'], 0)
    
    def test_ppg_heart_rate_extraction(self):
        """Test PPG processing for heart rate"""
        # This would need more complex PPG data simulation
        # For now, test that PPG buffer management works
        
        # Create a packet with PPG-like data
        ppg_packet = bytes([0xDF, 0x00, 0x00, 0x00] + 
                          [0x00] * 4 +  # Skip to PPG section
                          [0x50, 0x00] * 10)  # High values typical of PPG
        
        decoded = self.decoder.decode(ppg_packet)
        
        # PPG processing should not crash
        self.assertIsNotNone(decoded)
    
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
        # Some errors may have been recorded
        self.assertGreaterEqual(stats['packets_decoded'], 3)

class TestDecodedData(unittest.TestCase):
    """Test DecodedData dataclass"""
    
    def test_decoded_data_creation(self):
        """Test creating DecodedData objects"""
        data = DecodedData(
            timestamp=datetime.datetime.now(),
            packet_type='TEST',
            eeg={'ch0': [1, 2, 3]},
            ppg={'samples': [100, 200]},
            imu={'accel': [0, 0, 1]},
            heart_rate=72.5,
            battery=85,
            raw_bytes=b'\x00\x01\x02'
        )
        
        self.assertEqual(data.packet_type, 'TEST')
        self.assertEqual(len(data.eeg['ch0']), 3)
        self.assertEqual(data.heart_rate, 72.5)
        self.assertEqual(data.battery, 85)

if __name__ == '__main__':
    unittest.main()