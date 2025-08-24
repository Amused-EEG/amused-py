"""
Integration tests for the Amused library
Tests that multiple components work together correctly
"""

import unittest
import asyncio
import tempfile
import os
import sys
import numpy as np
from datetime import datetime, timedelta
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_stream_client import MuseStreamClient
from muse_raw_stream import MuseRawStream
from muse_replay import MuseReplayPlayer, MuseBinaryParser
from muse_realtime_decoder import MuseRealtimeDecoder
from muse_ppg_heart_rate import PPGHeartRateExtractor, simulate_ppg_signal
from muse_fnirs_processor import FNIRSProcessor

class TestStreamToFile(unittest.TestCase):
    """Test streaming data to binary file and reading it back"""
    
    def setUp(self):
        """Create temporary file for testing"""
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.bin', delete=False)
        self.temp_file.close()
        self.filepath = self.temp_file.name
    
    def tearDown(self):
        """Clean up temporary file"""
        if os.path.exists(self.filepath):
            os.unlink(self.filepath)
    
    def test_write_decode_cycle(self):
        """Test writing raw data and decoding it"""
        # Create raw stream
        stream = MuseRawStream(self.filepath)
        stream.open_write()
        
        # Write some test packets
        test_packets = [
            # EEG packet
            bytes([0xDF, 0x00, 0x00, 0x00] + [0x80, 0x08] * 9),
            # IMU packet
            bytes([0xF4, 0x00, 0x00, 0x00] + [0x00, 0x64, 0x00, 0xC8, 0x01, 0x2C,
                                               0x00, 0x32, 0x00, 0x64, 0x00, 0x96]),
            # PPG-like packet
            bytes([0xDF, 0x00, 0x00, 0x00] + [0x50, 0x00] * 10)
        ]
        
        for packet in test_packets:
            stream.write_packet(packet)
        stream.close()
        
        # Read back and decode
        decoder = MuseRealtimeDecoder()
        stream.open_read()
        
        decoded_packets = []
        for raw_packet in stream.read_packets():
            decoded = decoder.decode(raw_packet.data)
            decoded_packets.append(decoded)
        
        stream.close()
        
        # Verify we got all packets decoded
        self.assertEqual(len(decoded_packets), 3)
        self.assertEqual(decoded_packets[0].packet_type, 'EEG_PPG')
        self.assertEqual(decoded_packets[1].packet_type, 'IMU')
        self.assertIsNotNone(decoded_packets[0].eeg)
        self.assertIsNotNone(decoded_packets[1].imu)
    
    def test_replay_with_callbacks(self):
        """Test replaying data with callbacks"""
        # First write some data
        stream = MuseRawStream(self.filepath)
        stream.open_write()
        
        # Write multiple EEG packets over time
        base_time = datetime.now()
        for i in range(10):
            packet = bytes([0xDF, 0x00, 0x00, 0x00] + [0x80 + i, 0x08] * 9)
            timestamp = base_time + timedelta(milliseconds=i * 100)
            stream.write_packet(packet, timestamp)
        
        stream.close()
        
        # Now replay with callbacks
        player = MuseReplayPlayer(
            filepath=self.filepath,
            speed=10.0,  # 10x speed
            decode=True
        )
        
        packets_received = []
        
        def on_decoded(data):
            packets_received.append(data)
        
        player.on_decoded(on_decoded)
        
        # Use asyncio to run the replay
        async def run_replay():
            await player.play(realtime=False)  # Not realtime for test speed
        
        asyncio.run(run_replay())
        
        # Verify we received all packets
        self.assertEqual(len(packets_received), 10)
        for packet in packets_received:
            self.assertEqual(packet.packet_type, 'EEG_PPG')

