"""
Muse Real-time Decoder
On-the-fly decoding of Muse S Athena BLE packets with minimal latency

Provides instant access to sensor values without intermediate storage.
Uses TAG-based subpacket parsing per the Athena protocol.
"""

import numpy as np
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
import datetime
import logging

try:
    from scipy.signal import find_peaks
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

import muse_athena_protocol as proto

logger = logging.getLogger(__name__)


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
    Real-time packet decoder for Muse S Athena data streams

    Uses TAG-based subpacket parsing with correct bit-unpacking:
    - EEG: 14-bit LSB-first
    - Optics/PPG: 20-bit LSB-first
    - IMU: 16-bit little-endian

    Features:
    - Callback-based processing
    - Minimal memory footprint
    - Stream statistics
    """

    def __init__(self):
        """Initialize decoder with default settings"""
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
            data: Raw packet bytes from SENSOR_UUID notification
            timestamp: Packet timestamp

        Returns:
            DecodedData object with parsed values
        """
        if timestamp is None:
            timestamp = datetime.datetime.now()

        self.stats['packets_decoded'] += 1
        self.stats['last_packet_time'] = timestamp

        if not data:
            return DecodedData(timestamp=timestamp, packet_type='EMPTY', raw_bytes=data)

        decoded = DecodedData(
            timestamp=timestamp,
            packet_type='SENSOR',
            raw_bytes=data
        )

        try:
            parsed = proto.parse_payload(data)
            self._populate_decoded(parsed, decoded)
        except Exception as e:
            self.stats['decode_errors'] += 1
            logger.debug("Decode error: %s", e)

        # Trigger callbacks
        self._trigger_callbacks(decoded)

        return decoded

    def _populate_decoded(self, parsed: Dict[str, list], decoded: DecodedData):
        """Populate DecodedData from parsed subpackets."""

        # EEG
        if parsed["EEG"]:
            decoded.eeg = {}
            for subpacket in parsed["EEG"]:
                arr = subpacket["data"]  # shape (n_samples, n_channels)
                n_channels = subpacket["n_channels"]
                if n_channels == 4:
                    names = proto.EEG_CHANNELS_4
                else:
                    names = proto.EEG_CHANNELS_8
                for ch_idx in range(n_channels):
                    ch_name = names[ch_idx] if ch_idx < len(names) else f"ch{ch_idx}"
                    decoded.eeg[ch_name] = arr[:, ch_idx].tolist()
                    self.stats['eeg_samples'] += arr.shape[0]
            decoded.packet_type = 'EEG'

        # ACCGYRO (IMU)
        if parsed["ACCGYRO"]:
            decoded.imu = {}
            for subpacket in parsed["ACCGYRO"]:
                arr = subpacket["data"]  # shape (3, 6)
                decoded.imu['accel'] = arr[:, 0:3].tolist()
                decoded.imu['gyro'] = arr[:, 3:6].tolist()
                self.stats['imu_samples'] += arr.shape[0]
            if not parsed["EEG"]:
                decoded.packet_type = 'IMU'

        # Optics (PPG)
        if parsed["OPTICS"]:
            decoded.ppg = {}
            for subpacket in parsed["OPTICS"]:
                arr = subpacket["data"]  # shape (n_samples, n_channels)
                n_channels = subpacket["n_channels"]
                if n_channels == 8:
                    names = proto.OPTICS_CHANNELS_8
                else:
                    names = [f"opt{i}" for i in range(n_channels)]
                for ch_idx in range(n_channels):
                    ch_name = names[ch_idx] if ch_idx < len(names) else f"opt{ch_idx}"
                    decoded.ppg[ch_name] = arr[:, ch_idx].tolist()
                self.stats['ppg_samples'] += arr.shape[0]

                # Update heart rate buffer using IR channel (index 0)
                ir_samples = arr[:, 0].tolist()
                self.ppg_buffer.extend(ir_samples)
                if len(self.ppg_buffer) > 128:  # 2 seconds at 64Hz
                    self._calculate_heart_rate(decoded)
                    if len(self.ppg_buffer) > 320:  # Keep max 5 seconds
                        self.ppg_buffer = self.ppg_buffer[-320:]

            if decoded.packet_type == 'SENSOR':
                decoded.packet_type = 'OPTICS'

        # Battery
        if parsed["BATTERY"]:
            decoded.packet_type = 'BATTERY'

        # Combined packet type
        if parsed["EEG"] and (parsed["OPTICS"] or parsed["ACCGYRO"]):
            decoded.packet_type = 'MULTI'

    def _calculate_heart_rate(self, decoded: DecodedData):
        """Calculate heart rate from PPG buffer"""
        if len(self.ppg_buffer) < 128:  # Need at least 2 seconds
            return

        try:
            signal = np.array(
                self.ppg_buffer[-640:] if len(self.ppg_buffer) > 640
                else self.ppg_buffer
            )

            # Detrend
            signal = signal - np.mean(signal)

            if not SCIPY_AVAILABLE:
                return
            peaks, _ = find_peaks(signal, distance=40, prominence=np.std(signal) * 0.3)

            if len(peaks) > 1:
                peak_intervals = np.diff(peaks) / 64.0  # 64 Hz sampling
                heart_rate = 60.0 / np.mean(peak_intervals)

                if 40 < heart_rate < 200:  # Physiological range
                    decoded.heart_rate = heart_rate
                    self.last_heart_rate = heart_rate
                    logger.debug("Calculated HR: %.1f BPM", heart_rate)
        except Exception:
            pass

    def _trigger_callbacks(self, decoded: DecodedData):
        """Trigger registered callbacks"""
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

    decoder = MuseRealtimeDecoder()

    def on_eeg(data: DecodedData):
        first_channel = next(iter(data.eeg.keys()))
        print(f"EEG: {len(data.eeg)} channels, {first_channel}: {data.eeg[first_channel][0]:.1f} uV")

    def on_heart_rate(data: DecodedData):
        print(f"Heart Rate: {data.heart_rate:.0f} BPM")

    def on_imu(data: DecodedData):
        print(f"IMU: Accel={data.imu['accel']}, Gyro={data.imu['gyro']}")

    decoder.register_callback('eeg', on_eeg)
    decoder.register_callback('heart_rate', on_heart_rate)
    decoder.register_callback('imu', on_imu)

    # Build a synthetic TAG-based test packet:
    # 14-byte header (byte 9 = TAG_EEG_4CH = 0x11) + 28 bytes EEG data
    header = bytearray(14)
    header[9] = proto.TAG_EEG_4CH
    eeg_data = bytes(28)  # zeros = all channels at 0 uV
    test_packet = bytes(header) + eeg_data

    decoded = decoder.decode(test_packet)
    print(f"Decoded: {decoded.packet_type}")

    stats = decoder.get_stats()
    print(f"\nStatistics:")
    print(f"  Packets: {stats['packets_decoded']}")
    print(f"  EEG samples: {stats['eeg_samples']}")
    print(f"  Error rate: {stats['error_rate']:.1%}")


if __name__ == "__main__":
    example_realtime_processing()
