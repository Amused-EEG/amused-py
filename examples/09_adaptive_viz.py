"""
Example 9: Adaptive Rate Visualization
Different update rates for different signals for optimal display

- EEG: Lower update rate with smoothing (too fast/noisy to be useful raw)
- PPG: Medium update rate to see pulse waveform
- Heart Rate: High update rate for instant feedback
- IMU: Medium update rate for motion detection
"""

import asyncio
import sys
import os
import threading
import numpy as np
from datetime import datetime
from collections import deque

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Fix Windows Qt/Bleak conflict
try:
    from bleak.backends.winrt.util import allow_sta
    allow_sta()
except ImportError:
    pass

# Import PyQtGraph
try:
    import pyqtgraph as pg
    from pyqtgraph.Qt import QtCore, QtWidgets, QtGui
except ImportError:
    print("PyQtGraph not installed! Install with: pip install pyqtgraph PyQt5")
    sys.exit(1)

from muse_stream_client import MuseStreamClient
from muse_discovery import find_muse_devices

# Update rates for different signals
EEG_UPDATE_HZ = 10    # EEG updates slowly (smoothed anyway)
PPG_UPDATE_HZ = 30    # PPG updates faster to see waveform
HR_UPDATE_HZ = 2      # Heart rate updates frequently for instant feedback
IMU_UPDATE_HZ = 20    # IMU for motion detection

# Display settings
EEG_WINDOW_SAMPLES = 256   # Show ~1 second at 256Hz
PPG_WINDOW_SAMPLES = 128   # Show ~2 seconds at 64Hz  
HR_HISTORY_POINTS = 120    # Show 2 minutes of HR history
IMU_WINDOW_SAMPLES = 100   # Show ~2 seconds at 52Hz

# Data buffers
eeg_buffers = {ch: deque(maxlen=EEG_WINDOW_SAMPLES) for ch in 
              ['TP9', 'AF7', 'AF8', 'TP10', 'FPz', 'AUX_R', 'AUX_L']}
ppg_buffer = deque(maxlen=PPG_WINDOW_SAMPLES)
heart_rates = deque(maxlen=HR_HISTORY_POINTS)
current_hr = 0.0
imu_accel = {'x': deque(maxlen=IMU_WINDOW_SAMPLES), 
             'y': deque(maxlen=IMU_WINDOW_SAMPLES), 
             'z': deque(maxlen=IMU_WINDOW_SAMPLES)}

# Thread-safe data exchange
import queue
eeg_queue = queue.Queue()
ppg_queue = queue.Queue()
hr_queue = queue.Queue()
imu_queue = queue.Queue()

# Data callbacks
def process_eeg(data):
    """Queue EEG data"""
    if 'channels' in data:
        eeg_queue.put(data['channels'])

def process_ppg(data):
    """Queue PPG data"""
    if 'samples' in data:
        ppg_queue.put(data['samples'])

def process_heart_rate(hr):
    """Queue heart rate"""
    hr_queue.put(hr)

def process_imu(data):
    """Queue IMU data"""
    if 'accel' in data:
        imu_queue.put(('accel', data['accel']))

async def stream_data(device_address: str, duration: int):
    """Stream data from Muse device"""
    client = MuseStreamClient(
        save_raw=False,
        decode_realtime=True,
        verbose=False
    )
    
    client.on_eeg(process_eeg)
    client.on_ppg(process_ppg)
    client.on_heart_rate(process_heart_rate)
    client.on_imu(process_imu)
    
    print(f"Connecting to {device_address}...")
    success = await client.connect_and_stream(
        device_address,
        duration_seconds=duration,
        preset='p1035'
    )
    
    print("Stream complete" if success else "Stream failed")

