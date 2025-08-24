# Amused - A Muse S Direct BLE Implementation

**The first open-source BLE protocol implementation for Muse S headsets**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Finally!** Direct BLE connection to Muse S without proprietary SDKs. We're quite *amused* that we cracked the protocol nobody else has published online!

## 🎉 The Real Story

We reverse-engineered the BLE communication from scratch to provide researchers with full control over their Muse S devices. 

**Key breakthrough:** The `dc001` command must be sent TWICE to start streaming - a critical detail not in any documentation!

## Features

- **EEG Streaming**: 7 channels at 256 Hz (TP9, AF7, AF8, TP10, FPz, AUX_R, AUX_L)
- **PPG Heart Rate**: Real-time HR and HRV from photoplethysmography sensors  
- **IMU Motion**: 9-axis accelerometer + gyroscope
- **Binary Recording**: 10x more efficient than CSV with replay capability
- **Real-time Visualization**: Multiple visualization options including band powers
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

### Visualization Dependencies (Optional)

```bash
# For PyQtGraph visualizations
pip install pyqtgraph PyQt5

# For all visualization features
pip install -r requirements-viz.txt
```

## Quick Start

```python
import asyncio
from muse_stream_client import MuseStreamClient
from muse_discovery import find_muse_devices

async def stream():
    # Find Muse devices
    devices = await find_muse_devices()
    if not devices:
        print("No Muse device found!")
        return
    
    device = devices[0]
    print(f"Found: {device.name}")
    
    # Create streaming client
    client = MuseStreamClient(
        save_raw=True,      # Save to binary file
        decode_realtime=True # Decode in real-time
    )
    
    # Stream for 30 seconds
    await client.connect_and_stream(
        device.address,
        duration_seconds=30,
        preset='p1035'  # Full sensor mode
    )
    
    summary = client.get_summary()
    print(f"Collected {summary['packets_received']} packets")

asyncio.run(stream())
```

## Core Components

### `MuseStreamClient`
The main streaming client for real-time data collection:
- Connects to Muse S via BLE
- Streams all sensor data (EEG, PPG, IMU)
- Optional binary recording
- Real-time callbacks for data processing

### `MuseRawStream`
Binary data storage and retrieval:
- Efficient binary format (10x smaller than CSV)
- Fast read/write operations
- Packet-level access with timestamps

### `MuseRealtimeDecoder`
Real-time packet decoding:
- Decodes BLE packets on-the-fly
- Extracts EEG, PPG, IMU data
- Calculates heart rate from PPG
- Minimal latency

### `MuseReplayPlayer`
Replay recorded sessions:
- Play back binary recordings
- Variable speed playback
- Same callback interface as live streaming

## Usage Examples

### 1. Basic Streaming
```python
# See examples/01_basic_streaming.py
from muse_stream_client import MuseStreamClient
from muse_discovery import find_muse_devices

client = MuseStreamClient(
    save_raw=False,  # Don't save, just stream
    decode_realtime=True,
    verbose=True
)

devices = await find_muse_devices()
if devices:
    await client.connect_and_stream(
        devices[0].address,
        duration_seconds=30,
        preset='p1035'
    )
```

### 2. Recording to Binary
```python
# See examples/02_full_sensors.py
client = MuseStreamClient(
    save_raw=True,  # Enable binary saving
    data_dir="muse_data"
)

# Records all sensors to binary file
await client.connect_and_stream(
    device.address,
    duration_seconds=60,
    preset='p1035'
)
```

### 3. Parsing Recorded Data
```python
# See examples/03_parse_data.py
from muse_raw_stream import MuseRawStream
from muse_realtime_decoder import MuseRealtimeDecoder

stream = MuseRawStream("muse_data/recording.bin")
stream.open_read()

decoder = MuseRealtimeDecoder()
for packet in stream.read_packets():
    decoded = decoder.decode(packet.data, packet.timestamp)
    if decoded.eeg:
        print(f"EEG data: {decoded.eeg}")
    if decoded.heart_rate:
        print(f"Heart rate: {decoded.heart_rate:.0f} BPM")
```

### 4. Real-time Callbacks
```python
# See examples/04_stream_with_callbacks.py
def process_eeg(data):
    channels = data['channels']
    # Process EEG data in real-time
    print(f"Got EEG from {len(channels)} channels")

def process_heart_rate(hr):
    print(f"Heart Rate: {hr:.0f} BPM")

client = MuseStreamClient()
client.on_eeg(process_eeg)
client.on_heart_rate(process_heart_rate)

await client.connect_and_stream(device.address)
```

### 5. Visualization Examples

#### Band Power Visualization
```python
# See examples/07_lsl_style_viz.py
# Shows Delta, Theta, Alpha, Beta, Gamma bands
# Stable bar graphs without jumpy waveforms
```

#### Simple Frequency Display
```python
# See examples/09_frequency_display.py
# Just shows dominant frequency (Hz) for each channel
# Clean, large numbers - no graphs
```

#### Heart Rate Monitor
```python
# See examples/06_heart_monitor.py
# Dedicated heart rate display with zones
# Shows current BPM, trend, and history
```

## Protocol Details

The Muse S uses Bluetooth Low Energy (BLE) with a custom protocol:

### Connection Sequence
1. Connect to device
2. Enable notifications on control characteristic
3. Send halt command (`0x02680a`)
4. Set preset (`p1035` for full sensors)
5. Enable sensor notifications
6. Send start command (`dc001`) **TWICE**
7. Stream data

### Presets
- `p21`: Basic EEG only
- `p1034`: Sleep mode preset 1
- `p1035`: Full sensor mode (recommended)

### Packet Types
- `0xDF`: EEG + PPG combined
- `0xF4`: IMU (accelerometer + gyroscope)
- `0xDB`, `0xD9`: Mixed sensor data

## Troubleshooting

### No data received?
- Ensure `dc001` is sent twice (critical!)
- Check Bluetooth is enabled
- Make sure Muse S is in pairing mode
- Try preset `p1035` for full sensor access

### Heart rate not showing?
- Heart rate requires ~2 seconds of PPG data
- Check PPG sensor contact with skin
- Use preset `p1035` which enables PPG

### Qt/Visualization errors?
- Install PyQt5: `pip install PyQt5 pyqtgraph`
- On Windows, the library handles Qt/asyncio conflicts automatically
- Try examples 06 or 09 for simpler visualizations

## Examples Directory

The `examples/` folder contains working examples:

1. `01_basic_streaming.py` - Simple EEG streaming
2. `02_full_sensors.py` - Record all sensors to binary
3. `03_parse_data.py` - Parse binary recordings
4. `04_stream_with_callbacks.py` - Real-time processing
5. `05_save_and_replay.py` - Record and replay sessions
6. `06_heart_monitor.py` - Clean heart rate display
7. `07_lsl_style_viz.py` - LSL-style band power visualization
8. `09_frequency_display.py` - Simple Hz display for each channel

## Contributing

This is the first open implementation! Areas to explore:
- Additional sensor modes
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

**Note**: Research software for educational purposes. Probably not for medical use.