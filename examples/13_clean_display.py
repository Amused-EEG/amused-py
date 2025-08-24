"""
Example 13: Clean Simple Display
Minimal, clean visualization focusing on what matters

Shows:
- Brain state indicator (based on alpha/beta waves)
- Heart rate (calculated from PPG if needed)
- Simple status indicators
"""

import asyncio
import sys
import os
import threading
import numpy as np
from collections import deque
from scipy import signal

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

# Global state
brain_state = "WAITING"
heart_rate = 0
heart_rate_history = deque(maxlen=60)
ppg_buffer = deque(maxlen=320)  # 5 seconds at 64Hz for HR calculation
eeg_alpha_power = 0
eeg_beta_power = 0

import queue
data_queue = queue.Queue()

def calculate_heart_rate_from_ppg(ppg_data):
    """Calculate heart rate from PPG signal"""
    if len(ppg_data) < 128:
        return None
    
    try:
        # Convert to numpy array
        ppg_signal = np.array(ppg_data)
        
        # Simple bandpass filter (0.5-4 Hz for heart rate)
        b, a = signal.butter(2, [0.5, 4], btype='band', fs=64)
        filtered = signal.filtfilt(b, a, ppg_signal)
        
        # Find peaks
        peaks, _ = signal.find_peaks(filtered, distance=32)  # Min 32 samples between peaks
        
        if len(peaks) > 1:
            # Calculate heart rate from peak intervals
            intervals = np.diff(peaks) / 64.0  # Convert to seconds
            hr = 60.0 / np.mean(intervals)
            
            if 40 < hr < 180:  # Reasonable range
                return hr
    except:
        pass
    
    return None

def process_eeg(data):
    if 'channels' in data:
        # Use frontal channels for brain state
        frontal_data = []
        for ch in ['AF7', 'AF8', 'FPz']:
            if ch in data['channels']:
                frontal_data.extend(data['channels'][ch])
        
        if frontal_data:
            data_queue.put(('eeg', frontal_data))

def process_ppg(data):
    if 'samples' in data and len(data['samples']) > 0:
        data_queue.put(('ppg', data['samples']))

def process_heart_rate(hr):
    if hr and hr > 0:
        data_queue.put(('hr', hr))

async def stream_data(device_address: str):
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
    
    if success:
        print("Streaming complete")
    else:
        print("Streaming failed")

def update_display():
    """Update the display"""
    global brain_state, heart_rate, eeg_alpha_power, eeg_beta_power
    
    eeg_samples = []
    
    # Process queued data
    for _ in range(50):
        try:
            data_type, data = data_queue.get_nowait()
            
            if data_type == 'eeg':
                eeg_samples.extend(data)
            
            elif data_type == 'ppg':
                # Add to PPG buffer for HR calculation
                ppg_buffer.extend(data)
                
                # Try to calculate HR from PPG if we have enough data
                if len(ppg_buffer) >= 128:
                    calculated_hr = calculate_heart_rate_from_ppg(list(ppg_buffer))
                    if calculated_hr:
                        heart_rate = calculated_hr
                        heart_rate_history.append(calculated_hr)
            
            elif data_type == 'hr':
                # Direct heart rate from decoder
                heart_rate = data
                heart_rate_history.append(data)
                
        except queue.Empty:
            break
    
    # Update brain state from EEG
    if len(eeg_samples) >= 256:
        try:
            # FFT for frequency analysis
            fft = np.abs(np.fft.rfft(eeg_samples))
            freqs = np.fft.rfftfreq(len(eeg_samples), 1/256)
            
            # Calculate band powers
            alpha_mask = (freqs >= 8) & (freqs < 12)
            beta_mask = (freqs >= 12) & (freqs < 30)
            
            if any(alpha_mask):
                eeg_alpha_power = np.mean(fft[alpha_mask])
            if any(beta_mask):
                eeg_beta_power = np.mean(fft[beta_mask])
            
            # Determine state
            if eeg_alpha_power > eeg_beta_power * 1.5:
                brain_state = "RELAXED"
                state_color = '#4CAF50'
                state_icon = "😌"
            elif eeg_beta_power > eeg_alpha_power * 1.5:
                brain_state = "FOCUSED"
                state_color = '#2196F3'
                state_icon = "🎯"
            else:
                brain_state = "NEUTRAL"
                state_color = '#FFC107'
                state_icon = "😐"
            
            brain_text.setText(f"{state_icon}\n{brain_state}")
            brain_text.setColor(state_color)
            
        except Exception as e:
            print(f"EEG processing error: {e}")
    
    # Update heart rate display
    if heart_rate > 0:
        hr_text.setText(f"{heart_rate:.0f}")
        
        # Color based on HR zones
        if heart_rate < 60:
            hr_color = '#00BCD4'  # Low
        elif heart_rate < 90:
            hr_color = '#4CAF50'  # Normal
        elif heart_rate < 120:
            hr_color = '#FFC107'  # Elevated
        else:
            hr_color = '#F44336'  # High
        
        hr_text.setColor(hr_color)
        
        # Show trend arrow
        if len(heart_rate_history) > 2:
            recent_avg = np.mean(list(heart_rate_history)[-5:])
            older_avg = np.mean(list(heart_rate_history)[-10:-5])
            
            if recent_avg > older_avg + 2:
                trend_text.setText("↑")
            elif recent_avg < older_avg - 2:
                trend_text.setText("↓")
            else:
                trend_text.setText("→")
    
    # Update status
    status_parts = []
    if eeg_alpha_power > 0 or eeg_beta_power > 0:
        status_parts.append("EEG ✓")
    if heart_rate > 0:
        status_parts.append("HR ✓")
    if len(ppg_buffer) > 0:
        status_parts.append("PPG ✓")
    
    status_text.setText(" | ".join(status_parts) if status_parts else "Waiting for data...")

