"""
Example 18: Simple Frequency Display
Just shows the dominant frequency for each channel - clean and stable

Shows:
- Current dominant frequency (Hz) for each channel
- Color-coded by brain wave type
- Large, easy-to-read numbers
- No jumpy graphs
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
UPDATE_RATE = 5  # Hz - how often to update display
SMOOTHING = 0.85  # Smoothing factor (0-1, higher = smoother)

class FrequencyDisplay(pg.GraphicsLayoutWidget):
    """
    Simple frequency display - just shows Hz values
    """
    
    def __init__(self):
        super().__init__()
        self.device_address = None
        self.timer_started = False
        
        # Channel configuration (main 4 channels)
        self.channels = {
            'TP9': {'row': 1, 'col': 0, 'label': 'Left Temporal'},
            'AF7': {'row': 1, 'col': 1, 'label': 'Left Frontal'},
            'AF8': {'row': 2, 'col': 0, 'label': 'Right Frontal'},
            'TP10': {'row': 2, 'col': 1, 'label': 'Right Temporal'}
        }
        
        # Data buffers
        self.sample_rate = 256
        self.buffer_size = 512  # 2 seconds
        self.eeg_buffers = {ch: deque(maxlen=self.buffer_size) for ch in self.channels}
        
        # Frequency tracking
        self.current_freq = {ch: 10.0 for ch in self.channels}
        self.smoothed_freq = {ch: 10.0 for ch in self.channels}
        
        # UI elements
        self.freq_displays = {}
        self.channel_labels = {}
        
        # Thread-safe queue
        import queue
        self.data_queue = queue.Queue()
        
        self._init_ui()
        self._find_and_connect()
        
        # Start a timer to check for timer start request
        self.check_timer = QtCore.QTimer()
        self.check_timer.timeout.connect(self._check_start_timer)
        self.check_timer.start(100)  # Check every 100ms
    
    def _init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle('Brain Wave Frequencies - Simple Display')
        self.resize(800, 600)
        self.setBackground('#1e1e1e')
        
        # Title
        title = self.addLabel('', row=0, col=0, colspan=2)
        title.setText('<h1 style="color: #4ECDC4;">Brain Frequencies (Hz)</h1>')
        
        # Create frequency displays for each channel
        for ch_name, ch_info in self.channels.items():
            # Channel name
            label_box = self.addViewBox(row=ch_info['row']*2-1, col=ch_info['col'])
            label = pg.TextItem(
                text=ch_info['label'],
                anchor=(0.5, 0.5),
                color='#9E9E9E'
            )
            label.setFont(QtGui.QFont('Arial', 14))
            label_box.addItem(label)
            label.setPos(0.5, 0.5)
            self.channel_labels[ch_name] = label
            
            # Frequency display
            freq_box = self.addViewBox(row=ch_info['row']*2, col=ch_info['col'])
            freq_text = pg.TextItem(
                text="--",
                anchor=(0.5, 0.5)
            )
            freq_text.setFont(QtGui.QFont('Arial', 48, QtGui.QFont.Bold))
            freq_box.addItem(freq_text)
            freq_text.setPos(0.5, 0.5)
            self.freq_displays[ch_name] = freq_text
        
        # Overall brain state
        self.state_box = self.addViewBox(row=5, col=0, colspan=2)
        self.state_text = pg.TextItem(
            text="Waiting for data...",
            anchor=(0.5, 0.5)
        )
        self.state_text.setFont(QtGui.QFont('Arial', 24, QtGui.QFont.Bold))
        self.state_box.addItem(self.state_text)
        self.state_text.setPos(0.5, 0.5)
        
        # Status
        self.status_label = self.addLabel('Searching for Muse device...', row=6, col=0, colspan=2)
    
    def get_frequency_color(self, freq):
        """Get color based on frequency band"""
        if freq < 4:
            return '#9C27B0'  # Delta - Purple
        elif freq < 8:
            return '#3F51B5'  # Theta - Blue
        elif freq < 12:
            return '#4CAF50'  # Alpha - Green
        elif freq < 30:
            return '#FF9800'  # Beta - Orange
        else:
            return '#F44336'  # Gamma - Red
    
    def get_frequency_state(self, freq):
        """Get state name based on frequency"""
        if freq < 4:
            return "Delta (Deep Sleep)"
        elif freq < 8:
            return "Theta (Meditation)"
        elif freq < 12:
            return "Alpha (Relaxed)"
        elif freq < 30:
            return "Beta (Focused)"
        else:
            return "Gamma (Active)"
    
    def _find_and_connect(self):
        """Find and connect to Muse device"""
        def connect_async():
            try:
                print("Searching for Muse device...")
                devices = asyncio.run(find_muse_devices(timeout=5.0))
                
                if devices:
                    self.device_address = devices[0].address
                    device_name = devices[0].name
                    print(f"Found: {device_name}")
                    
                    self.data_queue.put(('status', f'Connected to {device_name}'))
                    self._start_streaming()
                else:
                    print("No Muse device found")
                    self.data_queue.put(('status', 'No device found'))
                    
            except Exception as e:
                print(f"Connection error: {e}")
                self.data_queue.put(('status', f'Error: {e}'))
        
        threading.Thread(target=connect_async, daemon=True).start()
    
    def _start_streaming(self):
        """Start streaming from Muse device"""
        if not self.device_address:
            return
        
        async def stream_data():
            client = MuseStreamClient(
                save_raw=False,
                decode_realtime=True,
                verbose=False
            )
            
            def process_eeg(data):
                if 'channels' in data:
                    self.data_queue.put(('eeg', data['channels']))
            
            client.on_eeg(process_eeg)
            
            print(f"Starting stream...")
            success = await client.connect_and_stream(
                self.device_address,
                duration_seconds=0,
                preset='p1035'
            )
            
            if not success:
                self.data_queue.put(('status', 'Streaming failed'))
        
        threading.Thread(
            target=lambda: asyncio.run(stream_data()),
            daemon=True
        ).start()
        
        # Queue timer start for main thread
        self.data_queue.put(('start_timer', None))
    
    def _check_start_timer(self):
        """Check if we need to start the main update timer"""
        try:
            while True:
                data_type, _ = self.data_queue.get_nowait()
                if data_type == 'start_timer' and not self.timer_started:
                    self.timer_started = True
                    self.check_timer.stop()
                    # Start the real update timer
                    self.timer = QtCore.QTimer()
                    self.timer.timeout.connect(self.update_display)
                    self.timer.start(int(1000 / UPDATE_RATE))
                    break
        except:
            pass
    
    def calculate_dominant_frequency(self, channel):
        """Calculate dominant frequency for a channel"""
        if len(self.eeg_buffers[channel]) < self.buffer_size:
            return None
        
        # Get data and remove DC
        data = np.array(self.eeg_buffers[channel])
        data = data - np.mean(data)
        
        # Apply window
        window = np.hanning(len(data))
        data = data * window
        
        # FFT
        fft = np.fft.rfft(data)
        freqs = np.fft.rfftfreq(len(data), 1/self.sample_rate)
        power = np.abs(fft) ** 2
        
        # Find peak in physiological range (1-40 Hz)
        valid_mask = (freqs >= 1) & (freqs <= 40)
        if np.any(valid_mask):
            valid_power = power[valid_mask]
            valid_freqs = freqs[valid_mask]
            
            # Find peak
            peak_idx = np.argmax(valid_power)
            return valid_freqs[peak_idx]
        
        return None
    
    def update_display(self):
        """Update the display"""
        # Process queued data
        for _ in range(20):
            try:
                data_type, data = self.data_queue.get_nowait()
                
                if data_type == 'status':
                    self.status_label.setText(data)
                    
                elif data_type == 'eeg':
                    # Add samples to buffers
                    for ch_name in self.channels:
                        if ch_name in data:
                            samples = data[ch_name]
                            if isinstance(samples, list):
                                self.eeg_buffers[ch_name].extend(samples)
            except:
                break
        
        # Calculate and display frequencies
        avg_freq = 0
        count = 0
        
        for ch_name in self.channels:
            if len(self.eeg_buffers[ch_name]) >= self.buffer_size:
                freq = self.calculate_dominant_frequency(ch_name)
                
                if freq is not None:
                    # Apply smoothing
                    self.smoothed_freq[ch_name] = (
                        SMOOTHING * self.smoothed_freq[ch_name] +
                        (1 - SMOOTHING) * freq
                    )
                    
                    # Update display
                    display_freq = self.smoothed_freq[ch_name]
                    self.freq_displays[ch_name].setText(f"{display_freq:.1f}")
                    self.freq_displays[ch_name].setColor(self.get_frequency_color(display_freq))
                    
                    avg_freq += display_freq
                    count += 1
        
        # Update overall state
        if count > 0:
            overall_freq = avg_freq / count
            state = self.get_frequency_state(overall_freq)
            color = self.get_frequency_color(overall_freq)
            self.state_text.setText(state)
            self.state_text.setColor(color)
    
    def closeEvent(self, event):
        """Clean up when window is closed"""
        if hasattr(self, 'timer'):
            self.timer.stop()
        event.accept()


# --- Main Execution ---
if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    
    # Dark theme
    app.setStyle('Fusion')
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(30, 30, 30))
    palette.setColor(QtGui.QPalette.WindowText, QtCore.Qt.white)
    app.setPalette(palette)
    
    # Create and show
    main_window = FrequencyDisplay()
    main_window.show()
    
    sys.exit(app.exec_())