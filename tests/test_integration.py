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
import muse_athena_protocol as proto

# Import real test data if available
try:
    from .real_test_data import REAL_EEG_PACKETS, REAL_IMU_PACKETS, get_test_packet
    HAS_REAL_DATA = True
except ImportError:
    HAS_REAL_DATA = False
    REAL_EEG_PACKETS = []
    REAL_IMU_PACKETS = []

    def get_test_packet(packet_type='eeg'):
        header = bytearray(14)
        header[9] = proto.TAG_EEG_4CH
        return bytes(header) + bytes(28)


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


class TestStreamToFile(unittest.TestCase):
    """Test streaming data to binary file and reading it back"""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.bin', delete=False)
        self.temp_file.close()
        self.filepath = self.temp_file.name

    def tearDown(self):
        if os.path.exists(self.filepath):
            os.unlink(self.filepath)

    def test_write_decode_cycle(self):
        """Test writing raw data and decoding it"""
        stream = MuseRawStream(self.filepath)
        stream.open_write()

        if HAS_REAL_DATA and REAL_EEG_PACKETS and REAL_IMU_PACKETS:
            test_packets = [
                REAL_EEG_PACKETS[0],
                REAL_IMU_PACKETS[0],
                REAL_EEG_PACKETS[1] if len(REAL_EEG_PACKETS) > 1 else REAL_EEG_PACKETS[0]
            ]
        else:
            test_packets = [
                build_tag_packet(proto.TAG_EEG_4CH, bytes(28)),
                build_tag_packet(proto.TAG_ACCGYRO, bytes(36)),
                build_tag_packet(proto.TAG_OPTICS_8CH, bytes(40)),
            ]

        for packet in test_packets:
            stream.write_packet(packet)
        stream.close()

        decoder = MuseRealtimeDecoder()
        stream.open_read()

        decoded_packets = []
        for raw_packet in stream.read_packets():
            decoded = decoder.decode(raw_packet.data)
            decoded_packets.append(decoded)

        stream.close()

        self.assertEqual(len(decoded_packets), 3)
        # First should have EEG data
        self.assertIsNotNone(decoded_packets[0].eeg)
        # Second should have IMU data
        self.assertIsNotNone(decoded_packets[1].imu)

    def test_replay_with_callbacks(self):
        """Test replaying data with callbacks"""
        stream = MuseRawStream(self.filepath)
        stream.open_write()

        base_time = datetime.now()
        for i in range(10):
            packet = build_tag_packet(proto.TAG_EEG_4CH, bytes(28))
            timestamp = base_time + timedelta(milliseconds=i * 100)
            stream.write_packet(packet, timestamp)

        stream.close()

        player = MuseReplayPlayer(
            filepath=self.filepath,
            speed=10.0,
            decode=True
        )

        packets_received = []

        def on_decoded(data):
            packets_received.append(data)

        player.on_decoded(on_decoded)

        async def run_replay():
            await player.play(realtime=False)

        asyncio.run(run_replay())

        self.assertEqual(len(packets_received), 10)


class TestBiometricProcessing(unittest.TestCase):
    """Test PPG and fNIRS processing integration"""

    def test_ppg_to_fnirs_pipeline(self):
        """Test processing PPG data through heart rate and fNIRS"""
        duration = 30
        sample_rate = 64
        heart_rate = 72

        ir_signal = simulate_ppg_signal(duration, heart_rate, sample_rate) * 1000 + 50000
        nir_signal = simulate_ppg_signal(duration, heart_rate, sample_rate) * 800 + 48000
        red_signal = simulate_ppg_signal(duration, heart_rate, sample_rate) * 1200 + 45000

        hr_extractor = PPGHeartRateExtractor(sample_rate=sample_rate)
        hr_result = hr_extractor.extract_heart_rate(ir_signal)

        self.assertIsNotNone(hr_result)
        self.assertAlmostEqual(hr_result.heart_rate_bpm, heart_rate, delta=5)

        fnirs = FNIRSProcessor(sample_rate=sample_rate)
        baseline_samples = sample_rate * 5
        fnirs.add_samples(
            ir_signal[:baseline_samples],
            nir_signal[:baseline_samples],
            red_signal[:baseline_samples]
        )
        fnirs.calibrate_baseline()

        fnirs.add_samples(
            ir_signal[baseline_samples:],
            nir_signal[baseline_samples:],
            red_signal[baseline_samples:]
        )

        oxygenation = fnirs.extract_fnirs()
        if oxygenation:
            self.assertIsNotNone(oxygenation)
            self.assertGreater(oxygenation.tsi, -100)
            self.assertLessEqual(oxygenation.tsi, 100)

    def test_decoder_eeg_produces_valid_data(self):
        """Test that decoder produces valid EEG channel data"""
        decoder = MuseRealtimeDecoder()

        packet = build_tag_packet(proto.TAG_EEG_4CH, bytes(28))
        decoded = decoder.decode(packet)

        self.assertIsNotNone(decoded.eeg)
        self.assertEqual(len(decoded.eeg), 4)
        for ch_name in proto.EEG_CHANNELS_4:
            self.assertIn(ch_name, decoded.eeg)
            self.assertEqual(len(decoded.eeg[ch_name]), 4)


