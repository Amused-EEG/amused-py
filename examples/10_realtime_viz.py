"""
Example 10: Real-time Visualization with Unified Fast Updates
All data types update at the same high rate for true real-time display

Key features:
- Single fast update timer for all data
- Minimal processing overhead
- Direct data display without excessive smoothing
- Optimized for real-time feedback
"""

import asyncio
import sys
import os
import threading
import numpy as np
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

# Single update rate for everything - FAST!
UPDATE_HZ = 30  # 30 Hz for smooth real-time display

# Display windows
EEG_WINDOW = 512      # ~2 seconds at 256Hz
PPG_WINDOW = 256      # ~4 seconds at 64Hz  
HR_HISTORY = 200      # History points for HR
IMU_WINDOW = 200      # ~4 seconds at 52Hz

# Fast circular buffers
eeg_buffers = {ch: deque(maxlen=EEG_WINDOW) for ch in 
              ['TP9', 'AF7', 'AF8', 'TP10', 'FPz', 'AUX_R', 'AUX_L']}
ppg_buffer = deque(maxlen=PPG_WINDOW)
heart_rates = deque(maxlen=HR_HISTORY)
current_hr = 0.0
imu_data = {
    'accel_x': deque(maxlen=IMU_WINDOW),
    'accel_y': deque(maxlen=IMU_WINDOW),
    'accel_z': deque(maxlen=IMU_WINDOW)
}

# Single shared queue for all data
import queue
data_queue = queue.Queue()

# Data callbacks - just queue everything
def process_eeg(data):
    if 'channels' in data:
        data_queue.put(('eeg', data['channels']))

def process_ppg(data):
    if 'samples' in data:
        data_queue.put(('ppg', data['samples']))

def process_heart_rate(hr):
    data_queue.put(('hr', hr))

def process_imu(data):
    if 'accel' in data:
        data_queue.put(('accel', data['accel']))

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

def update_all():
    """Single fast update function for all data"""
    global current_hr
    
    # Process all available data quickly
    processed = 0
    while processed < 100:  # Process up to 100 items per update
        try:
            data_type, data = data_queue.get_nowait()
            
            if data_type == 'eeg':
                # Add EEG samples directly
                for channel, samples in data.items():
                    if channel in eeg_buffers:
                        # Add all samples for real-time display
                        if isinstance(samples, list):
                            eeg_buffers[channel].extend(samples)
                        else:
                            eeg_buffers[channel].append(samples)
            
            elif data_type == 'ppg':
                # Add PPG samples
                if isinstance(data, list):
                    ppg_buffer.extend(data)
                else:
                    ppg_buffer.append(data)
            
            elif data_type == 'hr':
                # Update heart rate
                current_hr = data
                heart_rates.append(data)
            
            elif data_type == 'accel':
                # Add IMU data
                if len(data) >= 3:
                    imu_data['accel_x'].append(data[0])
                    imu_data['accel_y'].append(data[1])
                    imu_data['accel_z'].append(data[2])
            
            processed += 1
        except queue.Empty:
            break
    
    # Update all plots at once
    
    # EEG plots - show raw data for real-time
    for i, (channel, buffer) in enumerate(eeg_buffers.items()):
        if len(buffer) > 0:
            # Just display last N points for performance
            data = list(buffer)
            if len(data) > 256:
                data = data[-256:]  # Show last second
            eeg_curves[i].setData(data)
    
    # PPG plot - show waveform
    if len(ppg_buffer) > 0:
        ppg_data = list(ppg_buffer)
        ppg_curve.setData(ppg_data)
    
    # Heart rate - update instantly
    if current_hr > 0:
        # Update big display
        hr_text.setText(f"{current_hr:.0f}")
        
        # Color based on zones
        if current_hr < 60:
            color = '#00BCD4'
        elif current_hr < 100:
            color = '#4CAF50'
        elif current_hr < 120:
            color = '#FFC107'
        else:
            color = '#F44336'
        hr_text.setColor(color)
        
        # Update history
        if len(heart_rates) > 0:
            hr_curve.setData(list(heart_rates))
    
    # IMU plots
    if len(imu_data['accel_x']) > 0:
        imu_curves[0].setData(list(imu_data['accel_x']))
    if len(imu_data['accel_y']) > 0:
        imu_curves[1].setData(list(imu_data['accel_y']))
    if len(imu_data['accel_z']) > 0:
        imu_curves[2].setData(list(imu_data['accel_z']))

