"""
Example 15: LSL-Style Band Power Visualization
Shows frequency band powers instead of raw waveforms

Shows:
- All 7 EEG channels with band power bars
- Stable, non-jumpy visualization
- Real-time frequency analysis
- Color-coded frequency bands
"""

import sys
import time
import asyncio
import threading
from collections import deque
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

# Add parent directory to path
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Fix Windows Qt/Bleak conflict
try:
    from bleak.backends.winrt.util import allow_sta
    allow_sta()
except ImportError:
    pass

from muse_stream_client import MuseStreamClient
from muse_discovery import find_muse_devices

# --- Configuration ---
UPDATE_INTERVAL_MS = 100  # How often to update the plot (milliseconds)
SAMPLING_RATE = 256  # Muse S EEG sampling rate
BUFFER_SIZE = 512  # Samples for FFT (2 seconds)
SMOOTHING = 0.85  # Smoothing factor for stable display

# --- Main Application Class ---
class RealTimePlot(pg.GraphicsLayoutWidget):
    """
    Real-time band power visualization using amused library.
    Displays frequency content of all 7 EEG channels.
    """
    
    def __init__(self):
        super().__init__()
        self.channel_count = 7  # Display all 7 EEG channels
        self.sampling_rate = SAMPLING_RATE
        self.device_address = None
        self.stream_thread = None
        
        # Data buffers for all 7 channels
        self.channel_names = ['TP9', 'AF7', 'AF8', 'TP10', 'FPz', 'AUX_R', 'AUX_L']
        self.databuffers = {
            channel: deque(maxlen=BUFFER_SIZE)
            for channel in self.channel_names
        }
        
        # Frequency bands
        self.bands = ['Delta (0.5-4Hz)', 'Theta (4-8Hz)', 'Alpha (8-12Hz)', 
                     'Beta (12-30Hz)', 'Gamma (30-50Hz)']
        self.band_ranges = [(0.5, 4), (4, 8), (8, 12), (12, 30), (30, 50)]
        self.band_colors = ['#9C27B0', '#3F51B5', '#4CAF50', '#FF9800', '#F44336']
        
        # Band power storage (smoothed)
        self.band_powers = {
            ch: {band: 0.0 for band in self.bands}
            for ch in self.channel_names
        }
        
        # Thread-safe queue for data
        import queue
        self.data_queue = queue.Queue()
        
        self._init_ui()
        self._find_device()
    
    def _init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle('Band Power Visualization - All 7 Channels')
        self.resize(1400, 900)
        self.setBackground('#1e1e1e')
        
        # Title
        title = self.addLabel('', row=0, col=0, colspan=4)
        title.setText('<h2 style="color: #4ECDC4;">EEG Band Powers</h2>')
        
        # Create bar graphs for each channel
        self.bar_plots = {}
        self.bar_items = {}
        
        for idx, channel in enumerate(self.channel_names):
            row = (idx // 4) + 1
            col = idx % 4
            
            # Create plot
            plot = self.addPlot(row=row, col=col)
            plot.setTitle(channel)
            plot.setLabel('left', 'Power (%)')
            plot.setYRange(0, 50)
            plot.showGrid(y=True, alpha=0.3)
            
            # Create bars for each band
            bars = []
            for i, (band, color) in enumerate(zip(self.bands, self.band_colors)):
                bar = pg.BarGraphItem(
                    x=[i], height=[0], width=0.8,
                    brush=color
                )
                plot.addItem(bar)
                bars.append(bar)
            
            # Set x-axis labels
            axis = plot.getAxis('bottom')
            axis.setTicks([[(i, b.split()[0]) for i, b in enumerate(self.bands)]])
            
            self.bar_plots[channel] = plot
            self.bar_items[channel] = bars
        
        # Status label
        self.status_label = self.addLabel('Searching for Muse device...', row=3, col=0, colspan=4)
    
    def _find_device(self):
        """Find and connect to Muse device."""
        def find_async():
            print("Looking for Muse device...")
            try:
                devices = asyncio.run(find_muse_devices(timeout=5.0))
                if devices:
                    self.device_address = devices[0].address
                    self.device_name = devices[0].name
                    print(f"Found device: {devices[0].name}")
                    # Queue status update for main thread
                    self.data_queue.put(('status', f"Connected to {devices[0].name}", None))
                    self._start_streaming()
                else:
                    print("No Muse device found!")
                    self.data_queue.put(('status', "No device found - please connect Muse", None))
            except Exception as e:
                print(f"Error finding device: {e}")
                self.data_queue.put(('status', f"Error: {e}", None))
        
        # Run device discovery in thread
        threading.Thread(target=find_async, daemon=True).start()
    
    def _start_streaming(self):
        """Start streaming from Muse device."""
        if not self.device_address:
            return
        
        async def stream_data():
            """Async streaming function."""
            client = MuseStreamClient(
                save_raw=False,
                decode_realtime=True,
                verbose=False
            )
            
            # Register EEG callback
            def process_eeg(data):
                if 'channels' in data:
                    self.data_queue.put(('eeg', data['channels']))
            
            client.on_eeg(process_eeg)
            
            # Connect and stream
            print(f"Starting stream from {self.device_address}...")
            success = await client.connect_and_stream(
                self.device_address,
                duration_seconds=0,  # Continuous streaming
                preset='p1035'  # Full sensor mode
            )
            
            if not success:
                print("Streaming failed!")
                self.data_queue.put(('status', "Streaming failed", None))
        
        # Start streaming in background thread
        self.stream_thread = threading.Thread(
            target=lambda: asyncio.run(stream_data()),
            daemon=True
        )
        self.stream_thread.start()
    
    def start_updates(self):
        """Start the timer to update plots."""
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(UPDATE_INTERVAL_MS)
    
    def update_plot(self):
        """Update the plot with new data from the queue."""
        # Process all available data
        samples_processed = 0
        max_samples = 50  # Process at most 50 samples per update
        
        while samples_processed < max_samples:
            try:
                data_type, data = self.data_queue.get_nowait()
                
                if data_type == 'status':
                    # Update status label from main thread
                    self.status_label.setText(data)
                    
                elif data_type == 'eeg':
                    channels = data
                    # Add samples to buffers
                    for channel_name in self.channel_names:
                        if channel_name in channels:
                            samples = channels[channel_name]
                            if isinstance(samples, list):
                                self.databuffers[channel_name].extend(samples)
                
                samples_processed += 1
                
            except:
                break  # No more data in queue
        
        # Calculate and display band powers
        for channel_name in self.channel_names:
            if len(self.databuffers[channel_name]) >= BUFFER_SIZE:
                # Get data and remove DC
                data = np.array(list(self.databuffers[channel_name])[-BUFFER_SIZE:])
                data = data - np.mean(data)
                
                # Apply window
                window = np.hanning(len(data))
                data = data * window
                
                # FFT
                fft = np.fft.rfft(data)
                freqs = np.fft.rfftfreq(len(data), 1/SAMPLING_RATE)
                power = np.abs(fft) ** 2
                
                # Calculate power in each band
                total_power = 0
                band_powers = []
                
                for low, high in self.band_ranges:
                    mask = (freqs >= low) & (freqs < high)
                    band_power = np.sum(power[mask])
                    band_powers.append(band_power)
                    total_power += band_power
                
                # Normalize and smooth
                if total_power > 0:
                    for i, (band, bp) in enumerate(zip(self.bands, band_powers)):
                        normalized = (bp / total_power) * 100
                        # Apply smoothing
                        old_val = self.band_powers[channel_name][band]
                        new_val = SMOOTHING * old_val + (1 - SMOOTHING) * normalized
                        self.band_powers[channel_name][band] = new_val
                        
                        # Update bar height
                        self.bar_items[channel_name][i].setOpts(height=[new_val])
    
    def closeEvent(self, event):
        """Clean up when window is closed."""
        if hasattr(self, 'timer'):
            self.timer.stop()
        event.accept()


# --- Main Execution ---
if __name__ == '__main__':
    # Create Qt Application
    app = QtWidgets.QApplication(sys.argv)
    
    # Create and show plot window
    main_window = RealTimePlot()
    main_window.show()
    
    # Start real-time updates
    main_window.start_updates()
    
    # Execute application
    sys.exit(app.exec_())