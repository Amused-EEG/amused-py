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
        # Generate 10 seconds of 72 BPM signal
        signal = simulate_ppg_signal(duration_seconds=10, heart_rate_bpm=72)
        
        result = self.extractor.extract_heart_rate(signal)
        
        self.assertIsNotNone(result)
        self.assertGreater(result.heart_rate_bpm, 0)
        # Should be close to 72 BPM (within 5 BPM)
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
            # Should be within 10% of true rate
            error = abs(result.heart_rate_bpm - true_rate) / true_rate
            self.assertLess(error, 0.1)
    
    def test_hrv_calculation(self):
        """Test HRV metrics calculation"""
        signal = simulate_ppg_signal(duration_seconds=30, heart_rate_bpm=70)
        result = self.extractor.extract_heart_rate(signal)
        
        self.assertIsNotNone(result.hrv_rmssd)
        self.assertIsNotNone(result.hrv_pnn50)
        self.assertGreater(result.hrv_rmssd, 0)
        self.assertGreaterEqual(result.hrv_pnn50, 0)
        self.assertLessEqual(result.hrv_pnn50, 100)
    
    def test_noisy_signal_handling(self):
        """Test handling of noisy signals"""
        # Generate signal with noise
        signal = simulate_ppg_signal(duration_seconds=10, heart_rate_bpm=75)
        noise = np.random.normal(0, 500, len(signal))
        noisy_signal = signal + noise
        
        result = self.extractor.extract_heart_rate(noisy_signal)
        
        # Should still get a result, but quality might be lower
        self.assertIsNotNone(result)
        if result.heart_rate_bpm > 0:
            self.assertIn(result.signal_quality, ['Poor', 'Fair', 'Good', 'Excellent'])
    
    def test_short_signal_handling(self):
        """Test handling of short signals"""
        # Very short signal (1 second)
        signal = simulate_ppg_signal(duration_seconds=1, heart_rate_bpm=70)
        result = self.extractor.extract_heart_rate(signal)
        
        # Should handle gracefully
        self.assertIsNotNone(result)
        # Might not get valid HR from such short signal
        if result.heart_rate_bpm == 0:
            self.assertEqual(result.signal_quality, 'Poor')
    
    def test_ppg_packet_parsing(self):
        """Test PPG packet parsing"""
        # Create a mock PPG packet (20 bytes)
        packet = bytes([0xDF, 0x00] + [0x80] * 18)
        
        ppg_data = self.extractor.parse_ppg_packet(packet)
        
        self.assertIsNotNone(ppg_data)
        self.assertGreater(len(ppg_data.ir_samples), 0)
        self.assertEqual(len(ppg_data.ir_samples), len(ppg_data.red_samples))

class TestFNIRSProcessor(unittest.TestCase):
    """Test fNIRS blood oxygenation processing"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.processor = FNIRSProcessor(sample_rate=64)
    
    def test_sample_addition(self):
        """Test adding samples to processor"""
        # Generate test samples
        ir_samples = [50000 + i for i in range(100)]
        nir_samples = [48000 + i for i in range(100)]
        red_samples = [45000 + i for i in range(100)]
        
        self.processor.add_samples(ir_samples, nir_samples, red_samples)
        
        self.assertEqual(len(self.processor.buffers['ir']), 100)
        self.assertEqual(len(self.processor.buffers['nir']), 100)
        self.assertEqual(len(self.processor.buffers['red']), 100)
    
    def test_baseline_calibration(self):
        """Test baseline calibration"""
        # Add enough samples for calibration
        samples_needed = 64 * 10  # 10 seconds
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
        # Simulate normal oxygenation
        duration = 64 * 15  # 15 seconds
        ir_signal = simulate_ppg_signal(duration_seconds=15, heart_rate_bpm=70) * 1000 + 50000
        nir_signal = simulate_ppg_signal(duration_seconds=15, heart_rate_bpm=70) * 800 + 48000
        red_signal = simulate_ppg_signal(duration_seconds=15, heart_rate_bpm=70) * 1200 + 45000
        
        self.processor.add_samples(ir_signal, nir_signal, red_signal)
        
        # Calibrate
        self.processor.calibrate_baseline()
        
        # Extract fNIRS
        fnirs = self.processor.extract_fnirs()
        
        self.assertIsNotNone(fnirs)
        self.assertGreater(fnirs.hbo2, 0)  # Oxygenated hemoglobin
        self.assertGreater(fnirs.hbr, 0)   # Deoxygenated hemoglobin
        self.assertGreater(fnirs.tsi, 0)   # Tissue saturation
        self.assertLessEqual(fnirs.tsi, 100)
        self.assertIn(fnirs.quality, ['Poor', 'Fair', 'Good', 'Excellent'])
    
    def test_cerebral_oxygenation(self):
        """Test cerebral oxygenation metrics"""
        # Add samples and calibrate
        samples = 64 * 15
        self.processor.add_samples(
            [50000] * samples,
            [48000] * samples,
            [45000] * samples
        )
        self.processor.calibrate_baseline()
        
        # Add slightly different samples (simulating change)
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
        
        # Values should be in physiological range
        self.assertGreater(cerebral['ScO2'], 0)
        self.assertLessEqual(cerebral['ScO2'], 100)
    
    def test_hypoxia_detection(self):
        """Test hypoxia detection"""
        # Simulate normal oxygenation first
        samples = 64 * 10
        self.processor.add_samples(
            [50000] * samples,
            [48000] * samples,
            [45000] * samples
        )
        self.processor.calibrate_baseline()
        
        # Normal - should not detect hypoxia
        is_hypoxic = self.processor.detect_hypoxia(threshold=60)
        # May or may not detect depending on baseline
        self.assertIsInstance(is_hypoxic, bool)
    
    def test_buffer_management(self):
        """Test buffer size management"""
        # Add many samples
        for _ in range(100):
            self.processor.add_samples([50000] * 64, [48000] * 64, [45000] * 64)
        
        # Buffers should be limited in size
        max_samples = 64 * 30  # 30 seconds max
        self.assertLessEqual(len(self.processor.buffers['ir']), max_samples)
        self.assertLessEqual(len(self.processor.buffers['nir']), max_samples)
        self.assertLessEqual(len(self.processor.buffers['red']), max_samples)

if __name__ == '__main__':
    unittest.main()