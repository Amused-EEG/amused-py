"""
Example 8: Ultra-Fast Visualization
Optimized for minimal lag with large data streams

Key optimizations:
- Fixed-size numpy arrays instead of growing buffers
- Minimal data copying
- Batch updates
- No unnecessary conversions
- Simplified rendering
"""

import asyncio
import sys
import os
import threading
import numpy as np
from datetime import datetime

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
    from pyqtgraph.Qt import QtCore, QtWidgets
except ImportError:
    print("PyQtGraph not installed! Install with: pip install pyqtgraph PyQt5")
    sys.exit(1)

from muse_stream_client import MuseStreamClient
from muse_discovery import find_muse_devices

# Performance settings
DISPLAY_SECONDS = 2  # Show last 2 seconds of data
EEG_HZ = 256
PPG_HZ = 64
UPDATE_HZ = 10  # Update display at 10 Hz for smooth but efficient rendering

# Pre-allocate fixed-size arrays for zero-copy performance
EEG_BUFFER_SIZE = DISPLAY_SECONDS * EEG_HZ
PPG_BUFFER_SIZE = DISPLAY_SECONDS * PPG_HZ

# Ring buffers using numpy arrays
class RingBuffer:
    """Fast ring buffer using numpy arrays"""
    def __init__(self, size):
        self.data = np.zeros(size)
        self.size = size
        self.ptr = 0
        self.filled = False
    
    def add(self, values):
        """Add values to ring buffer"""
        n = len(values)
        if n >= self.size:
            # If more values than buffer size, just take the last ones
            self.data[:] = values[-self.size:]
            self.ptr = 0
            self.filled = True
        else:
            # Add to buffer
            if self.ptr + n <= self.size:
                self.data[self.ptr:self.ptr + n] = values
            else:
                # Wrap around
                first_part = self.size - self.ptr
                self.data[self.ptr:] = values[:first_part]
                self.data[:n - first_part] = values[first_part:]
            
            self.ptr = (self.ptr + n) % self.size
            if self.ptr == 0:
                self.filled = True
    
    def get_display_data(self):
        """Get data in display order"""
        if self.filled:
            # Return data starting from ptr (oldest) to ptr-1 (newest)
            return np.roll(self.data, -self.ptr)
        else:
            # Return only filled portion
            return self.data[:self.ptr]

# Global buffers
eeg_buffers = {ch: RingBuffer(EEG_BUFFER_SIZE) for ch in 
              ['TP9', 'AF7', 'AF8', 'TP10', 'FPz', 'AUX_R', 'AUX_L']}
ppg_buffer = RingBuffer(PPG_BUFFER_SIZE)
heart_rate = 0.0

# Thread-safe data exchange
import queue
data_queue = queue.Queue()

# Data callbacks
def process_eeg(data):
    """Queue EEG data"""
    if 'channels' in data:
        data_queue.put(('eeg', data['channels']))

def process_ppg(data):
    """Queue PPG data"""
    if 'samples' in data:
        data_queue.put(('ppg', data['samples']))

def process_heart_rate(hr):
    """Update heart rate"""
    global heart_rate
    heart_rate = hr

async def stream_data(device_address: str, duration: int):
    """Stream data from Muse device"""
    client = MuseStreamClient(
        save_raw=False,
        decode_realtime=True,
        verbose=False  # Less verbose for performance
    )
    
    client.on_eeg(process_eeg)
    client.on_ppg(process_ppg)
    client.on_heart_rate(process_heart_rate)
    
    print(f"Connecting to {device_address}...")
    success = await client.connect_and_stream(
        device_address,
        duration_seconds=duration,
        preset='p1035'
    )
    
    if success:
        print("Stream complete")
    else:
        print("Stream failed")

def setup_plot(win, title, row, col, y_range=None, color='w'):
    """Create a plot with optimized settings"""
    p = win.addPlot(title=title, row=row, col=col)
    p.showGrid(x=False, y=True, alpha=0.2)  # Minimal grid
    p.setDownsampling(mode='peak')  # Automatic downsampling
    p.setClipToView(True)  # Don't render outside view
    
    if y_range:
        p.setYRange(*y_range)
        p.enableAutoRange(axis='y', enable=False)  # Disable auto-range for performance
    
    curve = p.plot(pen=pg.mkPen(color=color, width=1))  # Thin lines render faster
    return p, curve

def update_plots():
    """Fast plot update"""
    # Process all queued data
    processed = 0
    while processed < 50:  # Limit processing per update
        try:
            data_type, data = data_queue.get_nowait()
            
            if data_type == 'eeg':
                for channel, samples in data.items():
                    if channel in eeg_buffers:
                        # Convert to numpy array if needed
                        if not isinstance(samples, np.ndarray):
                            samples = np.array(samples, dtype=np.float32)
                        eeg_buffers[channel].add(samples)
            
            elif data_type == 'ppg':
                if isinstance(data, list) and len(data) > 0:
                    # Just take first value or mean
                    value = np.mean(data) if len(data) > 1 else data[0]
                    ppg_buffer.add(np.array([value]))
            
            processed += 1
        except queue.Empty:
            break
    
    # Update plots with current buffer data
    for i, (channel, buffer) in enumerate(eeg_buffers.items()):
        data = buffer.get_display_data()
        if len(data) > 0:
            # Downsample for display if needed
            if len(data) > 512:
                data = data[::len(data)//512]
            eeg_curves[i].setData(data)
    
    # Update PPG
    ppg_data = ppg_buffer.get_display_data()
    if len(ppg_data) > 0:
        ppg_curve.setData(ppg_data)
    
    # Update heart rate text
    if heart_rate > 0:
        hr_label.setText(f"Heart Rate: {heart_rate:.0f} BPM")

def main():
    """Main function"""
    global eeg_curves, ppg_curve, hr_label
    
    print("Fast Muse S Visualization")
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
    
    # Configure for performance
    pg.setConfigOptions(antialias=False)  # Disable antialiasing for speed
    pg.setConfigOptions(useWeave=True)  # Use weave for faster computation
    
    # Create window
    win = pg.GraphicsLayoutWidget(show=True, title="Fast Muse Visualization")
    win.resize(1000, 700)
    
    # Create plots with minimal features for speed
    eeg_curves = []
    colors = ['r', 'g', 'b', 'c', 'm', 'y', 'w']
    
    # Add title
    win.addLabel("EEG Channels (2s window)", row=0, col=0, colspan=2)
    
    # Create compact EEG layout
    for i, (channel, color) in enumerate(zip(eeg_buffers.keys(), colors)):
        row = (i % 4) + 1
        col = i // 4
        _, curve = setup_plot(win, channel, row, col, y_range=(-500, 500), color=color)
        eeg_curves.append(curve)
    
    # PPG plot
    win.addLabel("PPG & Heart Rate", row=5, col=0, colspan=2)
    _, ppg_curve = setup_plot(win, "PPG", row=6, col=0, colspan=2, color='r')
    
    # Heart rate label
    hr_label = win.addLabel("Heart Rate: -- BPM", row=7, col=0, colspan=2)
    hr_label.setText("Heart Rate: -- BPM")
    
    # Create fast update timer
    timer = QtCore.QTimer()
    timer.timeout.connect(update_plots)
    timer.start(1000 // UPDATE_HZ)  # Update at specified Hz
    
    # Start streaming in background
    print(f"\nStarting stream...")
    stream_thread = threading.Thread(
        target=lambda: asyncio.run(stream_data(device.address, 300)),
        daemon=True
    )
    stream_thread.start()
    
    print("Close window to stop\n")
    
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