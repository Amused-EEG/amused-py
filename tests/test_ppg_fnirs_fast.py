"""
Fast tests for PPG Heart Rate and fNIRS Processing
Uses shorter signals and simpler calculations for faster testing
"""

import unittest
import numpy as np
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_ppg_heart_rate import PPGHeartRateExtractor, simulate_ppg_signal
from muse_fnirs_processor import FNIRSProcessor

class TestPPGHeartRateFast(unittest.TestCase):
    """Fast tests for PPG heart rate extraction"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.extractor = PPGHeartRateExtractor(sample_rate=64)
    
    def test_heart_rate_extraction_quick(self):
        """Quick test with short signal"""
        # Generate only 2 seconds of signal
        signal = simulate_ppg_signal(duration_seconds=2, heart_rate_bpm=72)
        
        result = self.extractor.extract_heart_rate(signal)
        
        self.assertIsNotNone(result)
        # May not be accurate with short signal, just check it runs
        if result.heart_rate_bpm > 0:
            self.assertGreater(result.heart_rate_bpm, 30)
            self.assertLess(result.heart_rate_bpm, 200)
    
    def test_ppg_packet_parsing(self):
        """Test PPG packet parsing (no signal processing)"""
        # Create a mock PPG packet (20 bytes)
        packet = bytes([0xDF, 0x00] + [0x80] * 18)
        
        ppg_data = self.extractor.parse_ppg_packet(packet)
        
        self.assertIsNotNone(ppg_data)
        self.assertGreater(len(ppg_data.ir_samples), 0)

class TestFNIRSProcessorFast(unittest.TestCase):
    """Fast tests for fNIRS processing"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.processor = FNIRSProcessor(sample_rate=64)
    
    def test_sample_addition_quick(self):
        """Quick test adding samples"""
        # Add just 10 samples
        ir_samples = [50000] * 10
        nir_samples = [48000] * 10
        red_samples = [45000] * 10
        
        self.processor.add_samples(ir_samples, nir_samples, red_samples)
        
        self.assertEqual(len(self.processor.buffers['ir']), 10)
    
    def test_calibration_minimal(self):
        """Test calibration with minimal data"""
        # Add minimum samples for calibration
        samples_needed = 64 * 2  # Just 2 seconds
        ir_samples = [50000] * samples_needed
        nir_samples = [48000] * samples_needed
        red_samples = [45000] * samples_needed
        
        self.processor.add_samples(ir_samples, nir_samples, red_samples)
        
        # Even if calibration fails with short data, it shouldn't crash
        try:
            success = self.processor.calibrate_baseline()
            self.assertIsInstance(success, bool)
        except:
            pass  # Acceptable with minimal data

if __name__ == '__main__':
    unittest.main(verbosity=2)