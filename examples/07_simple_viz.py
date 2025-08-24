"""
Example 7: Simple Inline Visualization
Shows how to create your own real-time visualization without complex classes

This example demonstrates:
- Direct PyQtGraph usage for real-time plots
- Efficient data buffering with deque
- Downsampling for performance
- All visualization code in one place for clarity
"""

import asyncio
import sys
import os
import threading
import queue
from collections import deque
import numpy as np
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Fix Windows Qt/Bleak conflict
try:
    from bleak.backends.winrt.util import allow_sta
    allow_sta()
except ImportError:
    pass

# Import PyQtGraph for visualization
try:
    import pyqtgraph as pg
    from pyqtgraph.Qt import QtCore, QtWidgets, QtGui
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    print("PyQtGraph not installed! Install with: pip install pyqtgraph PyQt5")
    sys.exit(1)

from muse_stream_client import MuseStreamClient
from muse_discovery import find_muse_devices

# Global data queues for thread-safe communication
data_queue = queue.Queue()

# Data buffers - using deque for efficient circular buffer
MAX_DISPLAY_POINTS = 256  # Show only last 256 points for performance
eeg_buffers = {
    'TP9': deque(maxlen=MAX_DISPLAY_POINTS),
    'AF7': deque(maxlen=MAX_DISPLAY_POINTS),
    'AF8': deque(maxlen=MAX_DISPLAY_POINTS),
    'TP10': deque(maxlen=MAX_DISPLAY_POINTS),
    'FPz': deque(maxlen=MAX_DISPLAY_POINTS),
    'AUX_R': deque(maxlen=MAX_DISPLAY_POINTS),
    'AUX_L': deque(maxlen=MAX_DISPLAY_POINTS)
}
ppg_buffer = deque(maxlen=MAX_DISPLAY_POINTS)
heart_rates = deque(maxlen=60)  # Last 60 heart rate values

# Callback functions for data processing
def process_eeg(data):
    """Process EEG data - add to queue for GUI thread"""
    if 'channels' in data:
        data_queue.put(('eeg', data['channels']))

def process_ppg(data):
    """Process PPG data"""
    if 'samples' in data and isinstance(data['samples'], list):
        data_queue.put(('ppg', data['samples']))

def process_heart_rate(hr):
    """Process heart rate"""
    data_queue.put(('heart_rate', hr))

def process_imu(data):
    """Process IMU data"""
    # For simplicity, we'll skip IMU in this example
    pass

async def stream_worker(device_address: str, duration: int):
    """Async worker for BLE streaming"""
    client = MuseStreamClient(
        save_raw=False,
        decode_realtime=True,
        verbose=True
    )
    
    # Register callbacks
    client.on_eeg(process_eeg)
    client.on_ppg(process_ppg)
    client.on_heart_rate(process_heart_rate)
    client.on_imu(process_imu)
    
    # Connect and stream
    print(f"Connecting to {device_address}...")
    success = await client.connect_and_stream(
        device_address,
        duration_seconds=duration,
        preset='p1035'  # Sleep mode with all sensors
    )
    
    if success:
        print("Streaming complete!")
    else:
        print("Streaming failed")