def main():
    """Main function"""
    global eeg_curves, ppg_curve, hr_curve, hr_text, imu_curves
    
    print("Real-time Muse Visualization (Unified Fast Updates)")
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
    
    # Configure for performance with some quality
    pg.setConfigOptions(antialias=False)  # No antialiasing for speed
    
    # Create window
    win = pg.GraphicsLayoutWidget(show=True, title="Real-time Muse - All Fast Updates")
    win.resize(1400, 900)
    win.setWindowTitle(f'Muse Real-time @ {UPDATE_HZ} Hz')
    
    # === EEG Section (Left) ===
    win.addLabel("EEG Channels (Real-time)", row=0, col=0, colspan=2)
    eeg_curves = []
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFA726', '#AB47BC', '#66BB6A']
    
    for i, (channel, color) in enumerate(zip(eeg_buffers.keys(), colors)):
        row = (i // 2) + 1
        col = i % 2
        p = win.addPlot(title=channel, row=row, col=col)
        p.setYRange(-500, 500)
        p.showGrid(y=True, alpha=0.2)
        p.hideAxis('bottom')
        p.setDownsampling(mode='peak')  # Auto downsample for display
        p.setClipToView(True)
        curve = p.plot(pen=pg.mkPen(color=color, width=1))  # Thin for speed
        eeg_curves.append(curve)
    
    # === Heart Rate Section (Right Top) ===
    win.addLabel("Heart Rate (Real-time)", row=0, col=2, colspan=2)
    
    # Big HR display
    hr_widget = win.addViewBox(row=1, col=2, colspan=2, rowspan=2)
    hr_text = pg.TextItem(text="--", anchor=(0.5, 0.5))
    hr_text.setFont(QtGui.QFont('Arial', 72, QtGui.QFont.Bold))
    hr_widget.addItem(hr_text)
    hr_text.setPos(0.5, 0.5)
    
    # BPM label
    bpm_label = win.addLabel("BPM", row=1, col=4)
    
    # HR history plot
    hr_plot = win.addPlot(title="Heart Rate Trend", row=3, col=2, colspan=2)
    hr_plot.setLabel('left', 'BPM')
    hr_plot.setYRange(40, 140)
    hr_plot.showGrid(y=True, alpha=0.3)
    hr_curve = hr_plot.plot(pen=pg.mkPen(color='#E91E63', width=2))
    
    # === PPG Section (Right Middle) ===
    ppg_plot = win.addPlot(title="PPG Pulse Wave (Real-time)", row=4, col=2, colspan=2)
    ppg_plot.setLabel('left', 'PPG')
    ppg_plot.showGrid(y=True, alpha=0.3)
    ppg_plot.setDownsampling(mode='peak')
    ppg_curve = ppg_plot.plot(pen=pg.mkPen(color='#FF5252', width=1))
    
    # === IMU Section (Bottom) ===
    win.addLabel("Motion Sensor (Real-time)", row=5, col=0, colspan=4)
    imu_plot = win.addPlot(title="Accelerometer XYZ", row=6, col=0, colspan=4)
    imu_plot.setLabel('left', 'Acceleration (g)')
    imu_plot.setYRange(-2, 2)
    imu_plot.showGrid(y=True, alpha=0.3)
    imu_plot.addLegend()
    imu_plot.setDownsampling(mode='peak')
    
    imu_curves = []
    imu_colors = ['#FF5252', '#69F0AE', '#448AFF']
    for color, axis in zip(imu_colors, ['X', 'Y', 'Z']):
        curve = imu_plot.plot(pen=pg.mkPen(color=color, width=1), name=axis)
        imu_curves.append(curve)
    
    # Single fast timer for everything
    timer = QtCore.QTimer()
    timer.timeout.connect(update_all)
    timer.start(1000 // UPDATE_HZ)  # Fast updates!
    
    # Start streaming
    print(f"\nStarting stream...")
    stream_thread = threading.Thread(
        target=lambda: asyncio.run(stream_data(device.address, 300)),
        daemon=True
    )
    stream_thread.start()
    
    print(f"Visualization running at {UPDATE_HZ} Hz")
    print("All data updates in real-time!")
    print("Close window to stop.\n")
    
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