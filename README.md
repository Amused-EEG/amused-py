# Amused - A Muse S Direct

**The first open-source BLE protocol implementation for Muse S headsets**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Finally!** Direct BLE connection to Muse S without proprietary SDKs. We're quite *amused* that we cracked the protocol nobody else has published online!

## 🎉 The Real Story

We actually got access to InteraXon's official SDK - but discovered it **doesn't provide the low-level control researchers need**. The SDK locks you into their framework, limits data access, and doesn't expose the raw protocol. So we reverse-engineered the BLE communication from scratch.

**Key breakthrough:** The `dc001` command must be sent TWICE to start streaming - a critical detail not in any documentation!

## Features

- **EEG Streaming**: 7 channels at 256 Hz (TP9, AF7, AF8, TP10, FPz, AUX_R, AUX_L)
- **PPG Heart Rate**: Real-time HR and HRV from 3-wavelength sensors  
- **fNIRS Blood Oxygenation**: Cerebral hemodynamics (HbO2, HbR, TSI)
- **IMU Motion**: 9-axis accelerometer + gyroscope
- **Sleep Monitoring**: 8+ hour sessions with automatic data logging
- **Real-time Visualization**: Interactive plots with PyQtGraph or web-based Plotly/Dash
- **Binary Recording**: 10x more efficient than CSV with replay capability
- **No SDK Required**: Pure Python with BLE - no proprietary libraries!

## Installation

```bash
pip install amused
```

Or from source:
```bash
git clone https://github.com/nexon33/amused.git
cd amused
pip install -e .
```

## Quick Start

```python
import amused
import asyncio

async def stream():
    # Find and connect to a Muse device
    devices = await amused.find_muse_devices()
    if devices:
        device = devices[0]  # Use first device found
        
        # Stream with full sensor suite
        client = amused.MuseSleepClient()  
        await client.connect_and_monitor(device.address)

asyncio.run(stream())
```

## Core Modules

### `muse_exact_client.py` 
**Testing & Basic EEG** - This was our initial proof-of-concept that cracked the protocol. It streams basic EEG data using the minimal command sequence. Great for testing connections and debugging.

### `muse_sleep_client.py`
**Full Sensor Suite** - This is what you want for real applications! It enables ALL sensors just like the Muse app's sleep mode:
- All EEG channels
- PPG for heart rate 
- fNIRS for blood oxygenation
- IMU for motion tracking
- Extended monitoring (8+ hours)
- CSV data logging

The sleep client uses presets `p1034`/`p1035` which activate the complete sensor array, while the exact client uses `p21` for basic EEG only.

## Command Line Tools

```bash
# Basic EEG test (verify connection)
amused-stream  # Uses muse_exact_client

# Full sensor monitoring (all modalities)
amused-sleep   # Uses muse_sleep_client

# Parse recorded data
amused-parse
```

## Usage Examples

### Full Biometric Monitoring (Recommended)
```python
from amused import MuseSleepClient

client = MuseSleepClient(log_dir="my_data")
# Monitors for specified hours with ALL sensors
await client.connect_and_monitor(device_address, duration_hours=1)
```

### Basic EEG Testing
```python
from amused import MuseClient

client = MuseClient()
# Simple 30-second EEG stream for testing
await client.connect_and_stream(device_address)
```

### Heart Rate Extraction
```python
extractor = amused.PPGHeartRateExtractor()
result = extractor.extract_heart_rate(ppg_data)
print(f"Heart Rate: {result.heart_rate_bpm} BPM")
print(f"HRV RMSSD: {result.hrv_rmssd} ms")
```

### Blood Oxygenation (fNIRS)
```python
processor = amused.FNIRSProcessor()
processor.add_samples(ir, nir, red)
fnirs = processor.extract_fnirs()
print(f"Brain Oxygen Saturation: {fnirs.tsi}%")
```

### Parse Sleep Session
```python
parser = amused.MuseIntegratedParser()
data = parser.parse_csv_file("sleep_data/session.csv")
# Extracts EEG, PPG, fNIRS, and IMU from multiplexed stream
```

## Protocol Details

The Muse S multiplexes all sensor data in a single BLE stream. Key differences:

**Basic Mode (p21 preset)**:
- EEG only
- Simple packet structure
- Lower bandwidth

**Sleep Mode (p1034/p1035 presets)**:
- All sensors enabled
- Multiplexed packets with headers (0xdf, 0xf4, 0xdb, 0xd9)
- PPG/fNIRS embedded in stream
- Higher bandwidth (~17 packets/sec)

## Requirements

- Python 3.8+
- Bleak (BLE library)
- NumPy, SciPy
- Muse S headset

## Troubleshooting

**No data received?**
- Ensure `dc001` is sent twice (critical!)
- Try both clients (exact for basic, sleep for full)
- Check Bluetooth pairing

**PPG not working?**
- PPG is embedded in sleep mode stream
- Use `MuseSleepClient`, not `MuseClient`
- Parse with `MuseIntegratedParser`

## Real-time Visualization

Amused includes powerful visualization capabilities with multiple backends:

### PyQtGraph (Desktop - Fastest)
```python
from amused import MuseStreamClient
from muse_visualizer import MuseVisualizer

# Create visualizer
viz = MuseVisualizer(backend='pyqtgraph')

# Stream with visualization
client = MuseStreamClient()
client.on_eeg(viz.update_eeg)
client.on_ppg(viz.update_ppg)
client.on_heart_rate(viz.update_heart_rate)
client.on_imu(viz.update_imu)

# Start streaming and visualization
# See examples/06_realtime_visualization.py
```

### Plotly/Dash (Web-based)
```python
# Web-based visualization at http://localhost:8050
viz = MuseVisualizer(backend='plotly', port=8050)
viz.run()  # Opens in browser
```

### Installation
```bash
# For PyQtGraph (fastest, desktop)
pip install pyqtgraph PyQt5

# For Plotly/Dash (web-based)
pip install plotly dash

# Or install all visualization dependencies
pip install -r requirements-viz.txt
```

### Features
- Live EEG waveforms (7 channels: TP9, AF7, AF8, TP10, FPz, AUX_R, AUX_L)
- PPG heart rate monitoring with trend
- IMU motion tracking (accel + gyro)
- Frequency spectrum analysis with band indicators
- Smooth 30+ FPS updates
- Recording replay with visualization

## Contributing

This is the first open implementation! Areas to explore:
- Additional presets
- Machine learning pipelines
- Mobile apps
- Advanced signal processing

## License

MIT License - see LICENSE file

## Citation

If you use Amused in research:
```
@software{amused2025,
  title = {Amused: A Muse S Direct BLE Implementation},
  author = {Adrian Tadeusz Belmans},
  year = {2025},
  url = {https://github.com/nexon33/amused}
}
```

---

**Note**: Research software for educational purposes. Not for medical use.
