"""
Muse Real-time Decoder
On-the-fly decoding of Muse S BLE packets with minimal latency

Provides instant access to sensor values without intermediate storage
"""

import struct
import numpy as np
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
import datetime
try:
    from scipy.signal import find_peaks
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

@dataclass
class DecodedData:
    """Container for decoded sensor data"""
    timestamp: datetime.datetime
    packet_type: str
    eeg: Optional[Dict[str, List[float]]] = None
    ppg: Optional[Dict[str, List[float]]] = None
    imu: Optional[Dict[str, List[float]]] = None
    heart_rate: Optional[float] = None
    battery: Optional[int] = None
    raw_bytes: bytes = b''

class MuseRealtimeDecoder:
    """
    Real-time packet decoder for Muse S data streams
    
    Features:
    - Zero-copy decoding where possible
    - Callback-based processing
    - Minimal memory footprint
    - Stream statistics
    """
    
    def __init__(self):
        """Initialize decoder with default settings"""
        # Scaling factors
        self.EEG_SCALE = 1000.0 / 2048.0  # Convert to microvolts
        self.IMU_SCALE = 1.0 / 100.0      # Convert to standard units
        
        # Callbacks for different data types
        self.callbacks: Dict[str, List[Callable]] = {
            'eeg': [],
            'ppg': [],
            'imu': [],
            'heart_rate': [],
            'any': []  # Called for any packet
        }
        
        # Statistics
        self.stats = {
            'packets_decoded': 0,
            'eeg_samples': 0,
            'ppg_samples': 0,
            'imu_samples': 0,
            'decode_errors': 0,
            'last_packet_time': None
        }
        
        # Buffers for derived metrics
        self.ppg_buffer = []
        self.last_heart_rate = None
    
    def register_callback(self, data_type: str, callback: Callable[[DecodedData], None]):
        """
        Register a callback for specific data type
        
        Args:
            data_type: 'eeg', 'ppg', 'imu', 'heart_rate', or 'any'
            callback: Function to call with decoded data
            
        Example:
            decoder.register_callback('eeg', lambda data: print(f"EEG: {data.eeg}"))
        """
        if data_type in self.callbacks:
            self.callbacks[data_type].append(callback)
    
    def decode(self, data: bytes, timestamp: Optional[datetime.datetime] = None) -> DecodedData:
        """
        Decode a raw BLE packet in real-time
        
        Args:
            data: Raw packet bytes
            timestamp: Packet timestamp
            
        Returns:
            DecodedData object with parsed values
        """
        if timestamp is None:
            timestamp = datetime.datetime.now()
        
        self.stats['packets_decoded'] += 1
        self.stats['last_packet_time'] = timestamp
        
        # Identify packet type
        if not data:
            return DecodedData(timestamp=timestamp, packet_type='EMPTY', raw_bytes=data)
        
        packet_type_byte = data[0]
        decoded = DecodedData(
            timestamp=timestamp,
            packet_type=self._get_packet_type(packet_type_byte),
            raw_bytes=data
        )
        
        try:
            # Fast path decoding based on packet type
            if packet_type_byte == 0xDF:
                self._decode_type_df(data, decoded)
            elif packet_type_byte == 0xF4:
                self._decode_type_f4(data, decoded)
            elif packet_type_byte == 0xDB:
                self._decode_type_db(data, decoded)
            elif packet_type_byte == 0xD9:
                self._decode_type_d9(data, decoded)
            else:
                # Try generic decoding
                self._decode_generic(data, decoded)
        except Exception as e:
            self.stats['decode_errors'] += 1
            # Continue even if decoding fails
        
        # Trigger callbacks
        self._trigger_callbacks(decoded)
        
        return decoded
    
    def _get_packet_type(self, type_byte: int) -> str:
        """Get human-readable packet type"""
        types = {
            0xDF: 'EEG_PPG',
            0xF4: 'IMU',
            0xDB: 'MIXED_1',
            0xD9: 'MIXED_2'
        }
        return types.get(type_byte, f'UNKNOWN_{type_byte:02X}')
    
    def _decode_type_df(self, data: bytes, decoded: DecodedData):
        """Fast decode for 0xDF packets (EEG + PPG)"""
        decoded.eeg = {}
        decoded.ppg = {}
        
        # Skip header (4 bytes)
        offset = 4
        channel_count = 0
        max_iterations = len(data)  # Prevent infinite loops
        iterations = 0
        
        # Muse S has 7 EEG channels: TP9, AF7, AF8, TP10, FPz, AUX_R, AUX_L
        channel_names = ['TP9', 'AF7', 'AF8', 'TP10', 'FPz', 'AUX_R', 'AUX_L']
        
        # Extract EEG segments (18 bytes each)
        while offset < len(data) and iterations < max_iterations and channel_count < 7:
            iterations += 1
            
            # Try EEG segment (18 bytes)
            if offset + 18 <= len(data) and self._looks_like_eeg(data[offset:offset+18]):
                samples = self._fast_unpack_eeg(data[offset:offset+18])
                channel_name = channel_names[channel_count] if channel_count < len(channel_names) else f'ch{channel_count}'
                decoded.eeg[channel_name] = samples
                self.stats['eeg_samples'] += len(samples)
                channel_count += 1
                offset += 18
            # Try PPG segment (20 bytes)  
            elif offset + 20 <= len(data):
                ppg_samples = self._fast_unpack_ppg(data[offset:offset+20])
                if ppg_samples:
                    decoded.ppg['samples'] = ppg_samples
                    self.stats['ppg_samples'] += len(ppg_samples)
                    
                    # Update heart rate buffer
                    self.ppg_buffer.extend(ppg_samples)
                    if len(self.ppg_buffer) > 320:  # 5 seconds at 64Hz
                        self._calculate_heart_rate(decoded)
                        self.ppg_buffer = self.ppg_buffer[-320:]
                    
                    offset += 20
                else:
                    offset += 1  # Skip one byte if not PPG
            else:
                break  # Not enough data left
    
    def _decode_type_f4(self, data: bytes, decoded: DecodedData):
        """Fast decode for 0xF4 packets (IMU)"""
        if len(data) < 16:
            return
        
        decoded.imu = {}
        offset = 4
        
        try:
            # Direct struct unpack for speed
            ax, ay, az, gx, gy, gz = struct.unpack_from('>hhhhhh', data, offset)
            
            decoded.imu['accel'] = [ax * self.IMU_SCALE, ay * self.IMU_SCALE, az * self.IMU_SCALE]
            decoded.imu['gyro'] = [gx * self.IMU_SCALE, gy * self.IMU_SCALE, gz * self.IMU_SCALE]
            self.stats['imu_samples'] += 2
        except:
            pass
    
    def _decode_type_db(self, data: bytes, decoded: DecodedData):
        """Fast decode for 0xDB packets (Mixed)"""
        # These often contain control data or mixed sensors
        self._decode_generic(data[4:], decoded)
    
    def _decode_type_d9(self, data: bytes, decoded: DecodedData):
        """Fast decode for 0xD9 packets (Mixed)"""
        # Similar to 0xDB
        self._decode_generic(data[4:], decoded)
    
    def _decode_generic(self, data: bytes, decoded: DecodedData):
        """Generic decoder for unknown packet types"""
        # Look for known patterns
        offset = 0
        
        while offset < len(data) - 10:
            # Check for EEG pattern
            if offset + 18 <= len(data) and self._looks_like_eeg(data[offset:offset+18]):
                if decoded.eeg is None:
                    decoded.eeg = {}
                samples = self._fast_unpack_eeg(data[offset:offset+18])
                # Use proper channel names for Muse S
                channel_names = ['TP9', 'AF7', 'AF8', 'TP10', 'FPz', 'AUX_R', 'AUX_L']
                ch_idx = len(decoded.eeg)
                channel_name = channel_names[ch_idx] if ch_idx < len(channel_names) else f'ch{ch_idx}'
                decoded.eeg[channel_name] = samples
                self.stats['eeg_samples'] += len(samples)
                offset += 18
            else:
                offset += 1
    
    def _looks_like_eeg(self, segment: bytes) -> bool:
        """Quick check if segment contains EEG data"""
        if len(segment) != 18:
            return False
        
        # Check first sample range
        sample = (segment[0] << 4) | (segment[1] >> 4)
        return 1000 < sample < 3000
    
    def _fast_unpack_eeg(self, data: bytes) -> List[float]:
        """Fast EEG unpacking using numpy if available"""
        samples = []
        
        # Unpack 12 samples from 18 bytes
        for i in range(6):
            offset = i * 3
            # Two 12-bit samples in 3 bytes
            b0, b1, b2 = data[offset:offset+3]
            
            sample1 = (b0 << 4) | (b1 >> 4)
            sample2 = ((b1 & 0x0F) << 8) | b2
            
            # Convert to microvolts
            samples.append((sample1 - 2048) * self.EEG_SCALE)
            samples.append((sample2 - 2048) * self.EEG_SCALE)
        
        return samples
    
    def _fast_unpack_ppg(self, data: bytes) -> List[int]:
        """Fast PPG unpacking"""
        if len(data) < 20:
            return []
        
        samples = []
        # Extract PPG samples (simplified)
        for i in range(0, 18, 3):
            if i + 2 < len(data):
                # 20-bit samples, simplified to 16-bit for speed
                val = (data[i] << 8) | data[i+1]
                if val > 10000:  # PPG range check
                    samples.append(val)
        
        return samples if len(samples) > 2 else []
    
    def _calculate_heart_rate(self, decoded: DecodedData):
        """Calculate heart rate from PPG buffer"""
        if len(self.ppg_buffer) < 320:
            return
        
        try:
            # Simple peak detection for heart rate
            signal = np.array(self.ppg_buffer[-640:] if len(self.ppg_buffer) > 640 else self.ppg_buffer)
            
            # Detrend
            signal = signal - np.mean(signal)
            
            # Find peaks (simplified)
            if not SCIPY_AVAILABLE:
                return
            peaks, _ = find_peaks(signal, distance=40, prominence=np.std(signal)*0.3)
            
            if len(peaks) > 1:
                # Calculate heart rate
                peak_intervals = np.diff(peaks) / 64.0  # 64 Hz sampling
                heart_rate = 60.0 / np.mean(peak_intervals)
                
                if 40 < heart_rate < 200:  # Physiological range
                    decoded.heart_rate = heart_rate
                    self.last_heart_rate = heart_rate
        except:
            pass
    
    def _trigger_callbacks(self, decoded: DecodedData):
        """Trigger registered callbacks"""
        # Type-specific callbacks
        if decoded.eeg and self.callbacks['eeg']:
            for callback in self.callbacks['eeg']:
                callback(decoded)
        
        if decoded.ppg and self.callbacks['ppg']:
            for callback in self.callbacks['ppg']:
                callback(decoded)
        
        if decoded.imu and self.callbacks['imu']:
            for callback in self.callbacks['imu']:
                callback(decoded)
        
        if decoded.heart_rate and self.callbacks['heart_rate']:
            for callback in self.callbacks['heart_rate']:
                callback(decoded)
        
        # General callbacks
        for callback in self.callbacks['any']:
            callback(decoded)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get decoder statistics"""
        return {
            'packets_decoded': self.stats['packets_decoded'],
            'eeg_samples': self.stats['eeg_samples'],
            'ppg_samples': self.stats['ppg_samples'],
            'imu_samples': self.stats['imu_samples'],
            'decode_errors': self.stats['decode_errors'],
            'error_rate': self.stats['decode_errors'] / max(1, self.stats['packets_decoded']),
            'last_heart_rate': self.last_heart_rate,
            'last_packet': self.stats['last_packet_time']
        }
    
    def reset_stats(self):
        """Reset statistics"""
        self.stats = {
            'packets_decoded': 0,
            'eeg_samples': 0,
            'ppg_samples': 0,
            'imu_samples': 0,
            'decode_errors': 0,
            'last_packet_time': None
        }

# Example real-time processing
def example_realtime_processing():
    """Example of real-time packet processing"""
    
    print("Real-time Decoder Example")
    print("=" * 60)
    
    # Create decoder
    decoder = MuseRealtimeDecoder()
    
    # Register callbacks for different data types
    def on_eeg(data: DecodedData):
        print(f"EEG: {len(data.eeg)} channels, first sample: {data.eeg['ch0'][0]:.1f} μV")
    
    def on_heart_rate(data: DecodedData):
        print(f"Heart Rate: {data.heart_rate:.0f} BPM")
    
    def on_imu(data: DecodedData):
        print(f"IMU: Accel={data.imu['accel']}, Gyro={data.imu['gyro']}")
    
    decoder.register_callback('eeg', on_eeg)
    decoder.register_callback('heart_rate', on_heart_rate)
    decoder.register_callback('imu', on_imu)
    
    # Simulate incoming packets
    test_packets = [
        bytes.fromhex("df0000" + "80088008" * 10),  # EEG packet
        bytes.fromhex("f40200" + "0100020003000400050006" * 2),  # IMU packet
    ]
    
    for packet in test_packets:
        decoded = decoder.decode(packet)
        print(f"Decoded: {decoded.packet_type}")
    
    # Show statistics
    stats = decoder.get_stats()
    print(f"\nStatistics:")
    print(f"  Packets: {stats['packets_decoded']}")
    print(f"  EEG samples: {stats['eeg_samples']}")
    print(f"  Error rate: {stats['error_rate']:.1%}")

if __name__ == "__main__":
    example_realtime_processing()