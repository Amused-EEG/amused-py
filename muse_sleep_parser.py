"""
Muse S Sleep Data Parser
Parses CSV files created by muse_sleep_client.py to extract actual sensor values.

Based on Muse S protocol analysis:
- EEG: 12 samples of 12-bit data per packet (256 Hz)
- IMU: 3-axis accelerometer + gyroscope (52 Hz)
- Timestamps and packet counters for synchronization
"""

import csv
import struct
import json
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
import os
import matplotlib.pyplot as plt
from collections import defaultdict

@dataclass
class EEGData:
    """Container for EEG samples"""
    timestamp: datetime
    packet_num: int
    channel: str
    samples: List[float]  # in microvolts
    sample_rate: int = 256

@dataclass
class IMUData:
    """Container for IMU samples"""
    timestamp: datetime
    packet_num: int
    accel: List[Tuple[float, float, float]]  # (x, y, z) in G
    gyro: List[Tuple[float, float, float]]   # (x, y, z) in dps
    sample_rate: int = 52

@dataclass
class ParsedSession:
    """Complete parsed session data"""
    session_start: datetime
    session_end: datetime
    duration_seconds: float
    total_packets: int
    eeg_data: Dict[str, List[EEGData]] = field(default_factory=dict)
    imu_data: List[IMUData] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

