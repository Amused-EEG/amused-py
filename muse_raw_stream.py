"""
Muse Raw Stream Handler
Efficient binary storage and decoding for Muse S data streams

Binary format is ~10x smaller than CSV and preserves exact packet structure
"""

import struct
import datetime
import numpy as np
from typing import List, Dict, Optional, BinaryIO, Generator
from dataclasses import dataclass
import os

@dataclass
class RawPacket:
    """Container for raw packet data"""
    timestamp: datetime.datetime
    packet_num: int
    packet_type: int  # First byte identifier
    data: bytes

class MuseRawStream:
    """
    Handle raw binary streaming and storage for Muse S data
    
    Benefits over CSV:
    - 10x smaller file size
    - Preserves exact binary structure
    - Fast reading/writing
    - Can decode on-the-fly
    """
    
    # Packet type identifiers
    PACKET_TYPES = {
        0xDF: 'MULTI_EEG_PPG',    # Multiplexed EEG + PPG
        0xF4: 'MULTI_IMU',        # IMU data
        0xDB: 'MULTI_MIXED_1',    # Mixed sensor data
        0xD9: 'MULTI_MIXED_2',    # Mixed sensor data
        0xFF: 'UNKNOWN'           # Unknown/other
    }
    
    def __init__(self, filepath: Optional[str] = None):
        """
        Initialize raw stream handler
        
        Args:
            filepath: Path for binary file (auto-generated if not provided)
        """
        if filepath is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs("raw_data", exist_ok=True)
            filepath = f"raw_data/muse_raw_{timestamp}.bin"
        
        self.filepath = filepath
        self.file_handle: Optional[BinaryIO] = None
        self.packet_count = 0
        self.write_mode = False
        self.read_mode = False
    
    def open_write(self):
        """Open file for writing raw packets"""
        self.file_handle = open(self.filepath, 'wb')
        self.write_mode = True
        self.packet_count = 0
        
        # Write file header with session info
        magic = b'MUSB'  # Magic number (MUSe Binary)
        version = 2       # Format version
        session_start = datetime.datetime.now()
        start_timestamp_ms = int(session_start.timestamp() * 1000)
        
        # Header format: [magic(4)] [version(1)] [start_timestamp_ms(8)] [reserved(16)]
        header = struct.pack('<4sBQ16s', 
                           magic, 
                           version, 
                           start_timestamp_ms,
                           b'\x00' * 16)  # Reserved for future use
        
        self.file_handle.write(header)
        self.session_start = session_start
    
    def open_read(self):
        """Open file for reading raw packets"""
        self.file_handle = open(self.filepath, 'rb')
        self.read_mode = True
        
        # Read and verify header
        header_start = self.file_handle.read(5)
        magic = header_start[:4]
        version = header_start[4]
        
        if magic != b'MUSB':
            raise ValueError("Invalid file format - not a Muse binary stream file")
        
        if version != 2:
            raise ValueError(f"Unsupported format version: {version}. Only version 2 is supported.")
        
        # Read header with timing info
        extended_header = self.file_handle.read(24)  # 8 bytes timestamp + 16 reserved
        start_timestamp_ms = struct.unpack('<Q', extended_header[:8])[0]
        self.session_start = datetime.datetime.fromtimestamp(start_timestamp_ms / 1000)
    
    def write_packet(self, data: bytes, timestamp: Optional[datetime.datetime] = None):
        """
        Write raw packet to file using efficient relative timestamps
        
        Format: [packet_num(2)] [relative_ms(4)] [type(1)] [size(2)] [data(N)]
        
        Args:
            data: Raw packet bytes from BLE
            timestamp: Packet timestamp (auto-generated if not provided)
        """
        if not self.write_mode:
            self.open_write()
        
        if timestamp is None:
            timestamp = datetime.datetime.now()
        
        # Determine packet type from first byte
        packet_type = data[0] if data else 0xFF
        
        # Calculate relative timestamp (ms since session start)
        relative_ms = int((timestamp - self.session_start).total_seconds() * 1000)
        
        # Write packet with compact header
        size = len(data)
        header = struct.pack('<HIBH', 
                           self.packet_count & 0xFFFF,  # 16-bit packet number
                           relative_ms,                  # 32-bit relative timestamp
                           packet_type,                  # 8-bit unsigned type
                           size)                         # 16-bit size
        
        self.file_handle.write(header + data)
        self.packet_count += 1
        
        # Flush periodically for safety
        if self.packet_count % 100 == 0:
            self.file_handle.flush()
    
    def read_packets(self) -> Generator[RawPacket, None, None]:
        """
        Generator to read packets from file
        
        Yields:
            RawPacket objects with absolute timestamps
        """
        if not self.read_mode:
            self.open_read()
        
        while True:
            # Read compact header: [packet_num(2)] [relative_ms(4)] [type(1)] [size(2)]
            header = self.file_handle.read(9)
            if len(header) < 9:
                break
            
            # Unpack header
            packet_num, relative_ms, packet_type, size = struct.unpack('<HIBH', header)
            
            # Read data
            data = self.file_handle.read(size)
            if len(data) < size:
                break
            
            # Calculate absolute timestamp from relative
            timestamp = self.session_start + datetime.timedelta(milliseconds=relative_ms)
            
            yield RawPacket(
                timestamp=timestamp,
                packet_num=packet_num,
                packet_type=packet_type,
                data=data
            )
    
    def decode_packet(self, packet: RawPacket) -> Dict:
        """
        Decode raw packet into sensor data
        
        Args:
            packet: Raw packet to decode
            
        Returns:
            Dictionary with decoded sensor values
        """
        result = {
            'timestamp': packet.timestamp,
            'packet_num': packet.packet_num,
            'packet_type': self.PACKET_TYPES.get(packet.packet_type, 'UNKNOWN'),
            'raw_hex': packet.data.hex()
        }
        
        # Decode based on packet type
        if packet.packet_type == 0xDF:
            # EEG + PPG multiplexed
            result.update(self._decode_eeg_ppg(packet.data))
        elif packet.packet_type == 0xF4:
            # IMU data
            result.update(self._decode_imu(packet.data))
        elif packet.packet_type in [0xDB, 0xD9]:
            # Mixed sensor data
            result.update(self._decode_mixed(packet.data))
        
        return result
    
    def _decode_eeg_ppg(self, data: bytes) -> Dict:
        """Decode EEG + PPG multiplexed packet"""
        decoded = {'eeg': {}, 'ppg': {}}
        
        # Skip header (4 bytes typically)
        offset = 4
        
        # Look for EEG segments (18 bytes each)
        while offset + 18 <= len(data):
            if self._is_eeg_segment(data[offset:offset+18]):
                channel_id = len(decoded['eeg'])
                decoded['eeg'][f'channel_{channel_id}'] = self._unpack_eeg_samples(data[offset:offset+18])
                offset += 18
            elif offset + 20 <= len(data) and self._is_ppg_segment(data[offset:offset+20]):
                decoded['ppg']['samples'] = self._unpack_ppg_samples(data[offset:offset+20])
                offset += 20
            else:
                offset += 1
        
        return decoded
    
    def _decode_imu(self, data: bytes) -> Dict:
        """Decode IMU packet"""
        decoded = {'imu': {}}
        
        if len(data) >= 16:
            try:
                # Extract accelerometer and gyroscope (16-bit signed values)
                offset = 4
                ax = struct.unpack('>h', data[offset:offset+2])[0] / 100.0
                ay = struct.unpack('>h', data[offset+2:offset+4])[0] / 100.0
                az = struct.unpack('>h', data[offset+4:offset+6])[0] / 100.0
                gx = struct.unpack('>h', data[offset+6:offset+8])[0] / 100.0
                gy = struct.unpack('>h', data[offset+8:offset+10])[0] / 100.0
                gz = struct.unpack('>h', data[offset+10:offset+12])[0] / 100.0
                
                decoded['imu'] = {
                    'accelerometer': [ax, ay, az],
                    'gyroscope': [gx, gy, gz]
                }
            except:
                pass
        
        return decoded
    
    def _decode_mixed(self, data: bytes) -> Dict:
        """Decode mixed sensor packet"""
        # These contain various sensor data
        # Use generic decoding
        return self._decode_eeg_ppg(data)
    
    def _is_eeg_segment(self, segment: bytes) -> bool:
        """Check if segment contains EEG data"""
        if len(segment) != 18:
            return False
        
        # Check if values are in reasonable EEG range
        try:
            sample = (segment[0] << 4) | (segment[1] >> 4)
            return 1000 < sample < 3000  # Around 2048 midpoint
        except:
            return False
    
    def _is_ppg_segment(self, segment: bytes) -> bool:
        """Check if segment contains PPG data"""
        if len(segment) != 20:
            return False
        
        # PPG values are typically higher
        try:
            val = struct.unpack('>H', segment[0:2])[0]
            return val > 10000
        except:
            return False
    
    def _unpack_eeg_samples(self, data: bytes) -> List[float]:
        """Unpack 12 EEG samples from 18 bytes"""
        samples = []
        EEG_SCALE = 1000.0 / 2048.0  # Convert to microvolts
        
        for i in range(6):
            offset = i * 3
            three_bytes = data[offset:offset+3]
            
            # Two 12-bit samples packed in 3 bytes
            sample1 = (three_bytes[0] << 4) | (three_bytes[1] >> 4)
            sample2 = ((three_bytes[1] & 0x0F) << 8) | three_bytes[2]
            
            # Convert to microvolts
            uv1 = (sample1 - 2048) * EEG_SCALE
            uv2 = (sample2 - 2048) * EEG_SCALE
            
            samples.extend([uv1, uv2])
        
        return samples
    
    def _unpack_ppg_samples(self, data: bytes) -> List[int]:
        """Unpack PPG samples from 20 bytes"""
        samples = []
        
        # Simplified - extract as 16-bit values
        for i in range(0, min(18, len(data)), 2):
            if i + 2 <= len(data):
                val = struct.unpack('>H', data[i:i+2])[0]
                samples.append(val)
        
        return samples
    
    def close(self):
        """Close file handle"""
        if self.file_handle:
            self.file_handle.close()
            self.file_handle = None
        self.write_mode = False
        self.read_mode = False
    
    def get_file_info(self) -> Dict:
        """Get information about the raw file"""
        if not os.path.exists(self.filepath):
            return {}
        
        file_size = os.path.getsize(self.filepath)
        
        # Open to get header info
        self.open_read()
        session_start = self.session_start
        
        # Count packets and get timing
        packet_count = 0
        packet_types = {}
        first_packet_time = None
        last_packet_time = None
        
        for packet in self.read_packets():
            packet_count += 1
            ptype = self.PACKET_TYPES.get(packet.packet_type, 'UNKNOWN')
            packet_types[ptype] = packet_types.get(ptype, 0) + 1
            
            if first_packet_time is None:
                first_packet_time = packet.timestamp
            last_packet_time = packet.timestamp
        
        self.close()
        
        # Calculate duration
        duration = 0
        if first_packet_time and last_packet_time:
            duration = (last_packet_time - first_packet_time).total_seconds()
        
        return {
            'filepath': self.filepath,
            'format_version': 2,  # Always v2 now
            'session_start': session_start.isoformat() if session_start else None,
            'duration_seconds': duration,
            'file_size_bytes': file_size,
            'file_size_mb': file_size / (1024 * 1024),
            'packet_count': packet_count,
            'packet_types': packet_types,
            'packets_per_second': packet_count / duration if duration > 0 else 0,
            'compression_ratio': f"~10x smaller than CSV",
            'average_packet_size': (file_size - 29) / packet_count if packet_count > 0 else 0
        }

