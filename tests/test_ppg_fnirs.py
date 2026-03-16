"""
Tests for PPG Heart Rate and fNIRS Processing
"""

import unittest
import numpy as np
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_ppg_heart_rate import PPGHeartRateExtractor, simulate_ppg_signal
from muse_fnirs_processor import FNIRSProcessor

class TestPPGHeartRate(unittest.TestCase):
    """Test PPG heart rate extraction"""

    def setUp(self):
        """Set up test fixtures"""
        self.extractor = PPGHeartRateExtractor(sample_rate=64)

    def test_heart_rate_extraction_normal(self):
        """Test heart rate extraction from normal signal"""
        signal = simulate_ppg_signal(duration_seconds=10, heart_rate_bpm=72)

        result = self.extractor.extract_heart_rate(signal)

        self.assertIsNotNone(result)
        self.assertGreater(result.heart_rate_bpm, 0)
        self.assertAlmostEqual(result.heart_rate_bpm, 72, delta=5)
        self.assertGreater(result.confidence, 0.8)
        self.assertEqual(result.signal_quality, 'Excellent')

    def test_heart_rate_extraction_various_rates(self):
        """Test extraction at different heart rates"""
        test_rates = [50, 60, 80, 100, 120]

        for true_rate in test_rates:
            signal = simulate_ppg_signal(duration_seconds=10, heart_rate_bpm=true_rate)
            result = self.extractor.extract_heart_rate(signal)

            self.assertIsNotNone(result)
            error = abs(result.heart_rate_bpm - true_rate) / true_rate
            self.assertLess(error, 0.1)

    def test_hrv_calculation(self):
        """Test HRV metrics calculation"""
        signal = simulate_ppg_signal(duration_seconds=30, heart_rate_bpm=70)
        result = self.extractor.extract_heart_rate(signal)

        self.assertIsNotNone(result.peak_times)
        self.assertGreater(len(result.peak_times), 10)

        if len(result.peak_times) > 2:
            hrv = self.extractor.calculate_hrv(result.peak_times)
            self.assertIsNotNone(hrv)
            self.assertIn('rmssd_ms', hrv)
            self.assertIn('pnn50', hrv)
            self.assertGreater(hrv['rmssd_ms'], 0)
            self.assertGreaterEqual(hrv['pnn50'], 0)
            self.assertLessEqual(hrv['pnn50'], 100)

    def test_noisy_signal_handling(self):
        """Test handling of noisy signals"""
        signal = simulate_ppg_signal(duration_seconds=10, heart_rate_bpm=75)
        noise = np.random.normal(0, 500, len(signal))
        noisy_signal = signal + noise

        result = self.extractor.extract_heart_rate(noisy_signal)

        self.assertIsNotNone(result)
        if result.heart_rate_bpm > 0:
            self.assertIn(result.signal_quality, ['Poor', 'Fair', 'Good', 'Excellent'])

    def test_short_signal_handling(self):
        """Test handling of short signals"""
        signal = simulate_ppg_signal(duration_seconds=1, heart_rate_bpm=70)
        result = self.extractor.extract_heart_rate(signal)

        self.assertIsNotNone(result)
        if result.heart_rate_bpm == 0:
            self.assertIn(result.signal_quality, ['Poor', 'Insufficient data'])

    def test_ppg_packet_parsing(self):
        """Test optics packet parsing with 20-bit LSB-first"""
        # 40 bytes of raw optics data (8-channel mode)
        data = bytes(40)
        ppg_data = self.extractor.parse_ppg_packet(data, n_channels=8)

        self.assertIsNotNone(ppg_data)
        self.assertEqual(len(ppg_data.channels), 8)

    def test_ppg_packet_4ch(self):
        """Test 4-channel optics packet parsing"""
        data = bytes(30)
        ppg_data = self.extractor.parse_ppg_packet(data, n_channels=4)

        self.assertIsNotNone(ppg_data)
        self.assertEqual(len(ppg_data.channels), 4)


