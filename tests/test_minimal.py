"""
Minimal smoke tests for Amused library
These tests verify basic functionality without heavy processing
"""

import unittest
import tempfile
import os
import sys
import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_raw_stream import MuseRawStream, RawPacket
from muse_realtime_decoder import MuseRealtimeDecoder, DecodedData

class TestCoreComponents(unittest.TestCase):
    """Test that core components can be imported and instantiated"""
    
    def test_imports(self):
        """Test all imports work"""
        # These should not raise ImportError
        from muse_stream_client import MuseStreamClient
        from muse_replay import MuseReplayPlayer, MuseBinaryParser
        from muse_ppg_heart_rate import PPGHeartRateExtractor
        from muse_fnirs_processor import FNIRSProcessor
        
        # Verify classes exist
        self.assertTrue(MuseStreamClient)
        self.assertTrue(MuseReplayPlayer)
        self.assertTrue(PPGHeartRateExtractor)
        self.assertTrue(FNIRSProcessor)
    
    def test_decoder_creation(self):
        """Test decoder can be created"""
        decoder = MuseRealtimeDecoder()
        self.assertIsNotNone(decoder)
        
        # Test simple decode
        packet = bytes([0xDF, 0x00, 0x00, 0x00] + [0x80] * 16)
        result = decoder.decode(packet)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, DecodedData)
    
    def test_raw_stream_basic(self):
        """Test raw stream basic operations"""
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as tmp:
            filepath = tmp.name
        
        try:
            # Write
            stream = MuseRawStream(filepath)
            stream.open_write()
            stream.write_packet(b'\xDF\x00\x01\x02')
            stream.close()
            
            # Read
            stream.open_read()
            packets = list(stream.read_packets())
            stream.close()
            
            self.assertEqual(len(packets), 1)
            self.assertEqual(packets[0].data, b'\xDF\x00\x01\x02')
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)
    
    def test_dataclass_creation(self):
        """Test data classes can be created"""
        # RawPacket
        packet = RawPacket(
            timestamp=datetime.datetime.now(),
            packet_num=1,
            packet_type=0xDF,
            data=b'\x00\x01'
        )
        self.assertEqual(packet.packet_num, 1)
        
        # DecodedData
        decoded = DecodedData(
            timestamp=datetime.datetime.now(),
            packet_type='TEST'
        )
        self.assertEqual(decoded.packet_type, 'TEST')

class TestPackageStructure(unittest.TestCase):
    """Test package can be imported properly"""
    
    def test_package_import(self):
        """Test main package import"""
        import amused
        
        # Test version
        self.assertTrue(hasattr(amused, '__version__'))
        
        # Test main classes are exposed
        self.assertTrue(hasattr(amused, 'MuseStreamClient'))
        self.assertTrue(hasattr(amused, 'PPGHeartRateExtractor'))
        self.assertTrue(hasattr(amused, 'FNIRSProcessor'))

if __name__ == '__main__':
    # Run with minimal verbosity for speed
    unittest.main(verbosity=1)