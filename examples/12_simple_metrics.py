"""
Example 12: Ultra-Simple Metrics Display
Just the useful stuff - no complex graphs

Shows:
- Overall brain state (relaxed/focused/active)
- Heart rate with trend
- Motion detection
- Battery level
"""

import asyncio
import sys
import os
import threading
import numpy as np
from collections import deque

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from bleak.backends.winrt.util import allow_sta
    allow_sta()
except ImportError:
    pass

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets, QtGui

from muse_stream_client import MuseStreamClient
from muse_discovery import find_muse_devices

# Simple storage
eeg_power = {'alpha': 0, 'beta': 0, 'theta': 0}  # Brain wave power
heart_rate = 0
hr_history = deque(maxlen=30)  # Last 30 HR values
ppg_history = deque(maxlen=320)  # 5 seconds of PPG at 64Hz for HR calc
motion_level = 0
battery = 100

import queue
data_queue = queue.Queue()

def calculate_band_power(data, band_range):
    """Calculate power in frequency band"""
    if len(data) < 128:
        return 0
    
    fft = np.abs(np.fft.rfft(data))
    freqs = np.fft.rfftfreq(len(data), 1/256)
    
    # Get power in band
    mask = (freqs >= band_range[0]) & (freqs < band_range[1])
    if any(mask):
        return np.mean(fft[mask])
    return 0

def process_eeg(data):
    if 'channels' in data:
        # Just use frontal channels for overall state
        frontal = []
        for ch in ['AF7', 'AF8', 'FPz']:
            if ch in data['channels']:
                frontal.extend(data['channels'][ch])
        if frontal:
            data_queue.put(('eeg', frontal))

def process_ppg(data):
    if 'samples' in data and data['samples']:
        # PPG data exists
        samples = data['samples']
        if isinstance(samples, list) and len(samples) > 0:
            print(f"PPG: {len(samples)} samples")  # Debug
            data_queue.put(('ppg', samples))

def process_heart_rate(hr):
    if hr and hr > 0:  # Only process valid heart rates
        print(f"HR: {hr:.1f} BPM")  # Debug
        data_queue.put(('hr', hr))

def process_imu(data):
    if 'accel' in data and len(data['accel']) >= 3:
        # Calculate magnitude of acceleration vector
        accel_vals = data['accel'][:3]
        magnitude = np.sqrt(sum(x**2 for x in accel_vals))
        
        # Track change in magnitude over time
        if not hasattr(process_imu, 'last_mag'):
            process_imu.last_mag = magnitude
            process_imu.motion_buffer = []
        
        # Calculate change from last reading
        change = abs(magnitude - process_imu.last_mag)
        process_imu.last_mag = magnitude
        
        # Keep buffer of recent changes (smaller for faster response)
        process_imu.motion_buffer.append(change)
        if len(process_imu.motion_buffer) > 3:  # Only keep last 3 samples
            process_imu.motion_buffer.pop(0)
        
        # Use max of recent changes for instant response
        motion = max(process_imu.motion_buffer) if process_imu.motion_buffer else 0
        
        print(f"Motion: mag={magnitude:.0f}, change={change:.1f}, avg={motion:.1f}")  # Debug
        data_queue.put(('motion', motion))

async def stream_data(device_address: str):
    client = MuseStreamClient(
        save_raw=False,
        decode_realtime=True,
        verbose=False
    )
    
    client.on_eeg(process_eeg)
    client.on_ppg(process_ppg)  # Add PPG callback
    client.on_heart_rate(process_heart_rate)
    client.on_imu(process_imu)
    
    print(f"Connecting...")
    await client.connect_and_stream(
        device_address,
        duration_seconds=300,
        preset='p1035'
    )