def main():
    global brain_text, hr_text, trend_text, status_text
    
    print("Clean Muse Display")
    print("=" * 60)
    
    # Find device
    devices = asyncio.run(find_muse_devices(timeout=5.0))
    if not devices:
        print("No Muse device found!")
        return
    
    device = devices[0]
    print(f"Found: {device.name}\n")
    
    # Create app
    app = QtWidgets.QApplication([])
    
    # Window
    win = pg.GraphicsLayoutWidget(show=True, title="Muse Monitor")
    win.resize(600, 400)
    
    # Title
    win.addLabel("MUSE MONITOR", row=0, col=0, colspan=3)
    
    # Brain state section
    win.addLabel("Brain State", row=1, col=0)
    brain_box = win.addViewBox(row=2, col=0, rowspan=2)
    brain_text = pg.TextItem(text="---\nWAITING", anchor=(0.5, 0.5))
    brain_text.setFont(QtGui.QFont('Arial', 24, QtGui.QFont.Bold))
    brain_box.addItem(brain_text)
    brain_text.setPos(0.5, 0.5)
    
    # Heart rate section
    win.addLabel("Heart Rate", row=1, col=1)
    hr_box = win.addViewBox(row=2, col=1, rowspan=2)
    hr_text = pg.TextItem(text="--", anchor=(0.5, 0.5))
    hr_text.setFont(QtGui.QFont('Arial', 48, QtGui.QFont.Bold))
    hr_text.setColor('#E91E63')
    hr_box.addItem(hr_text)
    hr_text.setPos(0.5, 0.5)
    
    # Add BPM label
    bpm_box = win.addViewBox(row=3, col=1)
    bpm_label = pg.TextItem(text="BPM", anchor=(0.5, 0))
    bpm_label.setFont(QtGui.QFont('Arial', 12))
    bpm_box.addItem(bpm_label)
    bpm_label.setPos(0.5, 0.8)
    
    # Trend
    win.addLabel("Trend", row=1, col=2)
    trend_box = win.addViewBox(row=2, col=2, rowspan=2)
    trend_text = pg.TextItem(text="→", anchor=(0.5, 0.5))
    trend_text.setFont(QtGui.QFont('Arial', 36))
    trend_text.setColor('#9E9E9E')
    trend_box.addItem(trend_text)
    trend_text.setPos(0.5, 0.5)
    
    # Status bar
    status_text = win.addLabel("Connecting...", row=4, col=0, colspan=3)
    
    # Timer
    timer = QtCore.QTimer()
    timer.timeout.connect(update_display)
    timer.start(100)  # 10 Hz updates
    
    # Start streaming
    stream_thread = threading.Thread(
        target=lambda: asyncio.run(stream_data(device.address)),
        daemon=True
    )
    stream_thread.start()
    
    print("Monitoring...")
    print("Close window to stop\n")
    
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