def update_eeg():
    """Update EEG plots - runs at EEG_UPDATE_HZ"""
    # Process EEG data
    processed = 0
    while processed < 10:
        try:
            channels = eeg_queue.get_nowait()
            for channel, samples in channels.items():
                if channel in eeg_buffers:
                    # Downsample if too many samples
                    if len(samples) > 5:
                        samples = samples[::2]  # Take every other sample
                    eeg_buffers[channel].extend(samples[:3])
            processed += 1
        except queue.Empty:
            break
    
    # Update plots
    for i, (channel, buffer) in enumerate(eeg_buffers.items()):
        if len(buffer) > 10:
            # Apply smoothing
            data = np.array(buffer)
            kernel = np.ones(5) / 5
            smoothed = np.convolve(data, kernel, mode='valid')
            eeg_curves[i].setData(smoothed)

def update_ppg():
    """Update PPG plot - runs at PPG_UPDATE_HZ"""
    # Process PPG data
    processed = 0
    while processed < 5:
        try:
            samples = ppg_queue.get_nowait()
            if isinstance(samples, list) and len(samples) > 0:
                # Add individual samples for waveform detail
                for s in samples[:3]:  # Limit samples per update
                    if isinstance(s, (int, float)):
                        ppg_buffer.append(s)
            processed += 1
        except queue.Empty:
            break
    
    # Update plot
    if len(ppg_buffer) > 0:
        ppg_curve.setData(np.array(ppg_buffer))

def update_heart_rate():
    """Update heart rate display - runs at HR_UPDATE_HZ"""
    global current_hr
    
    # Get latest heart rate
    latest_hr = None
    while True:
        try:
            latest_hr = hr_queue.get_nowait()
        except queue.Empty:
            break
    
    if latest_hr is not None:
        current_hr = latest_hr
        heart_rates.append(latest_hr)
    
    # Update display
    if current_hr > 0:
        # Update text with current HR
        hr_text.setText(f"{current_hr:.0f}")
        
        # Update history plot
        if len(heart_rates) > 0:
            hr_curve.setData(np.array(heart_rates))
            
        # Update color based on HR zones
        if current_hr < 60:
            color = '#00BCD4'  # Cyan for low
        elif current_hr < 100:
            color = '#4CAF50'  # Green for normal
        elif current_hr < 120:
            color = '#FFC107'  # Amber for elevated
        else:
            color = '#F44336'  # Red for high
        
        hr_text.setColor(color)

def update_imu():
    """Update IMU plots - runs at IMU_UPDATE_HZ"""
    # Process IMU data
    processed = 0
    while processed < 5:
        try:
            data_type, data = imu_queue.get_nowait()
            if data_type == 'accel' and len(data) >= 3:
                imu_accel['x'].append(data[0])
                imu_accel['y'].append(data[1])
                imu_accel['z'].append(data[2])
            processed += 1
        except queue.Empty:
            break
    
    # Update plots
    for i, axis in enumerate(['x', 'y', 'z']):
        if len(imu_accel[axis]) > 0:
            imu_curves[i].setData(np.array(imu_accel[axis]))