def update_display():
    """Update simple metrics"""
    global heart_rate, motion_level, ppg_history
    
    eeg_buffer = []
    
    # Get latest data
    processed = 0
    while processed < 20:
        try:
            data_type, data = data_queue.get_nowait()
            
            if data_type == 'eeg':
                eeg_buffer.extend(data)
            elif data_type == 'ppg':
                # Store PPG for potential HR calculation
                ppg_history.extend(data)
            elif data_type == 'hr':
                heart_rate = data
                hr_history.append(data)
                print(f"Display HR: {heart_rate:.1f}")  # Debug
            elif data_type == 'motion':
                motion_level = data
            
            processed += 1
        except queue.Empty:
            break
    
    # Calculate brain state from EEG
    if len(eeg_buffer) >= 128:
        eeg_power['alpha'] = calculate_band_power(eeg_buffer, (8, 12))
        eeg_power['beta'] = calculate_band_power(eeg_buffer, (12, 30))
        eeg_power['theta'] = calculate_band_power(eeg_buffer, (4, 8))
        
        # Determine state
        total = sum(eeg_power.values())
        if total > 0:
            alpha_ratio = eeg_power['alpha'] / total
            beta_ratio = eeg_power['beta'] / total
            
            if alpha_ratio > 0.35:  # More sensitive
                state = "😌 RELAXED"
                color = '#4CAF50'
            elif beta_ratio > 0.35:  # More sensitive
                state = "🧠 FOCUSED"
                color = '#2196F3'
            elif eeg_power['theta'] / total > 0.3:
                state = "😴 DROWSY"
                color = '#9C27B0'
            else:
                state = "💭 NEUTRAL"
                color = '#9E9E9E'
            
            brain_label.setText(state)
            brain_label.setColor(color)
    
    # Update heart rate
    if heart_rate > 0:
        hr_label.setText(f"❤ {heart_rate:.0f} BPM")
        
        # Show trend
        if len(hr_history) > 2:
            if hr_history[-1] > hr_history[-2]:
                hr_trend.setText("↑")
                hr_trend.setColor('#FF5252')
            elif hr_history[-1] < hr_history[-2]:
                hr_trend.setText("↓")
                hr_trend.setColor('#4CAF50')
            else:
                hr_trend.setText("→")
                hr_trend.setColor('#FFC107')
    else:
        # No direct HR, try to calculate from PPG
        if len(ppg_history) >= 128:
            print(f"Calculating HR from {len(ppg_history)} PPG samples")  # Debug
            # Simple peak detection
            ppg_array = np.array(list(ppg_history)[-256:])  # Last 4 seconds
            # Find peaks (simple threshold method)
            mean_val = np.mean(ppg_array)
            peaks = []
            for i in range(1, len(ppg_array)-1):
                if ppg_array[i] > mean_val and ppg_array[i] > ppg_array[i-1] and ppg_array[i] > ppg_array[i+1]:
                    peaks.append(i)
            
            if len(peaks) > 2:
                # Calculate HR from peak intervals
                intervals = np.diff(peaks) / 64.0  # 64 Hz sampling
                hr_calc = 60.0 / np.mean(intervals)
                if 40 < hr_calc < 180:
                    heart_rate = hr_calc
                    hr_label.setText(f"❤ {hr_calc:.0f} BPM*")  # * for calculated
                    print(f"Calculated HR: {hr_calc:.0f} BPM")
    
    # Update motion (based on change in accelerometer magnitude)
    if motion_level > 15:  # Significant motion (adjusted threshold)
        motion_label.setText("🏃 MOVING")
        motion_label.setColor('#FF9800')
    elif motion_level > 3:  # Slight motion (lower threshold for responsiveness)
        motion_label.setText("🚶 SLIGHT")
        motion_label.setColor('#FFC107')
    else:
        motion_label.setText("🪑 STILL")
        motion_label.setColor('#607D8B')

def main():
    global brain_label, hr_label, hr_trend, motion_label
    
    print("Simple Muse Metrics")
    print("=" * 60)
    
    # Find device
    devices = asyncio.run(find_muse_devices(timeout=3.0))  # Faster discovery
    if not devices:
        print("No device found!")
        return
    
    device = devices[0]
    print(f"Found: {device.name}\n")
    
    # Create app
    app = QtWidgets.QApplication([])
    
    # Window
    win = pg.GraphicsLayoutWidget(show=True, title="Muse Metrics")
    win.resize(400, 500)
    
    # Title
    title = win.addLabel("MUSE METRICS", row=0, col=0, colspan=2)
    title.setText("MUSE METRICS", size='20pt', bold=True)
    
    # Brain state
    win.addLabel("Brain State", row=1, col=0, colspan=2)
    brain_box = win.addViewBox(row=2, col=0, colspan=2)
    brain_label = pg.TextItem(text="---", anchor=(0.5, 0.5))
    brain_label.setFont(QtGui.QFont('Arial', 32, QtGui.QFont.Bold))
    brain_box.addItem(brain_label)
    brain_label.setPos(0.5, 0.5)
    
    # Heart rate
    win.addLabel("Heart Rate", row=3, col=0, colspan=2)
    hr_box = win.addViewBox(row=4, col=0)
    hr_label = pg.TextItem(text="❤ --", anchor=(0.5, 0.5))
    hr_label.setFont(QtGui.QFont('Arial', 28))
    hr_label.setColor('#E91E63')
    hr_box.addItem(hr_label)
    hr_label.setPos(0.5, 0.5)
    
    # HR trend
    trend_box = win.addViewBox(row=4, col=1)
    hr_trend = pg.TextItem(text="→", anchor=(0.5, 0.5))
    hr_trend.setFont(QtGui.QFont('Arial', 36))
    trend_box.addItem(hr_trend)
    hr_trend.setPos(0.5, 0.5)
    
    # Motion
    win.addLabel("Motion", row=5, col=0, colspan=2)
    motion_box = win.addViewBox(row=6, col=0, colspan=2)
    motion_label = pg.TextItem(text="---", anchor=(0.5, 0.5))
    motion_label.setFont(QtGui.QFont('Arial', 24))
    motion_box.addItem(motion_label)
    motion_label.setPos(0.5, 0.5)
    
    # Timer
    timer = QtCore.QTimer()
    timer.timeout.connect(update_display)
    timer.start(200)  # 5 Hz is enough for metrics
    
    # Start streaming
    threading.Thread(
        target=lambda: asyncio.run(stream_data(device.address)),
        daemon=True
    ).start()
    
    print("Displaying simple metrics")
    print("Close window to stop\n")
    
    app.exec_()
    print("\nDone")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")