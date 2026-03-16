"""
Muse S Athena (Gen 3, MS_03) BLE Protocol

Correct packet parsing for the Athena variant, which uses a different
GATT profile and data encoding than older Muse devices.

Key differences from older Muse models:
- Multiplexed sensor data on a single characteristic (273e0013)
- TAG-based subpacket structure (not heuristic byte-0 identification)
- 14-bit LSB-first EEG packing (not 12-bit MSB-first)
- 20-bit LSB-first optics packing
- 16-bit little-endian IMU data

Protocol reverse-engineered via BLE packet capture analysis.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# BLE UUIDs
# ---------------------------------------------------------------------------
MUSE_SERVICE_UUID = "0000fe8d-0000-1000-8000-00805f9b34fb"
CONTROL_UUID = "273e0001-4c4d-454d-96be-f03bac821358"
SENSOR_UUID = "273e0013-4c4d-454d-96be-f03bac821358"
CONFIG_UUID = "273e0014-4c4d-454d-96be-f03bac821358"
SECONDARY_UUID = "273e0015-4c4d-454d-96be-f03bac821358"

# Legacy per-channel UUIDs (older Muse models, NOT used by Athena)
LEGACY_EEG_UUIDS = {
    "TP9": "273e0003-4c4d-454d-96be-f03bac821358",
    "AF7": "273e0004-4c4d-454d-96be-f03bac821358",
    "AF8": "273e0005-4c4d-454d-96be-f03bac821358",
    "TP10": "273e0006-4c4d-454d-96be-f03bac821358",
    "AUX": "273e0007-4c4d-454d-96be-f03bac821358",
}

# ---------------------------------------------------------------------------
# Subpacket TAG definitions
# ---------------------------------------------------------------------------
TAG_EEG_4CH = 0x11       # 4 channels, 4 samples/pkt, 28 data bytes
TAG_EEG_8CH = 0x12       # 8 channels, 2 samples/pkt, 28 data bytes
TAG_OPTICS_4CH = 0x34    # 4 channels, 3 samples/pkt, 30 data bytes
TAG_OPTICS_8CH = 0x35    # 8 channels, 2 samples/pkt, 40 data bytes
TAG_OPTICS_16CH = 0x36   # 16 channels, 1 sample/pkt, 40 data bytes
TAG_ACCGYRO = 0x47       # 6 channels, 3 samples/pkt, 36 data bytes
TAG_BATTERY_1 = 0x88     # Battery info, 188 data bytes
TAG_BATTERY_2 = 0x98     # Battery info, 20 data bytes

# Sensor configuration per TAG
# Format: (type, n_channels, n_samples, data_len, sample_rate_hz)
SENSOR_CONFIG = {
    TAG_EEG_4CH:     ("EEG",     4,  4, 28,  256),
    TAG_EEG_8CH:     ("EEG",     8,  2, 28,  256),
    TAG_OPTICS_4CH:  ("OPTICS",  4,  3, 30,  64),
    TAG_OPTICS_8CH:  ("OPTICS",  8,  2, 40,  64),
    TAG_OPTICS_16CH: ("OPTICS",  16, 1, 40,  64),
    TAG_ACCGYRO:     ("ACCGYRO", 6,  3, 36,  52),
    TAG_BATTERY_1:   ("BATTERY", 1,  1, 188, 0.2),
    TAG_BATTERY_2:   ("BATTERY", 1,  1, 20,  1.0),
}

# ---------------------------------------------------------------------------
# Scaling factors
# ---------------------------------------------------------------------------
EEG_SCALE = 1450.0 / 16383.0    # 14-bit raw → microvolts
ACC_SCALE = 0.0000610352         # raw → g
GYRO_SCALE = -0.0074768          # raw → deg/s
OPTICS_SCALE = 1.0 / 32768.0    # raw → normalized

# ---------------------------------------------------------------------------
# EEG channel names
# ---------------------------------------------------------------------------
EEG_CHANNELS_4 = ["TP9", "AF7", "AF8", "TP10"]
EEG_CHANNELS_8 = ["TP9", "AF7", "AF8", "TP10", "FPz", "AUX_R", "AUX_L", "CH8"]

# Optics channel names (8-channel mode, preset p1034)
OPTICS_CHANNELS_8 = [
    "LO_NIR", "RO_NIR",   # Left/Right Outer, ~850nm (fNIRS)
    "LO_IR", "RO_IR",     # Left/Right Outer, ~735nm (fNIRS)
    "LI_NIR", "RI_NIR",   # Left/Right Inner, ~850nm (PPG/short-ch)
    "LI_IR", "RI_IR",     # Left/Right Inner, ~735nm (PPG/short-ch)
]

# ---------------------------------------------------------------------------
# Packet header
# ---------------------------------------------------------------------------
HEADER_SIZE = 14  # First 14 bytes of each BLE notification


# ---------------------------------------------------------------------------
# Command encoding
# ---------------------------------------------------------------------------
def encode_cmd(cmd: str) -> bytes:
    """Encode a command string as a length-prefixed packet.

    Format: [length+1] [cmd bytes] [newline]
    e.g. "v6" → bytes [0x03, 0x76, 0x36, 0x0a]
    """
    encoded = cmd.encode("utf-8") + b"\n"
    return bytes([len(encoded) + 1]) + encoded


# Pre-encoded commands
COMMANDS = {
    "v6": encode_cmd("v6"),       # Request firmware version
    "s": encode_cmd("s"),         # Request device status
    "h": encode_cmd("h"),         # Halt streaming
    "p21": encode_cmd("p21"),     # Basic preset
    "p1034": encode_cmd("p1034"), # Full sensors (EEG + IMU + Optics)
    "p1035": encode_cmd("p1035"), # Alternative full sensor preset
    "dc001": encode_cmd("dc001"), # Start data stream
    "L1": encode_cmd("L1"),       # Required after dc001
}


def get_init_sequence(preset: str = "p1034") -> List[Tuple[str, bytes, float]]:
    """Return the correct Athena init command sequence.

    Each entry is (description, command_bytes, delay_after_seconds).
    The Athena requires dc001 to be sent twice -- first with preset p21,
    then after switching to the target preset.

    Args:
        preset: Target preset for streaming. Default "p1034" (full sensors).

    Returns:
        List of (description, command_bytes, delay_seconds) tuples.
    """
    return [
        # Phase 1: Handshake
        ("request firmware version", COMMANDS["v6"], 0.05),
        ("request device status", COMMANDS["s"], 0.05),
        ("halt any existing stream", COMMANDS["h"], 0.05),
        # Phase 2: Initial preset
        ("set initial preset p21", COMMANDS["p21"], 0.05),
        ("request status after preset", COMMANDS["s"], 0.05),
        # Phase 3: First start (primes the device)
        ("first dc001 (prime)", COMMANDS["dc001"], 0.05),
        ("L1 after first dc001", COMMANDS["L1"], 0.05),
        # Phase 4: Switch to target preset
        ("halt before preset switch", COMMANDS["h"], 0.05),
        ("set target preset", COMMANDS[preset], 0.05),
        ("request status after target preset", COMMANDS["s"], 0.05),
        # Phase 5: Actually start streaming
        ("second dc001 (start)", COMMANDS["dc001"], 0.05),
        ("L1 after second dc001", COMMANDS["L1"], 0.05),
    ]


# ---------------------------------------------------------------------------
# Bit unpacking helpers
# ---------------------------------------------------------------------------
def _unpack_bits_lsb(data: bytes, n_bits: int) -> List[int]:
    """Extract all bits from data, LSB-first within each byte.

    Returns a flat list of 0/1 values.
    """
    bits = []
    for byte in data:
        for bit in range(8):
            bits.append((byte >> bit) & 1)
    return bits


def _extract_values_from_bits(bits: List[int], n_values: int,
                              bits_per_value: int) -> List[int]:
    """Extract n_values unsigned integers of bits_per_value width from a bit list."""
    mask = (1 << bits_per_value) - 1
    values = []
    for i in range(n_values):
        start = i * bits_per_value
        value = 0
        for b in range(bits_per_value):
            if bits[start + b]:
                value |= (1 << b)
        values.append(value)
    return values


# ---------------------------------------------------------------------------
# Decoders
# ---------------------------------------------------------------------------
def decode_eeg(data: bytes, n_channels: int) -> np.ndarray:
    """Decode EEG data from 14-bit LSB-first packed bytes.

    Args:
        data: Raw data bytes (28 bytes for both 4ch and 8ch modes).
        n_channels: Number of EEG channels (4 or 8).

    Returns:
        np.ndarray of shape (n_samples, n_channels) in microvolts.
        - 4ch mode: (4, 4) -- 4 samples x 4 channels
        - 8ch mode: (2, 8) -- 2 samples x 8 channels
    """
    n_samples = 4 if n_channels == 4 else 2
    n_values = n_samples * n_channels  # 16 values either way

    bits = _unpack_bits_lsb(data[:28], 14)
    raw_values = _extract_values_from_bits(bits, n_values, 14)

    result = np.array(raw_values, dtype=np.float32).reshape(n_samples, n_channels)
    result *= EEG_SCALE
    return result


def decode_accgyro(data: bytes) -> np.ndarray:
    """Decode accelerometer + gyroscope data from 16-bit little-endian bytes.

    Args:
        data: Raw data bytes (36 bytes = 18 int16 values).

    Returns:
        np.ndarray of shape (3, 6) -- 3 samples x 6 channels.
        Columns 0-2: accelerometer in g.
        Columns 3-5: gyroscope in deg/s.
    """
    raw = np.frombuffer(data[:36], dtype="<i2").reshape(3, 6).astype(np.float32)
    result = raw.copy()
    result[:, 0:3] *= ACC_SCALE    # accelerometer → g
    result[:, 3:6] *= GYRO_SCALE   # gyroscope → deg/s
    return result


def decode_optics(data: bytes, n_channels: int) -> np.ndarray:
    """Decode optics/PPG data from 20-bit LSB-first packed bytes.

    Args:
        data: Raw data bytes.
        n_channels: Number of optics channels (4, 8, or 16).

    Returns:
        np.ndarray of shape (n_samples, n_channels), normalized.
        - 4ch mode: (3, 4) from 30 bytes
        - 8ch mode: (2, 8) from 40 bytes
        - 16ch mode: (1, 16) from 40 bytes
    """
    config = {4: (3, 30), 8: (2, 40), 16: (1, 40)}
    n_samples, n_bytes = config[n_channels]
    n_values = n_samples * n_channels

    bits = _unpack_bits_lsb(data[:n_bytes], 20)
    raw_values = _extract_values_from_bits(bits, n_values, 20)

    result = np.array(raw_values, dtype=np.float32).reshape(n_samples, n_channels)
    result *= OPTICS_SCALE
    return result


def decode_battery(data: bytes, tag: int) -> dict:
    """Decode battery information.

    Args:
        data: Raw data bytes.
        tag: TAG_BATTERY_1 (0x88) or TAG_BATTERY_2 (0x98).

    Returns:
        Dict with battery info. Exact structure depends on firmware.
    """
    # Battery packets contain JSON-like status; for now return raw
    return {"raw": data, "tag": tag}


def decode_subpacket(tag: int, data: bytes) -> Optional[dict]:
    """Decode a single subpacket given its TAG and data bytes.

    Args:
        tag: Subpacket TAG identifier.
        data: Raw data bytes for this subpacket.

    Returns:
        Dict with 'type', 'tag', 'data' (decoded np.ndarray or dict),
        'n_channels', 'n_samples', 'sample_rate'.
        Returns None if TAG is unknown.
    """
    config = SENSOR_CONFIG.get(tag)
    if config is None:
        return None

    sensor_type, n_channels, n_samples, data_len, sample_rate = config

    if sensor_type == "EEG":
        decoded = decode_eeg(data, n_channels)
    elif sensor_type == "ACCGYRO":
        decoded = decode_accgyro(data)
    elif sensor_type == "OPTICS":
        decoded = decode_optics(data, n_channels)
    elif sensor_type == "BATTERY":
        decoded = decode_battery(data, tag)
    else:
        return None

    return {
        "type": sensor_type,
        "tag": tag,
        "data": decoded,
        "n_channels": n_channels,
        "n_samples": n_samples,
        "sample_rate": sample_rate,
    }


# ---------------------------------------------------------------------------
# Payload parser
# ---------------------------------------------------------------------------
def parse_payload(payload: bytes) -> Dict[str, list]:
    """Parse a complete BLE notification payload into decoded subpackets.

    The payload structure:
    - Bytes 0-13: 14-byte header (byte 9 = first subpacket TAG)
    - Bytes 14+: First subpacket data (no TAG prefix, type from header byte 9)
    - After first subpacket: [TAG(1)][header(4)][data(N)] for each additional subpacket

    Args:
        payload: Raw bytes from a BLE notification on SENSOR_UUID.

    Returns:
        Dict with keys "EEG", "ACCGYRO", "OPTICS", "BATTERY", each
        containing a list of decoded subpacket dicts.
    """
    result: Dict[str, list] = {
        "EEG": [],
        "ACCGYRO": [],
        "OPTICS": [],
        "BATTERY": [],
    }

    if len(payload) < HEADER_SIZE + 1:
        return result

    # First subpacket: TAG is at header byte 9, data starts at offset 14
    first_tag = payload[9]
    config = SENSOR_CONFIG.get(first_tag)
    if config is not None:
        data_len = config[3]  # data_len field
        data_end = HEADER_SIZE + data_len
        if data_end <= len(payload):
            data_bytes = payload[HEADER_SIZE:data_end]
            decoded = decode_subpacket(first_tag, data_bytes)
            if decoded is not None:
                result[decoded["type"]].append(decoded)
            offset = data_end
        else:
            return result
    else:
        # Unknown first TAG, can't determine data length
        return result

    # Subsequent subpackets: [TAG(1)] [header(4)] [data(N)]
    while offset + 5 < len(payload):
        tag = payload[offset]
        cfg = SENSOR_CONFIG.get(tag)
        if cfg is None:
            break  # Unknown TAG, stop parsing

        data_len = cfg[3]
        data_start = offset + 5  # 1 byte TAG + 4 bytes header
        data_end = data_start + data_len

        if data_end > len(payload):
            break  # Not enough data

        data_bytes = payload[data_start:data_end]
        decoded = decode_subpacket(tag, data_bytes)
        if decoded is not None:
            result[decoded["type"]].append(decoded)

        offset = data_end

    return result
