"""
Integrated parser for Muse S sleep monitoring data
Extracts EEG, IMU, PPG, and fNIRS from multiplexed stream

The sleep presets (p1034/p1035) multiplex all sensor data into a single stream
"""

import csv
import struct
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import datetime
from muse_ppg_heart_rate import PPGHeartRateExtractor
from muse_fnirs_processor import FNIRSProcessor

@dataclass
class IntegratedSensorData:
    """Container for all sensor modalities"""
    timestamp: datetime.datetime
    packet_num: int
    
    # EEG data (microvolts)
    eeg_channels: Dict[str, List[float]] = field(default_factory=dict)
    
    # IMU data
    accelerometer: Optional[Tuple[float, float, float]] = None
    gyroscope: Optional[Tuple[float, float, float]] = None
    
    # PPG data (raw ADC values)
    ppg_ir: List[float] = field(default_factory=list)
    ppg_nir: List[float] = field(default_factory=list)
    ppg_red: List[float] = field(default_factory=list)
    
    # Derived metrics
    heart_rate: Optional[float] = None
    hbo2: Optional[float] = None  # Oxygenated hemoglobin
    hbr: Optional[float] = None   # Deoxygenated hemoglobin
    tsi: Optional[float] = None   # Tissue saturation index

class MuseIntegratedParser:
    """Parse multiplexed Muse S sleep data with all modalities"""
    
    def __init__(self):
        # EEG configuration
        self.EEG_SCALE_FACTOR = 1000.0 / 2048.0  # Convert to microvolts
        
        # PPG/Heart rate processor
        self.ppg_extractor = PPGHeartRateExtractor(sample_rate=64)
        self.ppg_buffer = {'ir': [], 'nir': [], 'red': []}
        
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
                
                # Convert hex to bytes
                data = bytes.fromhex(hex_data)
                
                # Parse packet
                sensor_data = self.parse_packet(data, timestamp, packet_num)
                if sensor_data:
                    self.parsed_data.append(sensor_data)
        
        # Final processing
        self.process_buffered_data()
        
        print(f"\nParsing complete:")
        print(f"  Total packets: {self.total_packets}")
        print(f"  EEG packets: {self.eeg_packets}")
        print(f"  IMU packets: {self.imu_packets}")
        print(f"  PPG packets: {self.ppg_packets}")
        
        return self.parsed_data
    
    def parse_packet(self, data: bytes, timestamp: datetime.datetime, packet_num: int) -> Optional[IntegratedSensorData]:
        """Parse a single multiplexed packet"""
        if len(data) < 4:
            return None
        
        self.total_packets += 1
        sensor_data = IntegratedSensorData(timestamp=timestamp, packet_num=packet_num)
        
        # Identify packet type by header pattern
        header = data[0:2]
        
        # Check for known packet markers
        if header[0] == 0xdf:  # Type 1 multiplexed packet
            self.parse_multiplexed_type1(data, sensor_data)
        elif header[0] == 0xf4:  # Type 2 multiplexed packet
            self.parse_multiplexed_type2(data, sensor_data)
        elif header[0] == 0xdb:  # Type 3 multiplexed packet
            self.parse_multiplexed_type3(data, sensor_data)
        elif header[0] == 0xd9:  # Type 4 multiplexed packet
            self.parse_multiplexed_type4(data, sensor_data)
        else:
            # Try generic parsing
            self.parse_generic_packet(data, sensor_data)
        
        return sensor_data
    
    def parse_multiplexed_type1(self, data: bytes, sensor_data: IntegratedSensorData):
        """Parse type 1 multiplexed packet (0xdf header)"""
        # These packets typically contain EEG + PPG data
        
        # Skip header (2 bytes) and counter (2 bytes)
        offset = 4
        
        # Look for data segments
        while offset < len(data) - 18:
            # Check for EEG pattern (18-byte segments)
            if self.is_eeg_segment(data[offset:offset+18]):
                samples = self.unpack_eeg_samples(data[offset:offset+18])
                sensor_data.eeg_channels[f'channel_{len(sensor_data.eeg_channels)}'] = samples
                self.eeg_packets += 1
                offset += 18
            # Check for PPG pattern (20-byte segments)
            elif offset + 20 <= len(data) and self.is_ppg_segment(data[offset:offset+20]):
                self.extract_ppg_samples(data[offset:offset+20], sensor_data)
                self.ppg_packets += 1
                offset += 20
            else:
                offset += 1
    
    def parse_multiplexed_type2(self, data: bytes, sensor_data: IntegratedSensorData):
        """Parse type 2 multiplexed packet (0xf4 header)"""
        # These packets often contain IMU data
        
        offset = 4
        
        # Look for IMU segments (9 bytes for accel, 9 for gyro)
        if len(data) >= offset + 18:
            try:
                # Accelerometer (3x 16-bit signed)
                ax = struct.unpack('>h', data[offset:offset+2])[0] / 100.0
                ay = struct.unpack('>h', data[offset+2:offset+4])[0] / 100.0
                az = struct.unpack('>h', data[offset+4:offset+6])[0] / 100.0
                
                # Gyroscope (3x 16-bit signed)
                gx = struct.unpack('>h', data[offset+6:offset+8])[0] / 100.0
                gy = struct.unpack('>h', data[offset+8:offset+10])[0] / 100.0
                gz = struct.unpack('>h', data[offset+10:offset+12])[0] / 100.0
                
                sensor_data.accelerometer = (ax, ay, az)
                sensor_data.gyroscope = (gx, gy, gz)
                self.imu_packets += 1
            except:
                pass
    
    def parse_multiplexed_type3(self, data: bytes, sensor_data: IntegratedSensorData):
        """Parse type 3 multiplexed packet (0xdb header)"""
        # Mixed sensor data
        self.parse_generic_packet(data[4:], sensor_data)
    
    def parse_multiplexed_type4(self, data: bytes, sensor_data: IntegratedSensorData):
        """Parse type 4 multiplexed packet (0xd9 header)"""
        # Mixed sensor data
        self.parse_generic_packet(data[4:], sensor_data)
    
    def parse_generic_packet(self, data: bytes, sensor_data: IntegratedSensorData):
        """Generic parsing for unknown packet types"""
        offset = 0
        
        # Scan for known patterns
        while offset < len(data) - 10:
            # Look for EEG segments
            if offset + 18 <= len(data) and self.is_eeg_segment(data[offset:offset+18]):
                samples = self.unpack_eeg_samples(data[offset:offset+18])
                sensor_data.eeg_channels[f'channel_{len(sensor_data.eeg_channels)}'] = samples
                self.eeg_packets += 1
                offset += 18
            
            # Look for PPG segments
            elif offset + 20 <= len(data) and self.is_ppg_segment(data[offset:offset+20]):
                self.extract_ppg_samples(data[offset:offset+20], sensor_data)
                self.ppg_packets += 1
                offset += 20
            
            else:
                offset += 1
    
    def is_eeg_segment(self, segment: bytes) -> bool:
        """Check if segment looks like EEG data"""
        if len(segment) != 18:
            return False
        
        # EEG values should be in reasonable range
        # Check first sample
        try:
            sample = (segment[0] << 4) | (segment[1] >> 4)
            # Should be around 2048 (midpoint) +/- 1000
            return 1000 < sample < 3000
        except:
            return False
    
    def is_ppg_segment(self, segment: bytes) -> bool:
        """Check if segment looks like PPG data"""
        if len(segment) != 20:
            return False
        
        # PPG typically has higher values and different pattern
        try:
            # Check if values are in PPG range (higher than EEG)
            first_val = struct.unpack('>H', segment[0:2])[0]
            return first_val > 10000  # PPG ADC values are typically high
        except:
            return False
    
    def unpack_eeg_samples(self, data: bytes) -> List[float]:
        """Unpack 12 EEG samples from 18 bytes"""
        samples = []
        
        for i in range(6):
            offset = i * 3
            three_bytes = data[offset:offset+3]
            
            # Two 12-bit samples packed in 3 bytes
            sample1 = (three_bytes[0] << 4) | (three_bytes[1] >> 4)
            sample2 = ((three_bytes[1] & 0x0F) << 8) | three_bytes[2]
            
            # Convert to microvolts
            uv1 = (sample1 - 2048) * self.EEG_SCALE_FACTOR
            uv2 = (sample2 - 2048) * self.EEG_SCALE_FACTOR
            
            samples.extend([uv1, uv2])
        
        return samples
    
    def extract_ppg_samples(self, segment: bytes, sensor_data: IntegratedSensorData):
        """Extract PPG samples from segment"""
        # PPG data: 7 samples of 20-bit data in 20 bytes
        # Format: 3 channels interleaved (IR, NIR, Red)
        
        try:
            # Simplified extraction - actual format may vary
            for i in range(0, min(18, len(segment)), 6):
                if i + 2 <= len(segment):
                    # Extract as 16-bit values for simplicity
                    ir_val = struct.unpack('>H', segment[i:i+2])[0]
                    sensor_data.ppg_ir.append(ir_val)
                    
                    if i + 4 <= len(segment):
                        nir_val = struct.unpack('>H', segment[i+2:i+4])[0]
                        sensor_data.ppg_nir.append(nir_val)
                    
                    if i + 6 <= len(segment):
                        red_val = struct.unpack('>H', segment[i+4:i+6])[0]
                        sensor_data.ppg_red.append(red_val)
            
            # Add to buffers for processing
            if sensor_data.ppg_ir:
                self.ppg_buffer['ir'].extend(sensor_data.ppg_ir)
                self.ppg_buffer['nir'].extend(sensor_data.ppg_nir)
                self.ppg_buffer['red'].extend(sensor_data.ppg_red)
                
                # Also add to fNIRS processor
                self.fnirs_processor.add_samples(
                    sensor_data.ppg_ir,
                    sensor_data.ppg_nir,
                    sensor_data.ppg_red
                )
        except:
            pass
    
    def process_buffered_data(self):
        """Process buffered PPG data for heart rate and fNIRS"""
        print("\nProcessing buffered sensor data...")
        
        # Extract heart rate if we have enough PPG data
        if len(self.ppg_buffer['ir']) >= 320:  # 5 seconds at 64Hz
            ir_signal = np.array(self.ppg_buffer['ir'][-640:])
            result = self.ppg_extractor.extract_heart_rate(ir_signal)
            
            if result.heart_rate_bpm > 0:
                print(f"  Heart Rate: {result.heart_rate_bpm:.0f} BPM")
                print(f"  Confidence: {result.confidence:.0%}")
                print(f"  Signal Quality: {result.signal_quality}")
        
        # Extract fNIRS measurements
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
            'has_heart_rate': len(self.ppg_buffer['ir']) > 0,
            'has_fnirs': self.fnirs_processor.calibrated
        }
        
        # EEG channels found
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
    
    # Find most recent sleep session
    csv_files = glob.glob("sleep_data/*.csv")
    
    if csv_files:
        latest_file = max(csv_files, key=os.path.getctime)
        print(f"Analyzing: {latest_file}\n")
        
        parser = analyze_sleep_session(latest_file)
        
        print("\nThe Muse S sleep monitoring captures:")
        print("1. EEG brain waves (multiple channels)")
        print("2. IMU motion data (accelerometer + gyroscope)")
        print("3. PPG photoplethysmography (3 wavelengths)")
        print("4. fNIRS blood oxygenation (derived from PPG)")
        print("5. Heart rate and HRV (from PPG)")
        print("\nAll multiplexed in a single data stream!")
    else:
        print("No sleep session files found in sleep_data/")