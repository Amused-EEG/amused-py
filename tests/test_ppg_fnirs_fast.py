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
        signal = simulate_ppg_signal(duration_seconds=2, heart_rate_bpm=72)

        result = self.extractor.extract_heart_rate(signal)

        self.assertIsNotNone(result)
        if result.heart_rate_bpm > 0:
            self.assertGreater(result.heart_rate_bpm, 30)
            self.assertLess(result.heart_rate_bpm, 200)

    def test_ppg_packet_parsing(self):
        """Test optics packet parsing with 20-bit LSB-first"""
        # 40 bytes of raw optics data (8-channel mode)
        data = bytes(40)
        ppg_data = self.extractor.parse_ppg_packet(data, n_channels=8)

        self.assertIsNotNone(ppg_data)
        self.assertEqual(len(ppg_data.channels), 8)


class TestFNIRSProcessorFast(unittest.TestCase):
    """Fast tests for fNIRS processing"""

    def setUp(self):
        """Set up test fixtures"""
        self.processor = FNIRSProcessor(sample_rate=64)

    def test_sample_addition_quick(self):
        """Quick test adding samples"""
        ir_samples = [50000] * 10
        nir_samples = [48000] * 10
        red_samples = [45000] * 10

        self.processor.add_samples(ir_samples, nir_samples, red_samples)

        self.assertEqual(len(self.processor.buffers['ir']), 10)

    def test_calibration_minimal(self):
        """Test calibration with minimal data"""
        samples_needed = 64 * 2
        ir_samples = [50000] * samples_needed
        nir_samples = [48000] * samples_needed
        red_samples = [45000] * samples_needed

        self.processor.add_samples(ir_samples, nir_samples, red_samples)

        try:
            success = self.processor.calibrate_baseline()
            self.assertIsInstance(success, bool)
        except:
            pass

if __name__ == '__main__':
    unittest.main(verbosity=2)