def main():
    """Main function"""
    global eeg_curves, ppg_curve, hr_curve, hr_text, imu_curves
    
    print("Adaptive Rate Muse Visualization")
    print("=" * 60)
    
    # Find device
    print("\nSearching for Muse devices...")
    devices = asyncio.run(find_muse_devices(timeout=5.0))
    
    if not devices:
        print("No devices found!")
        return
    
    device = devices[0]
    print(f"Found: {device.name}")
    
    # Create Qt application
    app = QtWidgets.QApplication([])
    
    # Configure for balance of quality and performance
    pg.setConfigOptions(antialias=True)
    
    # Create window
    win = pg.GraphicsLayoutWidget(show=True, title="Adaptive Muse Visualization")
    win.resize(1400, 900)
    
    # === EEG Section (Left) ===
    win.addLabel("EEG Channels (smoothed)", row=0, col=0, colspan=2)
    eeg_curves = []
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFA726', '#AB47BC', '#66BB6A']
    
    for i, (channel, color) in enumerate(zip(eeg_buffers.keys(), colors)):
        row = (i // 2) + 1
        col = i % 2
        p = win.addPlot(title=channel, row=row, col=col)
        p.setYRange(-500, 500)
        p.showGrid(y=True, alpha=0.2)
        p.hideAxis('bottom')
        curve = p.plot(pen=pg.mkPen(color=color, width=2))
        eeg_curves.append(curve)
    
    # === Heart Rate Section (Right Top) ===
    win.addLabel("Heart Rate Monitor", row=0, col=2, colspan=2)
    
    # Big HR display
    hr_widget = win.addViewBox(row=1, col=2, colspan=2, rowspan=2)
    hr_text = pg.TextItem(text="--", anchor=(0.5, 0.5))
    hr_text.setFont(QtGui.QFont('Arial', 72, QtGui.QFont.Bold))
    hr_widget.addItem(hr_text)
    hr_text.setPos(0.5, 0.5)
    
    # HR history plot
    hr_plot = win.addPlot(title="Heart Rate History (2 min)", row=3, col=2, colspan=2)
    hr_plot.setLabel('left', 'BPM')
    hr_plot.setYRange(40, 140)
    hr_plot.showGrid(y=True, alpha=0.3)
    hr_curve = hr_plot.plot(pen=pg.mkPen(color='#E91E63', width=3))
    
    # === PPG Section (Right Middle) ===
    ppg_plot = win.addPlot(title="PPG Waveform", row=4, col=2, colspan=2)
    ppg_plot.setLabel('left', 'PPG')
    ppg_plot.showGrid(y=True, alpha=0.3)
    ppg_curve = ppg_plot.plot(pen=pg.mkPen(color='#FF5252', width=2))
    
    # === IMU Section (Bottom) ===
    win.addLabel("Motion (Accelerometer)", row=5, col=0, colspan=4)
    imu_plot = win.addPlot(title="3-Axis Acceleration", row=6, col=0, colspan=4)
    imu_plot.setLabel('left', 'Accel (g)')
    imu_plot.showGrid(y=True, alpha=0.3)
    imu_plot.addLegend()
    
    imu_curves = []
    imu_colors = ['#FF5252', '#69F0AE', '#448AFF']
    for color, axis in zip(imu_colors, ['X', 'Y', 'Z']):
        curve = imu_plot.plot(pen=pg.mkPen(color=color, width=2), name=axis)
        imu_curves.append(curve)
    
    # Create multiple timers for different update rates
    eeg_timer = QtCore.QTimer()
    eeg_timer.timeout.connect(update_eeg)
    eeg_timer.start(1000 // EEG_UPDATE_HZ)
    
    ppg_timer = QtCore.QTimer()
    ppg_timer.timeout.connect(update_ppg)
    ppg_timer.start(1000 // PPG_UPDATE_HZ)
    
    hr_timer = QtCore.QTimer()
    hr_timer.timeout.connect(update_heart_rate)
    hr_timer.start(1000 // HR_UPDATE_HZ)
    
    imu_timer = QtCore.QTimer()
    imu_timer.timeout.connect(update_imu)
    imu_timer.start(1000 // IMU_UPDATE_HZ)
    
    # Start streaming
    print(f"\nStarting stream...")
    stream_thread = threading.Thread(
        target=lambda: asyncio.run(stream_data(device.address, 300)),
        daemon=True
    )
    stream_thread.start()
    
    print("Visualization running. Close window to stop.\n")
    print("Update rates:")
    print(f"  EEG: {EEG_UPDATE_HZ} Hz (smoothed)")
    print(f"  PPG: {PPG_UPDATE_HZ} Hz (waveform)")
    print(f"  Heart Rate: {HR_UPDATE_HZ} Hz (instant)")
    print(f"  IMU: {IMU_UPDATE_HZ} Hz (motion)")
    
    # Run app
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