class MuseSleepParser:
    """Parser for Muse S sleep data CSV files"""
    
    # Known packet markers from analysis
    MARKER_FCFF = b'\xfc\xff'
    MARKER_FFFF = b'\xff\xff\xff\xff'
    
    # Scaling factors
    EEG_SCALE_FACTOR = 0.48828125  # 12-bit to microvolts
    ACCEL_SCALE = 2.0 / 32768.0    # ±2G range
    GYRO_SCALE = 250.0 / 32768.0   # ±250 dps range
    
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.parsed_packets = 0
        self.errors = []
        
    def parse_csv_file(self, csv_path: str) -> ParsedSession:
        """Parse a complete CSV file from sleep session"""
        
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        
        if self.verbose:
            print(f"Parsing: {csv_path}")
        
        session = ParsedSession(
            session_start=None,
            session_end=None,
            duration_seconds=0,
            total_packets=0
        )
        
        # Initialize EEG channels
        eeg_channels = ['TP9', 'AF7', 'AF8', 'TP10', 'AUX']
        for channel in eeg_channels:
            session.eeg_data[channel] = []
        
        # Read and parse CSV
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            
            for row_num, row in enumerate(reader):
                try:
                    # Parse timestamp
                    timestamp = datetime.fromisoformat(row['timestamp'])
                    if session.session_start is None:
                        session.session_start = timestamp
                    session.session_end = timestamp
                    
                    # Parse packet
                    packet_num = int(row['packet_num'])
                    packet_size = int(row['size'])
                    hex_data = row['hex_data']
                    
                    # Convert hex to bytes
                    data = bytes.fromhex(hex_data)
                    
                    # Parse the packet based on size and content
                    self.parse_packet(data, timestamp, packet_num, session)
                    
                    session.total_packets += 1
                    
                    # Progress update
                    if (row_num + 1) % 100 == 0 and self.verbose:
                        print(f"  Processed {row_num + 1} packets...")
                        
                except Exception as e:
                    error_msg = f"Error parsing row {row_num}: {e}"
                    session.errors.append(error_msg)
                    if self.verbose:
                        print(f"  ⚠️ {error_msg}")
        
        # Calculate duration
        if session.session_start and session.session_end:
            session.duration_seconds = (session.session_end - session.session_start).total_seconds()
        
        # Summary
        if self.verbose:
            self.print_summary(session)
        
        return session
    
    def parse_packet(self, data: bytes, timestamp: datetime, packet_num: int, session: ParsedSession):
        """Parse individual packet based on its structure"""
        
        if len(data) < 20:
            return  # Too small to be valid sensor data
        
        # Look for data segments separated by markers
        if self.MARKER_FCFF in data:
            # This is a multiplexed packet with multiple data types
            segments = data.split(self.MARKER_FCFF)
            
            for segment in segments:
                if len(segment) >= 4:
                    self.parse_segment(segment, timestamp, packet_num, session)
        else:
            # Try to parse as a single data type
            self.parse_segment(data, timestamp, packet_num, session)
    
    def parse_segment(self, segment: bytes, timestamp: datetime, packet_num: int, session: ParsedSession):
        """Parse individual data segment"""
        
        # Try different parsing strategies based on segment patterns
        
        # Check for EEG pattern (starts with counter bytes)
        if len(segment) >= 20:
            try:
                # First 2 bytes might be packet counter
                if segment[0] < 0x10 and segment[1] < 0x10:
                    # Likely EEG data with channel indicator
                    channel_id = segment[0]
                    self.parse_eeg_data(segment[2:], timestamp, packet_num, channel_id, session)
                else:
                    # Try standard EEG format
                    self.parse_standard_eeg(segment, timestamp, packet_num, session)
            except:
                pass
        
        # Check for IMU pattern
        if len(segment) in [18, 20, 36]:
            try:
                self.parse_imu_data(segment, timestamp, packet_num, session)
            except:
                pass
    
    def parse_standard_eeg(self, data: bytes, timestamp: datetime, packet_num: int, session: ParsedSession):
        """Parse standard EEG packet format (20 bytes)"""
        
        if len(data) < 20:
            return
        
        try:
            # Standard format: [counter:2][samples:18]
            counter = struct.unpack('>H', data[0:2])[0]
            
            # Extract 12 samples from 18 bytes
            samples = self.unpack_eeg_samples(data[2:20])
            
            if samples and len(samples) == 12:
                # Add to first available channel (TP9 by default)
                eeg_data = EEGData(
                    timestamp=timestamp,
                    packet_num=packet_num,
                    channel='TP9',
                    samples=samples
                )
                session.eeg_data['TP9'].append(eeg_data)
                self.parsed_packets += 1
                
        except Exception as e:
            pass
    
    def parse_eeg_data(self, data: bytes, timestamp: datetime, packet_num: int, 
                      channel_id: int, session: ParsedSession):
        """Parse EEG data with channel identification"""
        
        # Map channel IDs to names
        channel_map = {
            0: 'TP9',
            1: 'AF7', 
            2: 'AF8',
            3: 'TP10',
            4: 'AUX'
        }
        
        channel = channel_map.get(channel_id, f'CH{channel_id}')
        
        try:
            samples = self.unpack_eeg_samples(data[:18])
            
            if samples:
                eeg_data = EEGData(
                    timestamp=timestamp,
                    packet_num=packet_num,
                    channel=channel,
                    samples=samples
                )
                
                if channel in session.eeg_data:
                    session.eeg_data[channel].append(eeg_data)
                else:
                    session.eeg_data[channel] = [eeg_data]
                    
                self.parsed_packets += 1
                
        except Exception as e:
            pass
    
    def unpack_eeg_samples(self, data: bytes) -> List[float]:
        """Unpack 12-bit EEG samples from 18 bytes"""
        
        if len(data) < 18:
            return []
        
        samples = []
        
        try:
            # 12 samples of 12-bit data packed in 18 bytes
            # 2 samples per 3 bytes
            for i in range(6):
                offset = i * 3
                if offset + 3 <= len(data):
                    three_bytes = data[offset:offset+3]
                    
                    # Extract two 12-bit samples
                    sample1 = (three_bytes[0] << 4) | (three_bytes[1] >> 4)
                    sample2 = ((three_bytes[1] & 0x0F) << 8) | three_bytes[2]
                    
                    # Convert to microvolts
                    uv1 = (sample1 - 2048) * self.EEG_SCALE_FACTOR
                    uv2 = (sample2 - 2048) * self.EEG_SCALE_FACTOR
                    
                    # Sanity check - EEG typically in ±500 µV range
                    if -1000 < uv1 < 1000:
                        samples.append(uv1)
                    if -1000 < uv2 < 1000:
                        samples.append(uv2)
                        
        except Exception as e:
            pass
        
        return samples
    
    def parse_imu_data(self, data: bytes, timestamp: datetime, packet_num: int, session: ParsedSession):
        """Parse IMU (accelerometer + gyroscope) data"""
        
        if len(data) < 12:
            return
        
        try:
            # IMU format: 3 samples of 6 values each (3 accel + 3 gyro)
            num_samples = len(data) // 12
            
            accel_samples = []
            gyro_samples = []
            
            for i in range(min(num_samples, 3)):
                offset = i * 12
                if offset + 12 <= len(data):
                    # Unpack 6 int16 values
                    values = struct.unpack('<6h', data[offset:offset+12])
                    
                    # First 3 are accelerometer
                    accel_x = values[0] * self.ACCEL_SCALE
                    accel_y = values[1] * self.ACCEL_SCALE
                    accel_z = values[2] * self.ACCEL_SCALE
                    
                    # Next 3 are gyroscope
                    gyro_x = values[3] * self.GYRO_SCALE
                    gyro_y = values[4] * self.GYRO_SCALE
                    gyro_z = values[5] * self.GYRO_SCALE
                    
                    # Sanity check
                    if abs(accel_x) < 5 and abs(gyro_x) < 500:
                        accel_samples.append((accel_x, accel_y, accel_z))
                        gyro_samples.append((gyro_x, gyro_y, gyro_z))
            
            if accel_samples:
                imu_data = IMUData(
                    timestamp=timestamp,
                    packet_num=packet_num,
                    accel=accel_samples,
                    gyro=gyro_samples
                )
                session.imu_data.append(imu_data)
                
        except Exception as e:
            pass
    
    def print_summary(self, session: ParsedSession):
        """Print session summary"""
        
        print("\n" + "=" * 60)
        print("📊 PARSING SUMMARY")
        print("=" * 60)
        
        print(f"Session Duration: {session.duration_seconds:.1f} seconds")
        print(f"Total Packets: {session.total_packets:,}")
        print(f"Parsed Packets: {self.parsed_packets:,}")
        
        print("\nEEG Data:")
        for channel, data in session.eeg_data.items():
            if data:
                total_samples = sum(len(d.samples) for d in data)
                print(f"  {channel}: {len(data)} packets, {total_samples:,} samples")
        
        print(f"\nIMU Data: {len(session.imu_data)} packets")
        
        if session.errors:
            print(f"\n⚠️ Errors: {len(session.errors)}")
    
    def export_to_numpy(self, session: ParsedSession, output_dir: str = "parsed_data"):
        """Export parsed data to numpy arrays"""
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Export EEG data
        for channel, data_list in session.eeg_data.items():
            if data_list:
                # Flatten all samples
                all_samples = []
                for data in data_list:
                    all_samples.extend(data.samples)
                
                if all_samples:
                    arr = np.array(all_samples)
                    filename = os.path.join(output_dir, f"eeg_{channel}.npy")
                    np.save(filename, arr)
                    print(f"  Saved {channel}: {arr.shape} samples to {filename}")
        
        # Export IMU data
        if session.imu_data:
            accel_data = []
            gyro_data = []
            
            for imu in session.imu_data:
                accel_data.extend(imu.accel)
                gyro_data.extend(imu.gyro)
            
            if accel_data:
                accel_arr = np.array(accel_data)
                np.save(os.path.join(output_dir, "accelerometer.npy"), accel_arr)
                print(f"  Saved Accelerometer: {accel_arr.shape}")
            
            if gyro_data:
                gyro_arr = np.array(gyro_data)
                np.save(os.path.join(output_dir, "gyroscope.npy"), gyro_arr)
                print(f"  Saved Gyroscope: {gyro_arr.shape}")
    
    def plot_eeg_samples(self, session: ParsedSession, channel: str = 'TP9', 
                         start_idx: int = 0, num_samples: int = 2560):
        """Plot EEG samples (10 seconds at 256 Hz)"""
        
        if channel not in session.eeg_data or not session.eeg_data[channel]:
            print(f"No data for channel {channel}")
            return
        
        # Collect samples
        samples = []
        for data in session.eeg_data[channel]:
            samples.extend(data.samples)
            if len(samples) >= start_idx + num_samples:
                break
        
        if len(samples) < start_idx + num_samples:
            num_samples = len(samples) - start_idx
        
        if num_samples <= 0:
            print("Not enough samples to plot")
            return
        
        # Create time axis (assuming 256 Hz)
        time_axis = np.arange(num_samples) / 256.0
        plot_samples = samples[start_idx:start_idx + num_samples]
        
        # Plot
        plt.figure(figsize=(12, 4))
        plt.plot(time_axis, plot_samples, 'b-', linewidth=0.5)
        plt.xlabel('Time (seconds)')
        plt.ylabel('Amplitude (µV)')
        plt.title(f'EEG Channel {channel} - {num_samples/256:.1f} seconds')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
    
    def calculate_statistics(self, session: ParsedSession) -> Dict[str, Any]:
        """Calculate statistics for the session"""
        
        stats = {
            'duration_seconds': session.duration_seconds,
            'total_packets': session.total_packets,
            'eeg_stats': {},
            'imu_stats': {}
        }
        
        # EEG statistics
        for channel, data_list in session.eeg_data.items():
            if data_list:
                all_samples = []
                for data in data_list:
                    all_samples.extend(data.samples)
                
                if all_samples:
                    arr = np.array(all_samples)
                    stats['eeg_stats'][channel] = {
                        'num_samples': len(all_samples),
                        'mean': float(np.mean(arr)),
                        'std': float(np.std(arr)),
                        'min': float(np.min(arr)),
                        'max': float(np.max(arr)),
                        'rms': float(np.sqrt(np.mean(arr**2)))
                    }
        
        # IMU statistics
        if session.imu_data:
            accel_data = []
            for imu in session.imu_data:
                accel_data.extend(imu.accel)
            
            if accel_data:
                accel_arr = np.array(accel_data)
                stats['imu_stats']['accelerometer'] = {
                    'num_samples': len(accel_data),
                    'mean_x': float(np.mean(accel_arr[:, 0])),
                    'mean_y': float(np.mean(accel_arr[:, 1])),
                    'mean_z': float(np.mean(accel_arr[:, 2])),
                    'movement_index': float(np.std(accel_arr))
                }
        
        return stats

def main():
    """Example usage"""
    
    print("=" * 60)
    print("Muse S Sleep Data Parser")
    print("=" * 60)
    
    # Example: Parse a sleep session CSV
    csv_file = "sleep_data/sleep_session_20240824_150000.csv"  # Update with actual file
    
    if not os.path.exists(csv_file):
        print(f"\n❌ File not found: {csv_file}")
        print("Please run muse_sleep_client.py first to generate data")
        return
    
    parser = MuseSleepParser(verbose=True)
    
    # Parse the CSV
    session = parser.parse_csv_file(csv_file)
    
    # Calculate statistics
    stats = parser.calculate_statistics(session)
    print("\n📈 Statistics:")
    print(json.dumps(stats, indent=2))
    
    # Export to numpy
    parser.export_to_numpy(session)
    
    # Plot sample EEG data
    if session.eeg_data.get('TP9'):
        print("\n📊 Plotting EEG samples...")
        parser.plot_eeg_samples(session, channel='TP9', num_samples=2560)

if __name__ == "__main__":
    main()