def update_plots():
    """Update all plots - called by Qt timer"""
    # Process up to 10 items from queue
    for _ in range(10):
        try:
            data_type, data = data_queue.get_nowait()
            
            if data_type == 'eeg':
                # Add EEG samples to buffers
                for channel, samples in data.items():
                    if channel in eeg_buffers:
                        # Add samples but downsample if too many
                        if len(samples) > 10:
                            # Take every Nth sample to avoid overwhelming
                            samples = samples[::len(samples)//10]
                        eeg_buffers[channel].extend(samples[:5])  # Max 5 samples per update
            
            elif data_type == 'ppg':
                # Add PPG samples
                if len(data) > 0:
                    ppg_buffer.append(np.mean(data))  # Just take mean for simplicity
            
            elif data_type == 'heart_rate':
                heart_rates.append(data)
                
        except queue.Empty:
            break
    
    # Update EEG plots
    for i, (channel, buffer) in enumerate(eeg_buffers.items()):
        if len(buffer) > 0:
            # Simple moving average for smoothing
            data = np.array(buffer)
            if len(data) > 5:
                kernel = np.ones(5) / 5
                data = np.convolve(data, kernel, mode='valid')
            
            x = np.arange(len(data))
            eeg_curves[i].setData(x, data)
    
    # Update PPG plot
    if len(ppg_buffer) > 0:
        x = np.arange(len(ppg_buffer))
        ppg_curve.setData(x, np.array(ppg_buffer))
    
    # Update heart rate
    if len(heart_rates) > 0:
        x = np.arange(len(heart_rates))
        hr_curve.setData(x, np.array(heart_rates))
        # Update text
        hr_text.setText(f"HR: {heart_rates[-1]:.0f} BPM")

def main():
    """Main function"""
    global eeg_curves, ppg_curve, hr_curve, hr_text
    
    print("Simple Muse S Visualization")
    print("=" * 60)
    
    # Step 1: Find device
    print("\nSearching for Muse devices...")
    devices = asyncio.run(find_muse_devices(timeout=5.0))
    
    if not devices:
        print("No Muse devices found!")
        return
    
    device = devices[0]
    print(f"Found: {device.name} ({device.address})")
    
    # Step 2: Create PyQtGraph window
    print("\nCreating visualization window...")
    
    # Create Qt application
    app = QtWidgets.QApplication([])
    
    # Create main window
    win = pg.GraphicsLayoutWidget(show=True, title="Muse S Simple Visualization")
    win.resize(1200, 800)
    
    # Enable antialiasing
    pg.setConfigOptions(antialias=True)
    
    # Create EEG plots (simplified layout)
    print("Setting up EEG plots...")
    eeg_curves = []
    channel_names = list(eeg_buffers.keys())
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFA726', '#AB47BC', '#66BB6A']
    
    for i, (channel, color) in enumerate(zip(channel_names, colors)):
        # Create plot
        if i < 4:
            p = win.addPlot(title=f"EEG {channel}", row=i, col=0)
        else:
            p = win.addPlot(title=f"EEG {channel}", row=i-4, col=1)
        
        p.setLabel('left', 'μV')
        p.setYRange(-500, 500)
        p.showGrid(x=True, y=True, alpha=0.3)
        
        # Add curve
        curve = p.plot(pen=pg.mkPen(color=color, width=2))
        eeg_curves.append(curve)
    
    # Create PPG plot
    print("Setting up PPG/Heart Rate plots...")
    ppg_plot = win.addPlot(title="PPG Signal", row=0, col=2)
    ppg_plot.setLabel('left', 'PPG')
    ppg_plot.showGrid(x=True, y=True, alpha=0.3)
    ppg_curve = ppg_plot.plot(pen=pg.mkPen(color='#FF5252', width=2))
    
    # Create heart rate plot
    hr_plot = win.addPlot(title="Heart Rate", row=1, col=2)
    hr_plot.setLabel('left', 'BPM')
    hr_plot.setYRange(40, 120)
    hr_plot.showGrid(x=True, y=True, alpha=0.3)
    hr_curve = hr_plot.plot(pen=pg.mkPen(color='#E91E63', width=3))
    
    # Add heart rate text
    hr_text = pg.TextItem(text="HR: -- BPM", anchor=(0, 0), color='w')
    hr_text.setFont(QtGui.QFont('Arial', 14, QtGui.QFont.Bold))
    hr_plot.addItem(hr_text)
    
    # Step 3: Setup update timer
    timer = QtCore.QTimer()
    timer.timeout.connect(update_plots)
    timer.start(50)  # 20 Hz update rate
    
    # Step 4: Start streaming in background thread
    print("\nStarting data stream...")
    duration = 300  # 5 minutes
    
    stream_thread = threading.Thread(
        target=lambda: asyncio.run(stream_worker(device.address, duration)),
        daemon=True
    )
    stream_thread.start()
    
    print("Visualization running. Close window to stop.\n")
    
    # Run Qt event loop
    app.exec_()
    
    print("\nVisualization closed")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nStopped by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()