"""
Integrated parser for Muse S sleep monitoring data
Extracts EEG, IMU, PPG, and fNIRS from multiplexed stream

Uses TAG-based subpacket parsing per the Athena protocol.
The sleep presets (p1034/p1035) multiplex all sensor data into a single stream.
"""

import csv
import numpy as np
from typing import List, Dict, Optional
from dataclasses import dataclass, field
import datetime
from muse_ppg_heart_rate import PPGHeartRateExtractor
from muse_fnirs_processor import FNIRSProcessor
import muse_athena_protocol as proto

@dataclass
class IntegratedSensorData:
    """Container for all sensor modalities"""
    timestamp: datetime.datetime
    packet_num: int

    # EEG data (microvolts)
    eeg_channels: Dict[str, List[float]] = field(default_factory=dict)

    # IMU data
    accelerometer: Optional[List[List[float]]] = None  # (n_samples, 3)
    gyroscope: Optional[List[List[float]]] = None       # (n_samples, 3)

    # Optics/PPG data (normalized)
    ppg_channels: Dict[str, List[float]] = field(default_factory=dict)

    # Derived metrics
    heart_rate: Optional[float] = None
    hbo2: Optional[float] = None   # Oxygenated hemoglobin
    hbr: Optional[float] = None    # Deoxygenated hemoglobin
    tsi: Optional[float] = None    # Tissue saturation index

class MuseIntegratedParser:
    """Parse multiplexed Muse S sleep data with all modalities.

    Uses TAG-based subpacket parsing with correct bit-unpacking.
    """

    def __init__(self):
        # PPG/Heart rate processor
        self.ppg_extractor = PPGHeartRateExtractor(sample_rate=64)
        self.ppg_buffer = []

        # fNIRS processor
        self.fnirs_processor = FNIRSProcessor(sample_rate=64)

        # Statistics
        self.total_packets = 0
        self.eeg_packets = 0
        self.imu_packets = 0
        self.ppg_packets = 0

        # Results storage
        self.parsed_data = []

    def parse_csv_file(self, csv_path: str) -> List[IntegratedSensorData]:
        """Parse CSV file containing hex data dumps"""
        print(f"Parsing integrated sensor data from: {csv_path}")

        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)

            for row in reader:
                timestamp = datetime.datetime.fromisoformat(row['timestamp'])
                packet_num = int(row['packet_num'])
                hex_data = row['hex_data']

                data = bytes.fromhex(hex_data)
                sensor_data = self.parse_packet(data, timestamp, packet_num)
                if sensor_data:
                    self.parsed_data.append(sensor_data)

        self.process_buffered_data()

        print(f"\nParsing complete:")
        print(f"  Total packets: {self.total_packets}")
        print(f"  EEG packets: {self.eeg_packets}")
        print(f"  IMU packets: {self.imu_packets}")
        print(f"  PPG packets: {self.ppg_packets}")

        return self.parsed_data

    def parse_packet(self, data: bytes, timestamp: datetime.datetime,
                     packet_num: int) -> Optional[IntegratedSensorData]:
        """Parse a single multiplexed packet using TAG-based structure."""
        if len(data) < proto.HEADER_SIZE + 1:
            return None

        self.total_packets += 1
        sensor_data = IntegratedSensorData(timestamp=timestamp, packet_num=packet_num)

        parsed = proto.parse_payload(data)

        # EEG
        for subpacket in parsed["EEG"]:
            arr = subpacket["data"]
            n_channels = subpacket["n_channels"]
            names = proto.EEG_CHANNELS_4 if n_channels == 4 else proto.EEG_CHANNELS_8
            for ch_idx in range(n_channels):
                ch_name = names[ch_idx] if ch_idx < len(names) else f"ch{ch_idx}"
                sensor_data.eeg_channels[ch_name] = arr[:, ch_idx].tolist()
            self.eeg_packets += 1

        # IMU
        for subpacket in parsed["ACCGYRO"]:
            arr = subpacket["data"]  # (3, 6)
            sensor_data.accelerometer = arr[:, 0:3].tolist()
            sensor_data.gyroscope = arr[:, 3:6].tolist()
            self.imu_packets += 1

        # Optics/PPG
        for subpacket in parsed["OPTICS"]:
            arr = subpacket["data"]
            n_channels = subpacket["n_channels"]
            if n_channels == 8:
                names = proto.OPTICS_CHANNELS_8
            else:
                names = [f"opt{i}" for i in range(n_channels)]
            for ch_idx in range(n_channels):
                ch_name = names[ch_idx] if ch_idx < len(names) else f"opt{ch_idx}"
                sensor_data.ppg_channels[ch_name] = arr[:, ch_idx].tolist()

            # Buffer IR channel for heart rate
            ir_samples = arr[:, 0].tolist()
            self.ppg_buffer.extend(ir_samples)

            # Feed fNIRS processor if we have the right channels
            if n_channels >= 4:
                # Outer NIR (850nm) and IR (735nm) channels
                lo_nir = arr[:, 0].tolist()
                lo_ir = arr[:, 2].tolist() if n_channels > 2 else []
                self.fnirs_processor.add_samples(lo_nir, lo_ir, [])

            self.ppg_packets += 1

        return sensor_data

    def process_buffered_data(self):
        """Process buffered PPG data for heart rate and fNIRS"""
        print("\nProcessing buffered sensor data...")

        if len(self.ppg_buffer) >= 320:  # 5 seconds at 64Hz
            ir_signal = np.array(self.ppg_buffer[-640:])
            result = self.ppg_extractor.extract_heart_rate(ir_signal)

            if result.heart_rate_bpm > 0:
                print(f"  Heart Rate: {result.heart_rate_bpm:.0f} BPM")
                print(f"  Confidence: {result.confidence:.0%}")
                print(f"  Signal Quality: {result.signal_quality}")

        if self.fnirs_processor.calibrate_baseline():
            fnirs = self.fnirs_processor.extract_fnirs()
            if fnirs:
                print(f"\nfNIRS Measurements:")
                print(f"  HbO2: {fnirs.hbo2:.1f} uM")
                print(f"  HbR: {fnirs.hbr:.1f} uM")
                print(f"  TSI: {fnirs.tsi:.1f}%")

                cerebral = self.fnirs_processor.get_cerebral_oxygenation()
                if cerebral:
                    print(f"\nCerebral Oxygenation:")
                    print(f"  ScO2: {cerebral['ScO2']:.1f}%")
                    print(f"  rSO2: {cerebral['rSO2']:.1f}%")

    def get_summary(self) -> Dict:
        """Get summary of parsed data"""
        summary = {
            'total_packets': self.total_packets,
            'eeg_packets': self.eeg_packets,
            'imu_packets': self.imu_packets,
            'ppg_packets': self.ppg_packets,
            'has_heart_rate': len(self.ppg_buffer) > 0,
            'has_fnirs': self.fnirs_processor.calibrated
        }

        if self.parsed_data:
            all_channels = set()
            for data in self.parsed_data:
                all_channels.update(data.eeg_channels.keys())
            summary['eeg_channels'] = list(all_channels)

        return summary

