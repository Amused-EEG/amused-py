"""
Muse S Data Parser - Handles multiplexed sensor data format
Uses TAG-based subpacket parsing per the Athena protocol.
"""

import numpy as np
from typing import List, Dict, Any
from dataclasses import dataclass

import muse_athena_protocol as proto

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
    """Parser for Muse S Athena multiplexed sensor data.

    Uses TAG-based subpacket parsing with correct decoding:
    - EEG: 14-bit LSB-first
    - IMU: 16-bit little-endian
    - Optics: 20-bit LSB-first
    """

    def __init__(self):
        self.packet_counter = 0
        self.last_timestamp = 0
        self.data_buffer = bytearray()

    def parse_packet(self, data: bytearray) -> Dict[str, Any]:
        """
        Parse a multiplexed data packet using TAG-based subpacket structure.

        Args:
            data: Raw BLE notification payload bytes.

        Returns:
            Dict with parsed sensor data.
        """
        result = {
            'packet_num': self.packet_counter,
            'packet_size': len(data),
            'eeg_samples': [],
            'imu_samples': [],
            'ppg_samples': [],
        }

        self.packet_counter += 1

        parsed = proto.parse_payload(bytes(data))

        # EEG
        for subpacket in parsed["EEG"]:
            arr = subpacket["data"]  # (n_samples, n_channels)
            n_channels = subpacket["n_channels"]
            names = proto.EEG_CHANNELS_4 if n_channels == 4 else proto.EEG_CHANNELS_8
            for s in range(arr.shape[0]):
                for c in range(n_channels):
                    ch_name = names[c] if c < len(names) else f"ch{c}"
                    result['eeg_samples'].append({
                        'channel': ch_name,
                        'value_uv': float(arr[s, c])
                    })

        # IMU
        for subpacket in parsed["ACCGYRO"]:
            arr = subpacket["data"]  # (3, 6)
            for s in range(arr.shape[0]):
                result['imu_samples'].append({
                    'accel_x': float(arr[s, 0]),
                    'accel_y': float(arr[s, 1]),
                    'accel_z': float(arr[s, 2]),
                    'gyro_x': float(arr[s, 3]),
                    'gyro_y': float(arr[s, 4]),
                    'gyro_z': float(arr[s, 5]),
                })

        # Optics/PPG
        for subpacket in parsed["OPTICS"]:
            arr = subpacket["data"]  # (n_samples, n_channels)
            n_channels = subpacket["n_channels"]
            if n_channels == 8:
                names = proto.OPTICS_CHANNELS_8
            else:
                names = [f"opt{i}" for i in range(n_channels)]
            for s in range(arr.shape[0]):
                sample = {}
                for c in range(n_channels):
                    ch_name = names[c] if c < len(names) else f"opt{c}"
                    sample[ch_name] = float(arr[s, c])
                result['ppg_samples'].append(sample)

        return result

    def get_statistics(self, parsed_data: Dict) -> Dict:
        """Get statistics from parsed data"""
        return {
            'packet_size': parsed_data['packet_size'],
            'eeg_samples': len(parsed_data['eeg_samples']),
            'imu_samples': len(parsed_data['imu_samples']),
            'ppg_samples': len(parsed_data['ppg_samples']),
        }


# Example usage and testing
if __name__ == "__main__":
    parser = MuseDataParser()

    # Build a synthetic TAG-based test packet
    header = bytearray(14)
    header[9] = proto.TAG_EEG_4CH
    eeg_data = bytes(28)  # zeros
    test_data = bytes(header) + eeg_data

    result = parser.parse_packet(bytearray(test_data))
    stats = parser.get_statistics(result)

    print("Parsing Test Results:")
    print(f"Packet size: {stats['packet_size']} bytes")
    print(f"EEG samples: {stats['eeg_samples']}")
    print(f"IMU samples: {stats['imu_samples']}")
    print(f"PPG samples: {stats['ppg_samples']}")

    if result['eeg_samples']:
        print(f"\nSample EEG values (uV): {result['eeg_samples'][:3]}")
