"""
Amused - A Muse S Direct
Open source BLE protocol implementation for Muse S EEG headsets

No proprietary SDK required - just pure Python and BLE!
"""

__version__ = "1.0.0"
__author__ = "nexon33 & Claude"

# Core streaming client
from .muse_stream_client import MuseStreamClient

# Legacy clients for testing
from .muse_exact_client import MuseExactClient
from .muse_sleep_client import MuseSleepClient

# Raw binary format
from .muse_raw_stream import MuseRawStream, RawPacket

# Real-time decoding
from .muse_realtime_decoder import MuseRealtimeDecoder, DecodedData

# Replay functionality
from .muse_replay import MuseReplayPlayer, MuseBinaryParser

# Data processing
from .muse_integrated_parser import MuseIntegratedParser
from .muse_sleep_parser import MuseSleepParser
from .muse_data_parser import MuseDataParser

# Biometric analysis
from .muse_ppg_heart_rate import PPGHeartRateExtractor, HeartRateResult
from .muse_fnirs_processor import FNIRSProcessor, FNIRSData

# Device configuration
from .muse_config import MuseDeviceConfig, MuseDevice
from .amused_config import AmusedConfig, quick_setup, set_viz_time, show_settings

__all__ = [
    "MuseStreamClient",
    "MuseExactClient", 
    "MuseSleepClient",
    "MuseRawStream",
    "RawPacket",
    "MuseRealtimeDecoder",
    "DecodedData",
    "MuseReplayPlayer",
    "MuseBinaryParser",
    "MuseIntegratedParser",
    "MuseSleepParser",
    "MuseDataParser",
    "PPGHeartRateExtractor",
    "HeartRateResult",
    "FNIRSProcessor",
    "FNIRSData",
    "MuseDeviceConfig",
    "MuseDevice",
    "AmusedConfig",
    "quick_setup",
    "set_viz_time",
    "show_settings",
]

def get_version():
    """Get the current version of Amused"""
    return __version__

def about():
    """Print information about Amused"""
    print(f"""
    ╔═══════════════════════════════════════════╗
    ║            Amused v{__version__}             ║
    ║       A Muse S Direct Protocol            ║
    ╚═══════════════════════════════════════════╝
    
    Open source BLE implementation for Muse S
    
    Features:
    - EEG streaming (7 channels, 256 Hz)
    - PPG heart rate monitoring (64 Hz)
    - fNIRS blood oxygenation
    - IMU motion tracking
    - Sleep monitoring (8+ hours)
    - Device discovery & configuration
    - Configurable visualization buffers
    
    No proprietary SDK required!
    
    Usage:
      import amused
      client = amused.MuseStreamClient()
      # Start streaming...
    
    For more info: https://github.com/nexon33/amused
    """)

if __name__ == "__main__":
    about()