def analyze_sleep_session(csv_path: str):
    """Analyze a complete sleep monitoring session"""
    print("=" * 60)
    print("Muse S Integrated Sleep Data Analysis")
    print("=" * 60)

    parser = MuseIntegratedParser()
    data = parser.parse_csv_file(csv_path)

    summary = parser.get_summary()

    print("\n" + "=" * 60)
    print("SESSION SUMMARY")
    print("=" * 60)

    print(f"\nSensor Modalities Detected:")
    print(f"  EEG: {'Yes' if summary['eeg_packets'] > 0 else 'No'} ({summary['eeg_packets']} packets)")
    print(f"  IMU: {'Yes' if summary['imu_packets'] > 0 else 'No'} ({summary['imu_packets']} packets)")
    print(f"  PPG: {'Yes' if summary['ppg_packets'] > 0 else 'No'} ({summary['ppg_packets']} packets)")

    if summary.get('eeg_channels'):
        print(f"\nEEG Channels: {', '.join(summary['eeg_channels'])}")

    if summary['has_heart_rate']:
        print(f"\nHeart Rate: Data available for extraction")

    if summary['has_fnirs']:
        print(f"\nfNIRS: Cerebral oxygenation data available")

    print("\n" + "=" * 60)

    return parser

if __name__ == "__main__":
    import glob
    import os

    csv_files = glob.glob("sleep_data/*.csv")

    if csv_files:
        latest_file = max(csv_files, key=os.path.getctime)
        print(f"Analyzing: {latest_file}\n")
        parser = analyze_sleep_session(latest_file)
    else:
        print("No sleep session files found in sleep_data/")