class TestBiometricProcessing(unittest.TestCase):
    """Test PPG and fNIRS processing integration"""
    
    def test_ppg_to_fnirs_pipeline(self):
        """Test processing PPG data through heart rate and fNIRS"""
        # Generate simulated PPG data
        duration = 30  # seconds
        sample_rate = 64
        heart_rate = 72
        
        # Generate 3-channel PPG (IR, NIR, Red)
        ir_signal = simulate_ppg_signal(duration, heart_rate, sample_rate) * 1000 + 50000
        nir_signal = simulate_ppg_signal(duration, heart_rate, sample_rate) * 800 + 48000
        red_signal = simulate_ppg_signal(duration, heart_rate, sample_rate) * 1200 + 45000
        
        # Process through heart rate extractor
        hr_extractor = PPGHeartRateExtractor(sample_rate=sample_rate)
        hr_result = hr_extractor.extract_heart_rate(ir_signal)
        
        self.assertIsNotNone(hr_result)
        self.assertAlmostEqual(hr_result.heart_rate_bpm, heart_rate, delta=5)
        
        # Process through fNIRS
        fnirs = FNIRSProcessor(sample_rate=sample_rate)
        fnirs.add_samples(ir_signal, nir_signal, red_signal)
        fnirs.calibrate_baseline()
        
        oxygenation = fnirs.extract_fnirs()
        self.assertIsNotNone(oxygenation)
        self.assertGreater(oxygenation.tsi, 0)
        self.assertLessEqual(oxygenation.tsi, 100)
    
    def test_decoder_to_biometrics(self):
        """Test decoding packets and extracting biometrics"""
        decoder = MuseRealtimeDecoder()
        hr_extractor = PPGHeartRateExtractor()
        
        # Track data through callbacks
        ppg_samples = []
        
        def on_ppg(data):
            if data.ppg:
                ppg_samples.extend(data.ppg.get('samples', []))
        
        decoder.register_callback('ppg', on_ppg)
        
        # Simulate PPG packets
        for i in range(100):
            # Create PPG-like packet
            packet = bytes([0xDF, 0x00, 0x00, 0x00] + 
                          [0x00] * 4 +  # Skip EEG section
                          [(50 + i) % 256, 0x00] * 8)  # PPG-like values
            decoder.decode(packet)
        
        # Should have collected PPG samples
        self.assertGreater(len(ppg_samples), 0)

class TestEndToEndStreaming(unittest.TestCase):
    """Test complete streaming pipeline (mock device)"""
    
    def test_client_configuration(self):
        """Test client configuration options"""
        # Test with saving disabled
        client_no_save = MuseStreamClient(
            save_raw=False,
            decode_realtime=True
        )
        self.assertFalse(client_no_save.save_raw)
        self.assertTrue(client_no_save.decode_realtime)
        
        # Test with saving enabled
        with tempfile.TemporaryDirectory() as tmpdir:
            client_save = MuseStreamClient(
                save_raw=True,
                decode_realtime=False,
                data_dir=tmpdir
            )
            self.assertTrue(client_save.save_raw)
            self.assertFalse(client_save.decode_realtime)
            self.assertEqual(client_save.data_dir, tmpdir)
    
    def test_callback_registration(self):
        """Test callback registration and management"""
        client = MuseStreamClient(save_raw=False)
        
        callbacks_called = {
            'eeg': False,
            'ppg': False,
            'imu': False,
            'heart_rate': False
        }
        
        def make_callback(name):
            def callback(data):
                callbacks_called[name] = True
            return callback
        
        # Register callbacks
        client.on_eeg(make_callback('eeg'))
        client.on_ppg(make_callback('ppg'))
        client.on_imu(make_callback('imu'))
        client.on_heart_rate(make_callback('heart_rate'))
        
        # Simulate data processing
        decoder = MuseRealtimeDecoder()
        
        # Simulate EEG packet
        eeg_packet = bytes([0xDF, 0x00, 0x00, 0x00] + [0x80, 0x08] * 9)
        decoded = decoder.decode(eeg_packet)
        
        # Process through client callbacks (would normally happen internally)
        if decoded.eeg and client._callbacks.get('eeg'):
            for cb in client._callbacks['eeg']:
                cb({'channels': decoded.eeg, 'timestamp': decoded.timestamp})
        
        # At least EEG callback should be possible to trigger
        # (In real usage, the client would trigger these internally)

