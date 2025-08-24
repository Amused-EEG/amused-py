"""
Example 11: Brain Wave Frequency Visualization
Simple, meaningful visualization showing dominant brain wave frequencies

Instead of noisy raw EEG, this shows:
- Dominant frequency at each sensor (Delta, Theta, Alpha, Beta, Gamma)
- Heart rate as a big number
- PPG pulse indicator
- Simple, clean, useful
"""

import asyncio
import sys
import os
import threading
import numpy as np
from collections import deque

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Fix Windows conflict
try:
    from bleak.backends.winrt.util import allow_sta
    allow_sta()
except ImportError:
    pass

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets, QtGui

from muse_stream_client import MuseStreamClient
from muse_discovery import find_muse_devices

# Brain wave bands (Hz)
BANDS = {
    'Delta': (0.5, 4, '#9C27B0'),   # Deep sleep
    'Theta': (4, 8, '#3F51B5'),     # Meditation
    'Alpha': (8, 12, '#4CAF50'),    # Relaxed
    'Beta': (12, 30, '#FF9800'),    # Active thinking
    'Gamma': (30, 60, '#F44336')    # High concentration
}

# Simple data storage
eeg_channels = ['TP9', 'AF7', 'AF8', 'TP10', 'FPz', 'AUX_R', 'AUX_L']
eeg_buffers = {ch: deque(maxlen=256) for ch in eeg_channels}  # 1 second at 256Hz
heart_rate = 0.0
ppg_pulse = 0.0

# Data queue
import queue
data_queue = queue.Queue()

def get_dominant_frequency(data):
    """Get dominant frequency from EEG data using FFT"""
    if len(data) < 128:
        return 0.0, "---"
    
    # FFT to get frequencies
    fft = np.abs(np.fft.rfft(data))
    freqs = np.fft.rfftfreq(len(data), 1/256)  # 256 Hz sampling
    
    # Find dominant frequency between 0.5 and 60 Hz
    mask = (freqs >= 0.5) & (freqs <= 60)
    if not any(mask):
        return 0.0, "---"
    
    freqs_masked = freqs[mask]
    fft_masked = fft[mask]
    
    # Get peak frequency
    peak_idx = np.argmax(fft_masked)
    peak_freq = freqs_masked[peak_idx]
    
    # Determine band
    for band_name, (low, high, color) in BANDS.items():
        if low <= peak_freq < high:
            return peak_freq, band_name
    
    return peak_freq, "---"

# Callbacks
def process_eeg(data):
    if 'channels' in data:
        data_queue.put(('eeg', data['channels']))

def process_ppg(data):
    if 'samples' in data:
        data_queue.put(('ppg', data['samples']))

def process_heart_rate(hr):
    data_queue.put(('hr', hr))

async def stream_data(device_address: str):
    """Stream from Muse"""
    client = MuseStreamClient(
        save_raw=False,
        decode_realtime=True,
        verbose=False
    )
    
    client.on_eeg(process_eeg)
    client.on_ppg(process_ppg)
    client.on_heart_rate(process_heart_rate)
    
    print(f"Connecting to {device_address}...")
    success = await client.connect_and_stream(
        device_address,
        duration_seconds=300,
        preset='p1035'
    )
    print("Done streaming" if success else "Failed")

def update_display():
    """Update the simple display"""
    global heart_rate, ppg_pulse
    
    # Process data
    processed = 0
    while processed < 50:
        try:
            data_type, data = data_queue.get_nowait()
            
            if data_type == 'eeg':
                for channel, samples in data.items():
                    if channel in eeg_buffers:
                        eeg_buffers[channel].extend(samples)
            
            elif data_type == 'ppg':
                if len(data) > 0:
                    ppg_pulse = np.mean(data)
            
            elif data_type == 'hr':
                heart_rate = data
            
            processed += 1
        except queue.Empty:
            break
    
    # Update brain wave displays
    for i, channel in enumerate(eeg_channels):
        if len(eeg_buffers[channel]) >= 128:
            freq, band = get_dominant_frequency(list(eeg_buffers[channel]))
            
            # Update text
            if band != "---":
                text = f"{band}\n{freq:.1f} Hz"
                color = BANDS[band][2]
            else:
                text = "---\n---"
                color = '#666666'
            
            channel_labels[i].setText(text)
            channel_labels[i].setColor(color)
    
    # Update heart rate
    if heart_rate > 0:
        hr_label.setText(f"{heart_rate:.0f}")
        
        # Pulse effect on PPG indicator
        if ppg_pulse > 0:
            # Make the heart icon pulse
            scale = 1.0 + (ppg_pulse / 1000000.0)  # Normalize PPG value
            heart_icon.setScale(scale)
    
    # Simple status
    status_label.setText(f"EEG: {sum(len(b) > 0 for b in eeg_buffers.values())}/7 active | "
                        f"HR: {'✓' if heart_rate > 0 else '✗'}")

