"""
Amused - A Muse S Direct
Open source BLE protocol implementation for Muse S EEG headsets

No proprietary SDK required - just pure Python and BLE!
"""

__version__ = "1.0.0"
__author__ = "nexon33 & Claude"

# Core clients
from .muse_exact_client import MuseClient
from .muse_sleep_client import MuseSleepClient

# Data processing
from .muse_integrated_parser import MuseIntegratedParser
from .muse_sleep_parser import MuseSleepParser
from .muse_data_parser import MuseDataParser

# Biometric analysis
from .muse_ppg_heart_rate import PPGHeartRateExtractor
from .muse_fnirs_processor import FNIRSProcessor

__all__ = [
    "MuseClient",
    "MuseSleepClient",
    "MuseIntegratedParser",
    "MuseSleepParser",
    "MuseDataParser",
    "PPGHeartRateExtractor",
    "FNIRSProcessor",
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
    - EEG streaming (12 channels, 256 Hz)
    - PPG heart rate monitoring (64 Hz)
    - fNIRS blood oxygenation
    - IMU motion tracking
    - Sleep monitoring (8+ hours)
    
    No proprietary SDK required!
    
    Usage:
      import amused
      client = amused.MuseClient()
      # Start streaming...
    
    For more info: https://github.com/nexon33/amused
    """)

if __name__ == "__main__":
    about()