class TestFNIRSProcessor(unittest.TestCase):
    """Test fNIRS blood oxygenation processing"""

    def setUp(self):
        """Set up test fixtures"""
        self.processor = FNIRSProcessor(sample_rate=64)

    def test_sample_addition(self):
        """Test adding samples to processor"""
        ir_samples = [50000 + i for i in range(100)]
        nir_samples = [48000 + i for i in range(100)]
        red_samples = [45000 + i for i in range(100)]

        self.processor.add_samples(ir_samples, nir_samples, red_samples)

        self.assertEqual(len(self.processor.buffers['ir']), 100)
        self.assertEqual(len(self.processor.buffers['nir']), 100)
        self.assertEqual(len(self.processor.buffers['red']), 100)

    def test_baseline_calibration(self):
        """Test baseline calibration"""
        samples_needed = 64 * 10
        ir_samples = [50000] * samples_needed
        nir_samples = [48000] * samples_needed
        red_samples = [45000] * samples_needed

        self.processor.add_samples(ir_samples, nir_samples, red_samples)

        success = self.processor.calibrate_baseline()

        self.assertTrue(success)
        self.assertTrue(self.processor.calibrated)
        self.assertIsNotNone(self.processor.baseline)
        self.assertIn('ir', self.processor.baseline)

    def test_fnirs_extraction(self):
        """Test fNIRS measurement extraction"""
        duration = 64 * 15
        ir_signal = simulate_ppg_signal(duration_seconds=15, heart_rate_bpm=70) * 1000 + 50000
        nir_signal = simulate_ppg_signal(duration_seconds=15, heart_rate_bpm=70) * 800 + 48000
        red_signal = simulate_ppg_signal(duration_seconds=15, heart_rate_bpm=70) * 1200 + 45000

        self.processor.add_samples(ir_signal, nir_signal, red_signal)
        self.processor.calibrate_baseline()

        fnirs = self.processor.extract_fnirs()

        self.assertIsNotNone(fnirs)
        self.assertGreater(fnirs.hbo2, 0)
        self.assertGreater(fnirs.hbr, 0)
        self.assertGreater(fnirs.tsi, 0)
        self.assertLessEqual(fnirs.tsi, 100)
        self.assertIn(fnirs.quality, ['Poor', 'Fair', 'Good', 'Excellent'])

    def test_cerebral_oxygenation(self):
        """Test cerebral oxygenation metrics"""
        samples = 64 * 15
        self.processor.add_samples(
            [50000] * samples,
            [48000] * samples,
            [45000] * samples
        )
        self.processor.calibrate_baseline()

        self.processor.add_samples(
            [50500] * samples,
            [48200] * samples,
            [45100] * samples
        )

        cerebral = self.processor.get_cerebral_oxygenation()

        self.assertIsNotNone(cerebral)
        self.assertIn('ScO2', cerebral)
        self.assertIn('rSO2', cerebral)
        self.assertIn('COx', cerebral)
        self.assertIn('quality', cerebral)

        self.assertGreater(cerebral['ScO2'], 0)
        self.assertLessEqual(cerebral['ScO2'], 100)

    def test_hypoxia_detection(self):
        """Test hypoxia detection"""
        samples = 64 * 10
        self.processor.add_samples(
            [50000] * samples,
            [48000] * samples,
            [45000] * samples
        )
        self.processor.calibrate_baseline()

        is_hypoxic = self.processor.detect_hypoxia(threshold=60)
        self.assertIn(type(is_hypoxic).__name__, ['bool', 'bool_'])

    def test_buffer_management(self):
        """Test buffer size management"""
        for _ in range(100):
            self.processor.add_samples([50000] * 64, [48000] * 64, [45000] * 64)

        max_samples = 64 * 30
        self.assertLessEqual(len(self.processor.buffers['ir']), max_samples)
        self.assertLessEqual(len(self.processor.buffers['nir']), max_samples)
        self.assertLessEqual(len(self.processor.buffers['red']), max_samples)

if __name__ == '__main__':
    unittest.main()