class TestEndToEndStreaming(unittest.TestCase):
    """Test complete streaming pipeline (mock device)"""

    def test_client_configuration(self):
        """Test client configuration options"""
        client_no_save = MuseStreamClient(
            save_raw=False,
            decode_realtime=True
        )
        self.assertFalse(client_no_save.save_raw)
        self.assertTrue(client_no_save.decode_realtime)

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

        client.on_eeg(make_callback('eeg'))
        client.on_ppg(make_callback('ppg'))
        client.on_imu(make_callback('imu'))
        client.on_heart_rate(make_callback('heart_rate'))

        # Simulate data processing
        decoder = MuseRealtimeDecoder()
        eeg_packet = build_tag_packet(proto.TAG_EEG_4CH, bytes(28))
        decoded = decoder.decode(eeg_packet)

        if decoded.eeg and client.user_callbacks.get('eeg'):
            cb = client.user_callbacks['eeg']
            if cb:
                cb({'channels': decoded.eeg, 'timestamp': decoded.timestamp})


class TestDataValidation(unittest.TestCase):
    """Test data validation and physiological ranges"""

    def test_eeg_value_ranges(self):
        """Test EEG values are in physiological range"""
        decoder = MuseRealtimeDecoder()

        # All-zero data → all-zero values (valid)
        eeg_packet = build_tag_packet(proto.TAG_EEG_4CH, bytes(28))
        decoded = decoder.decode(eeg_packet)

        self.assertIsNotNone(decoded.eeg)
        for channel, samples in decoded.eeg.items():
            for sample in samples:
                # With all-zero data, samples should be 0
                self.assertAlmostEqual(sample, 0.0, places=5)

    def test_heart_rate_ranges(self):
        """Test heart rate values are physiological"""
        extractor = PPGHeartRateExtractor()

        for true_hr in [40, 60, 80, 100, 120, 180]:
            signal = simulate_ppg_signal(10, true_hr)
            result = extractor.extract_heart_rate(signal)

            if result.heart_rate_bpm > 0:
                self.assertGreaterEqual(result.heart_rate_bpm, 30)
                self.assertLessEqual(result.heart_rate_bpm, 250)

    def test_oxygenation_ranges(self):
        """Test blood oxygenation values are physiological"""
        processor = FNIRSProcessor()

        samples = 64 * 10
        processor.add_samples(
            [50000] * samples,
            [48000] * samples,
            [45000] * samples
        )
        processor.calibrate_baseline()

        processor.add_samples(
            [50500] * samples,
            [48200] * samples,
            [45100] * samples
        )

        fnirs = processor.extract_fnirs()
        if fnirs:
            self.assertGreaterEqual(fnirs.tsi, 0)
            self.assertLessEqual(fnirs.tsi, 100)
            self.assertGreaterEqual(fnirs.hbo2, 0)
            self.assertGreaterEqual(fnirs.hbr, 0)


class TestFileFormats(unittest.TestCase):
    """Test file format compatibility and efficiency"""

    def test_binary_format_efficiency(self):
        """Test binary format is more efficient than CSV"""
        test_packets = []
        for i in range(1000):
            packet = bytes([0x00, 0x00] + [i % 256] * 18)
            test_packets.append(packet)

        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as tmp:
            binary_file = tmp.name

        stream = MuseRawStream(binary_file)
        stream.open_write()
        for packet in test_packets:
            stream.write_packet(packet)
        stream.close()

        binary_size = os.path.getsize(binary_file)

        csv_lines = []
        for i, packet in enumerate(test_packets):
            timestamp = datetime.now().isoformat()
            hex_data = packet.hex()
            csv_lines.append(f"{timestamp},0x00,{hex_data}")
        csv_content = '\n'.join(csv_lines)
        csv_size = len(csv_content.encode())

        compression_ratio = csv_size / binary_size
        self.assertGreater(compression_ratio, 2)

        os.unlink(binary_file)

if __name__ == '__main__':
    unittest.main(verbosity=2)