def convert_csv_to_raw(csv_path: str, output_path: Optional[str] = None) -> str:
    """
    Convert CSV hex dump to efficient raw binary format
    
    Args:
        csv_path: Path to CSV file
        output_path: Output binary file path
        
    Returns:
        Path to created binary file
    """
    import csv
    
    if output_path is None:
        output_path = csv_path.replace('.csv', '.bin')
    
    stream = MuseRawStream(output_path)
    stream.open_write()
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            timestamp = datetime.datetime.fromisoformat(row['timestamp'])
            hex_data = row['hex_data']
            data = bytes.fromhex(hex_data)
            
            stream.write_packet(data, timestamp)
    
    stream.close()
    
    # Get file info
    info = stream.get_file_info()
    print(f"Converted to binary: {output_path}")
    print(f"  Size: {info['file_size_mb']:.2f} MB")
    print(f"  Packets: {info['packet_count']}")
    
    return output_path

# Example usage
if __name__ == "__main__":
    print("Muse Raw Stream Handler")
    print("=" * 60)
    
    # Test with dummy data
    stream = MuseRawStream("test_stream.bin")
    
    # Write some test packets
    stream.open_write()
    
    # Simulate EEG packet
    test_eeg = bytes.fromhex("df0000" + "00" * 100)
    stream.write_packet(test_eeg)
    
    # Simulate IMU packet
    test_imu = bytes.fromhex("f40200" + "00" * 50)
    stream.write_packet(test_imu)
    
    stream.close()
    
    # Read back
    print("\nReading packets:")
    stream.open_read()
    for packet in stream.read_packets():
        decoded = stream.decode_packet(packet)
        print(f"  Packet {packet.packet_num}: {decoded['packet_type']}")
    stream.close()
    
    # Show file info
    info = stream.get_file_info()
    print(f"\nFile info:")
    print(f"  Size: {info['file_size_bytes']} bytes")
    print(f"  Packets: {info['packet_count']}")
    print(f"  Types: {info['packet_types']}")