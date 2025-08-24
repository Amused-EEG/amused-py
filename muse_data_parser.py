"""
Muse S Data Parser - Handles multiplexed sensor data format
Based on pcap analysis of actual device communication
"""

import struct
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
import numpy as np

@dataclass
class EEGSample:
    """Single EEG sample from one channel"""
    timestamp: float
    channel: str
    value_uv: float
    
@dataclass
class IMUSample:
    """IMU sample containing accelerometer and gyroscope data"""
    timestamp: float
    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float

class MuseDataParser:
    """Parser for Muse S multiplexed sensor data"""
    
    # Known packet markers from pcap analysis
    MARKER_FCFF = b'\xfc\xff'
    MARKER_FFFF = b'\xff\xff\xff\xff'
    
    # EEG scaling factor (12-bit to microvolts)
    EEG_SCALE_FACTOR = 0.48828125
    
    # IMU scaling factors
    ACCEL_SCALE = 2.0 / 32768.0  # ±2G range
    GYRO_SCALE = 250.0 / 32768.0  # ±250 dps range
    
    def __init__(self):
        self.packet_counter = 0
        self.last_timestamp = 0
        self.data_buffer = bytearray()
        
    def parse_packet(self, data: bytearray) -> Dict[str, Any]:
        """
        Parse a multiplexed data packet from handle 0x0018
        
        Based on pcap analysis, packets are 200-250 bytes and contain
        multiple sensor readings multiplexed together.
        """
        result = {
            'packet_num': self.packet_counter,
            'packet_size': len(data),
            'segments': [],
            'eeg_samples': [],
            'imu_samples': [],
            'unknown_data': []
        }
        
        self.packet_counter += 1
        
        # Look for known markers to segment the data
        if self.MARKER_FCFF in data:
            segments = self.split_by_marker(data, self.MARKER_FCFF)
            result['segments'] = segments
            
            # Process each segment
            for segment in segments:
                self.process_segment(segment, result)
        else:
            # No clear markers, try to parse as continuous stream
            self.process_continuous(data, result)
            
        return result
    
    def split_by_marker(self, data: bytearray, marker: bytes) -> List[bytearray]:
        """Split data by marker bytes"""
        segments = []
        parts = data.split(marker)
        
        for i, part in enumerate(parts):
            if len(part) > 0:
                # Keep marker with segment for context
                if i > 0:
                    part = marker + part
                segments.append(part)
                
        return segments
    
    def process_segment(self, segment: bytearray, result: Dict):
        """Process individual data segment"""
        if len(segment) < 4:
            return
            
        # Analyze segment structure
        segment_info = {
            'length': len(segment),
            'first_bytes': segment[:8].hex() if len(segment) >= 8 else segment.hex(),
            'type': 'unknown'
        }
        
        # Try to identify segment type based on patterns
        if len(segment) == 20:  # Standard BLE packet size
            segment_info['type'] = 'possible_standard_packet'
            self.try_parse_standard_packet(segment, result)
            
        elif len(segment) in [18, 19]:  # EEG data is often 18 bytes (12 samples)
            segment_info['type'] = 'possible_eeg'
            self.try_parse_eeg_segment(segment, result)
            
        elif self.looks_like_imu(segment):
            segment_info['type'] = 'possible_imu'
            self.try_parse_imu_segment(segment, result)
            
        result['segments'].append(segment_info)
    
    def process_continuous(self, data: bytearray, result: Dict):
        """Process data as continuous stream without clear markers"""
        # Look for patterns that might indicate data boundaries
        
        # Check for timestamp patterns (incrementing values)
        for i in range(0, len(data) - 4, 2):
            try:
                val = struct.unpack('<H', data[i:i+2])[0]
                if val > 0 and val < 65535:
                    # Could be a counter or timestamp
                    pass
            except:
                pass
                
        # Try to extract any clear numeric patterns
        self.extract_numeric_patterns(data, result)
    
    def try_parse_standard_packet(self, segment: bytearray, result: Dict):
        """Try to parse as standard Muse packet format"""
        if len(segment) < 20:
            return
            
        try:
            # Standard format: [counter:2][data:18]
            counter = struct.unpack('>H', segment[0:2])[0]
            
            # Check if this looks like EEG data (12 samples of 12-bit)
            if counter < 65535:  # Reasonable counter value
                samples = self.unpack_eeg_samples(segment[2:20])
                if samples:
                    for sample in samples:
                        result['eeg_samples'].append({
                            'counter': counter,
                            'value_uv': sample
                        })
        except Exception as e:
            pass
    
    def try_parse_eeg_segment(self, segment: bytearray, result: Dict):
        """Try to parse segment as EEG data"""
        try:
            samples = self.unpack_eeg_samples(segment)
            for sample in samples:
                result['eeg_samples'].append({
                    'value_uv': sample
                })
        except:
            pass
    
    def try_parse_imu_segment(self, segment: bytearray, result: Dict):
        """Try to parse segment as IMU data"""
        if len(segment) < 12:  # Need at least 6 int16 values
            return
            
        try:
            # Try to unpack as 3-axis accel + 3-axis gyro
            values = struct.unpack('<6h', segment[:12])
            
            # Apply scaling
            imu_sample = {
                'accel_x': values[0] * self.ACCEL_SCALE,
                'accel_y': values[1] * self.ACCEL_SCALE,
                'accel_z': values[2] * self.ACCEL_SCALE,
                'gyro_x': values[3] * self.GYRO_SCALE,
                'gyro_y': values[4] * self.GYRO_SCALE,
                'gyro_z': values[5] * self.GYRO_SCALE
            }
            
            # Sanity check - values should be reasonable
            if abs(imu_sample['accel_x']) < 10 and abs(imu_sample['gyro_x']) < 500:
                result['imu_samples'].append(imu_sample)
        except:
            pass
    
    def looks_like_imu(self, segment: bytearray) -> bool:
        """Check if segment might contain IMU data"""
        # IMU data typically has:
        # - Length divisible by 6 (3 axes * 2 sensors)
        # - Values in reasonable range when interpreted as int16
        
        if len(segment) < 12 or len(segment) % 6 != 0:
            return False
            
        try:
            # Sample first 6 values
            values = struct.unpack('<6h', segment[:12])
            # Check if values are in reasonable range for IMU
            max_val = max(abs(v) for v in values)
            return 100 < max_val < 30000  # Typical IMU raw values
        except:
            return False
    
    def unpack_eeg_samples(self, data: bytes) -> List[float]:
        """Unpack 12-bit EEG samples from 18 bytes"""
        if len(data) < 18:
            return []
            
        samples = []
        try:
            # 12 samples of 12-bit data packed in 18 bytes
            for i in range(6):  # 6 groups of 3 bytes = 2 samples
                offset = i * 3
                if offset + 3 <= len(data):
                    three_bytes = data[offset:offset+3]
                    
                    # Extract two 12-bit samples from 3 bytes
                    sample1 = (three_bytes[0] << 4) | (three_bytes[1] >> 4)
                    sample2 = ((three_bytes[1] & 0x0F) << 8) | three_bytes[2]
                    
                    # Convert to microvolts
                    uv1 = (sample1 - 2048) * self.EEG_SCALE_FACTOR
                    uv2 = (sample2 - 2048) * self.EEG_SCALE_FACTOR
                    
                    # Sanity check - EEG should be in reasonable range
                    if -500 < uv1 < 500:
                        samples.append(uv1)
                    if -500 < uv2 < 500:
                        samples.append(uv2)
        except:
            pass
            
        return samples
    
    def extract_numeric_patterns(self, data: bytearray, result: Dict):
        """Extract any identifiable numeric patterns from data"""
        patterns = []
        
        # Look for sequences of int16 values
        for i in range(0, len(data) - 2, 2):
            try:
                val = struct.unpack('<h', data[i:i+2])[0]
                if -32768 < val < 32767:
                    patterns.append(val)
            except:
                pass
                
        if patterns:
            result['unknown_data'].append({
                'type': 'int16_sequence',
                'count': len(patterns),
                'sample': patterns[:10]  # First 10 values
            })
    
    def get_statistics(self, parsed_data: Dict) -> Dict:
        """Get statistics from parsed data"""
        stats = {
            'packet_size': parsed_data['packet_size'],
            'num_segments': len(parsed_data['segments']),
            'eeg_samples': len(parsed_data['eeg_samples']),
            'imu_samples': len(parsed_data['imu_samples']),
            'segment_types': {}
        }
        
        # Count segment types
        for segment in parsed_data['segments']:
            seg_type = segment.get('type', 'unknown')
            stats['segment_types'][seg_type] = stats['segment_types'].get(seg_type, 0) + 1
            
        return stats


# Example usage and testing
if __name__ == "__main__":
    # Test with actual data from pcap
    test_data = bytes.fromhex(
        "e70100a1dae289930111059c010084407640570cf993a8e0fa3e1752ffffffffff03003edd3798116f82"
    )
    
    parser = MuseDataParser()
    result = parser.parse_packet(bytearray(test_data))
    stats = parser.get_statistics(result)
    
    print("📊 Parsing Test Results:")
    print(f"Packet size: {stats['packet_size']} bytes")
    print(f"Segments found: {stats['num_segments']}")
    print(f"EEG samples: {stats['eeg_samples']}")
    print(f"IMU samples: {stats['imu_samples']}")
    print(f"Segment types: {stats['segment_types']}")
    
    if result['eeg_samples']:
        print(f"\n📈 Sample EEG values (µV): {result['eeg_samples'][:3]}")
    if result['imu_samples']:
        print(f"\n🔄 Sample IMU values: {result['imu_samples'][:1]}")