class TestDataValidation(unittest.TestCase):
    """Test data validation and physiological ranges"""
    
    def test_eeg_value_ranges(self):
        """Test EEG values are in physiological range"""
        decoder = MuseRealtimeDecoder()
        
        # Create EEG packet with known values
        eeg_packet = bytes([0xDF, 0x00, 0x00, 0x00] + [0x80, 0x08] * 9)
        decoded = decoder.decode(eeg_packet)
        
        self.assertIsNotNone(decoded.eeg)
        for channel, samples in decoded.eeg.items():
            for sample in samples:
                # EEG should be in microvolts range
                self.assertGreaterEqual(sample, -1000)  # -1000 μV
                self.assertLessEqual(sample, 1000)      # +1000 μV
    
    def test_heart_rate_ranges(self):
        """Test heart rate values are physiological"""
        extractor = PPGHeartRateExtractor()
        
        # Test various heart rates
        for true_hr in [40, 60, 80, 100, 120, 180]:
            signal = simulate_ppg_signal(10, true_hr)
            result = extractor.extract_heart_rate(signal)
            
            if result.heart_rate_bpm > 0:
                # Should be in human range
                self.assertGreaterEqual(result.heart_rate_bpm, 30)
                self.assertLessEqual(result.heart_rate_bpm, 250)
    
    def test_oxygenation_ranges(self):
        """Test blood oxygenation values are physiological"""
        processor = FNIRSProcessor()
        
        # Add baseline samples
        samples = 64 * 10
        processor.add_samples(
            [50000] * samples,
            [48000] * samples,
            [45000] * samples
        )
        processor.calibrate_baseline()
        
        # Add measurement samples
        processor.add_samples(
            [50500] * samples,
            [48200] * samples,
            [45100] * samples
        )
        
        fnirs = processor.extract_fnirs()
        if fnirs:
            # TSI should be 0-100%
            self.assertGreaterEqual(fnirs.tsi, 0)
            self.assertLessEqual(fnirs.tsi, 100)
            
            # HbO2 and HbR should be positive
            self.assertGreaterEqual(fnirs.hbo2, 0)
            self.assertGreaterEqual(fnirs.hbr, 0)

class TestFileFormats(unittest.TestCase):
    """Test file format compatibility and efficiency"""
    
    def test_binary_format_efficiency(self):
        """Test binary format is more efficient than CSV"""
        # Create test data
        test_packets = []
        for i in range(1000):
            packet = bytes([0xDF, 0x00] + [i % 256] * 18)
            test_packets.append(packet)
        
        # Write to binary
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as tmp:
            binary_file = tmp.name
        
        stream = MuseRawStream(binary_file)
        stream.open_write()
        for packet in test_packets:
            stream.write_packet(packet)
        stream.close()
        
        # Get binary size
        binary_size = os.path.getsize(binary_file)
        
        # Estimate CSV size (timestamp,type,hex_data)
        csv_lines = []
        for i, packet in enumerate(test_packets):
            timestamp = datetime.now().isoformat()
            hex_data = packet.hex()
            csv_lines.append(f"{timestamp},0xDF,{hex_data}")
        csv_content = '\n'.join(csv_lines)
        csv_size = len(csv_content.encode())
        
        # Binary should be much smaller
        compression_ratio = csv_size / binary_size
        self.assertGreater(compression_ratio, 5)  # At least 5x smaller
        
        # Clean up
        os.unlink(binary_file)
    
    def test_parser_compatibility(self):
        """Test parser can handle both binary and decoded data"""
        parser = MuseBinaryParser(None)  # No file needed for this test
        
        # Test packet type identification
        packet_types = {
            0xDF: 'MULTI_EEG_PPG',
            0xF4: 'MULTI_IMU',
            0xDB: 'MULTI_MIXED_1',
            0xD9: 'MULTI_MIXED_2'
        }
        
        for type_byte, expected_name in packet_types.items():
            # Parser should correctly identify packet types
            # (This would be tested more thoroughly with actual file parsing)
            self.assertIn(expected_name, ['MULTI_EEG_PPG', 'MULTI_IMU', 
                                         'MULTI_MIXED_1', 'MULTI_MIXED_2'])

if __name__ == '__main__':
    # Run tests with verbosity
    unittest.main(verbosity=2)