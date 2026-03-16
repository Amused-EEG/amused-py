"""
Muse Raw Stream Handler
Efficient binary storage and decoding for Muse S data streams

Binary format is ~10x smaller than CSV and preserves exact packet structure.
Decoding uses TAG-based subpacket parsing per the Athena protocol.
"""

import struct
import datetime
import numpy as np
from typing import List, Dict, Optional, BinaryIO, Generator
from dataclasses import dataclass
import os

import muse_athena_protocol as proto

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
    - Can decode on-the-fly using TAG-based protocol
    """

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
                           b'\x00' * 16)

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
                           self.packet_count & 0xFFFF,
                           relative_ms,
                           packet_type,
                           size)

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
            header = self.file_handle.read(9)
            if len(header) < 9:
                break

            packet_num, relative_ms, packet_type, size = struct.unpack('<HIBH', header)

            data = self.file_handle.read(size)
            if len(data) < size:
                break

            timestamp = self.session_start + datetime.timedelta(milliseconds=relative_ms)

            yield RawPacket(
                timestamp=timestamp,
                packet_num=packet_num,
                packet_type=packet_type,
                data=data
            )

    def decode_packet(self, packet: RawPacket) -> Dict:
        """
        Decode raw packet into sensor data using TAG-based protocol.

        Args:
            packet: Raw packet to decode

        Returns:
            Dictionary with decoded sensor values
        """
        result = {
            'timestamp': packet.timestamp,
            'packet_num': packet.packet_num,
            'raw_hex': packet.data.hex()
        }

        parsed = proto.parse_payload(packet.data)

        # EEG
        if parsed["EEG"]:
            result['eeg'] = {}
            for subpacket in parsed["EEG"]:
                arr = subpacket["data"]
                n_channels = subpacket["n_channels"]
                names = proto.EEG_CHANNELS_4 if n_channels == 4 else proto.EEG_CHANNELS_8
                for ch_idx in range(n_channels):
                    ch_name = names[ch_idx] if ch_idx < len(names) else f"ch{ch_idx}"
                    result['eeg'][ch_name] = arr[:, ch_idx].tolist()

        # IMU
        if parsed["ACCGYRO"]:
            for subpacket in parsed["ACCGYRO"]:
                arr = subpacket["data"]
                result['imu'] = {
                    'accelerometer': arr[:, 0:3].tolist(),
                    'gyroscope': arr[:, 3:6].tolist()
                }

        # Optics/PPG
        if parsed["OPTICS"]:
            result['ppg'] = {}
            for subpacket in parsed["OPTICS"]:
                arr = subpacket["data"]
                n_channels = subpacket["n_channels"]
                if n_channels == 8:
                    names = proto.OPTICS_CHANNELS_8
                else:
                    names = [f"opt{i}" for i in range(n_channels)]
                for ch_idx in range(n_channels):
                    ch_name = names[ch_idx] if ch_idx < len(names) else f"opt{ch_idx}"
                    result['ppg'][ch_name] = arr[:, ch_idx].tolist()

        # Determine packet type string
        types_found = []
        if parsed["EEG"]:
            types_found.append("EEG")
        if parsed["ACCGYRO"]:
            types_found.append("IMU")
        if parsed["OPTICS"]:
            types_found.append("OPTICS")
        if parsed["BATTERY"]:
            types_found.append("BATTERY")
        result['packet_type'] = "+".join(types_found) if types_found else "UNKNOWN"

        return result

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

        self.open_read()
        session_start = self.session_start

        packet_count = 0
        packet_types = {}
        first_packet_time = None
        last_packet_time = None

        for packet in self.read_packets():
            packet_count += 1
            decoded = self.decode_packet(packet)
            ptype = decoded.get('packet_type', 'UNKNOWN')
            packet_types[ptype] = packet_types.get(ptype, 0) + 1

            if first_packet_time is None:
                first_packet_time = packet.timestamp
            last_packet_time = packet.timestamp

        self.close()

        duration = 0
        if first_packet_time and last_packet_time:
            duration = (last_packet_time - first_packet_time).total_seconds()

        return {
            'filepath': self.filepath,
            'format_version': 2,
            'session_start': session_start.isoformat() if session_start else None,
            'duration_seconds': duration,
            'file_size_bytes': file_size,
            'file_size_mb': file_size / (1024 * 1024),
            'packet_count': packet_count,
            'packet_types': packet_types,
            'packets_per_second': packet_count / duration if duration > 0 else 0,
            'compression_ratio': "~10x smaller than CSV",
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

    info = stream.get_file_info()
    print(f"Converted to binary: {output_path}")
    print(f"  Size: {info['file_size_mb']:.2f} MB")
    print(f"  Packets: {info['packet_count']}")

    return output_path

# Example usage
if __name__ == "__main__":
    print("Muse Raw Stream Handler")
    print("=" * 60)

    stream = MuseRawStream("test_stream.bin")

    # Write some test packets with TAG-based format
    stream.open_write()

    # Simulate EEG packet: 14-byte header (byte 9 = TAG_EEG_4CH) + 28 bytes data
    header = bytearray(14)
    header[9] = proto.TAG_EEG_4CH
    test_eeg = bytes(header) + bytes(28)
    stream.write_packet(test_eeg)

    # Simulate ACCGYRO packet: 14-byte header (byte 9 = TAG_ACCGYRO) + 36 bytes data
    header2 = bytearray(14)
    header2[9] = proto.TAG_ACCGYRO
    test_imu = bytes(header2) + bytes(36)
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