def main():
    """Main function"""
    global channel_labels, hr_label, heart_icon, status_label
    
    print("Brain Wave Visualization")
    print("=" * 60)
    
    # Find device
    print("\nSearching for Muse...")
    devices = asyncio.run(find_muse_devices(timeout=5.0))
    
    if not devices:
        print("No device found!")
        return
    
    device = devices[0]
    print(f"Found: {device.name}")
    
    # Create app
    app = QtWidgets.QApplication([])
    
    # Simple window
    win = pg.GraphicsLayoutWidget(show=True, title="Muse Brain Waves")
    win.resize(800, 600)
    
    # Title
    win.addLabel("Brain Wave Frequencies", row=0, col=0, colspan=4)
    
    # EEG channel displays - simple grid
    channel_labels = []
    positions = [
        (1, 0, 'TP9'),   # Left temporal
        (1, 1, 'AF7'),   # Left frontal
        (1, 2, 'AF8'),   # Right frontal
        (1, 3, 'TP10'),  # Right temporal
        (2, 1, 'FPz'),   # Front center
        (2, 0, 'AUX_R'), # Right aux
        (2, 2, 'AUX_L')  # Left aux
    ]
    
    for row, col, channel in positions:
        # Channel name
        win.addLabel(channel, row=row*2, col=col)
        
        # Frequency display
        vb = win.addViewBox(row=row*2+1, col=col)
        label = pg.TextItem(text="---\n---", anchor=(0.5, 0.5))
        label.setFont(QtGui.QFont('Arial', 18, QtGui.QFont.Bold))
        vb.addItem(label)
        label.setPos(0.5, 0.5)
        channel_labels.append(label)
    
    # Divider
    win.addLabel("─" * 40, row=5, col=0, colspan=4)
    
    # Heart rate section
    win.addLabel("Heart Rate", row=6, col=0, colspan=2)
    
    # Big HR display
    hr_box = win.addViewBox(row=7, col=0, colspan=2, rowspan=2)
    hr_label = pg.TextItem(text="--", anchor=(0.5, 0.5))
    hr_label.setFont(QtGui.QFont('Arial', 64, QtGui.QFont.Bold))
    hr_label.setColor('#E91E63')
    hr_box.addItem(hr_label)
    hr_label.setPos(0.5, 0.5)
    
    # Heart icon (pulses with PPG)
    heart_box = win.addViewBox(row=7, col=2, colspan=2, rowspan=2)
    heart_icon = pg.TextItem(text="❤", anchor=(0.5, 0.5))
    heart_icon.setFont(QtGui.QFont('Arial', 48))
    heart_icon.setColor('#FF5252')
    heart_box.addItem(heart_icon)
    heart_icon.setPos(0.5, 0.5)
    
    # Status bar
    status_label = win.addLabel("Connecting...", row=9, col=0, colspan=4)
    
    # Legend
    legend_text = " | ".join([f"{band}: {low}-{high}Hz" 
                              for band, (low, high, _) in BANDS.items()])
    win.addLabel(legend_text, row=10, col=0, colspan=4)
    
    # Timer for updates
    timer = QtCore.QTimer()
    timer.timeout.connect(update_display)
    timer.start(100)  # 10 Hz is plenty for frequency display
    
    # Start streaming
    stream_thread = threading.Thread(
        target=lambda: asyncio.run(stream_data(device.address)),
        daemon=True
    )
    stream_thread.start()
    
    print("\nShowing dominant brain wave frequencies at each sensor")
    print("Close window to stop\n")
    
    # Run
    app.exec_()
    print("\nDone")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()