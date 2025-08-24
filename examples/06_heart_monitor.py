"""
Example 14: Simple Heart Rate Monitor
Just displays heart rate - clean and simple

Shows:
- Current heart rate (big and clear)
- Heart rate trend
- Connection status
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

# Global state
current_hr = 0
hr_history = deque(maxlen=60)  # Last 60 heart rate values
ppg_buffer = deque(maxlen=320)  # For HR calculation if needed
connected = False

import queue
data_queue = queue.Queue()

def process_ppg(data):
    if 'samples' in data and data['samples']:
        samples = data['samples']
        if isinstance(samples, list) and len(samples) > 0:
            data_queue.put(('ppg', samples))

def process_heart_rate(hr):
    if hr and hr > 0:
        data_queue.put(('hr', hr))

async def stream_data(device_address: str):
    global connected
    
    client = MuseStreamClient(
        save_raw=False,
        decode_realtime=True,
        verbose=False
    )
    
    client.on_ppg(process_ppg)
    client.on_heart_rate(process_heart_rate)
    
    print(f"Connecting to Muse...")
    connected = await client.connect_and_stream(
        device_address,
        duration_seconds=300,  # 5 minutes
        preset='p1035'
    )
    
    if not connected:
        print("Connection failed")

def update_display():
    """Update the display"""
    global current_hr
    
    # Process queued data
    for _ in range(20):
        try:
            data_type, data = data_queue.get_nowait()
            
            if data_type == 'ppg':
                ppg_buffer.extend(data)
                # Keep buffer size manageable
                while len(ppg_buffer) > 320:
                    ppg_buffer.popleft()
            
            elif data_type == 'hr':
                current_hr = data
                hr_history.append(data)
                
        except queue.Empty:
            break
    
    # Update heart rate display
    if current_hr > 0:
        # Update main display
        hr_text.setText(f"{current_hr:.0f}")
        
        # Color based on HR zones
        if current_hr < 60:
            color = '#00BCD4'  # Cyan - Low
            zone = "REST"
        elif current_hr < 100:
            color = '#4CAF50'  # Green - Normal
            zone = "NORMAL"
        elif current_hr < 140:
            color = '#FFC107'  # Amber - Elevated
            zone = "ELEVATED"
        else:
            color = '#F44336'  # Red - High
            zone = "HIGH"
        
        hr_text.setColor(color)
        zone_text.setText(zone)
        zone_text.setColor(color)
        
        # Update graph
        if len(hr_history) > 1:
            x_data = np.arange(len(hr_history))
            y_data = np.array(hr_history)
            hr_curve.setData(x_data, y_data)
            
            # Update trend
            if len(hr_history) > 10:
                recent = np.mean(list(hr_history)[-5:])
                older = np.mean(list(hr_history)[-10:-5])
                
                if recent > older + 2:
                    trend_text.setText("↑")
                    trend_text.setColor('#FF5252')
                elif recent < older - 2:
                    trend_text.setText("↓")
                    trend_text.setColor('#4CAF50')
                else:
                    trend_text.setText("→")
                    trend_text.setColor('#FFC107')
    
    # Update status based on actual data reception
    if current_hr > 0:
        status_text.setText(f"Receiving data")
        status_text.setColor('#4CAF50')
    elif len(ppg_buffer) > 0:
        status_text.setText(f"Waiting for heart rate...")
        status_text.setColor('#FFC107')
    else:
        status_text.setText("Connecting...")
        status_text.setColor('#9E9E9E')

def main():
    global hr_text, zone_text, trend_text, hr_curve, status_text
    
    print("Heart Rate Monitor")
    print("=" * 60)
    
    # Find device
    print("Searching for Muse device...")
    devices = asyncio.run(find_muse_devices(timeout=3.0))
    if not devices:
        print("No device found!")
        return
    
    device = devices[0]
    print(f"Found: {device.name}\n")
    
    # Create app
    app = QtWidgets.QApplication([])
    
    # Window
    win = pg.GraphicsLayoutWidget(show=True, title="Muse Heart Rate")
    win.resize(800, 600)
    win.setBackground('#1e1e1e')  # Dark background
    
    # Title
    title = win.addLabel("♥ HEART RATE MONITOR ♥", row=0, col=0, colspan=3)
    title.setText("♥ HEART RATE MONITOR ♥", size='16pt', bold=True, color='#E91E63')
    
    # Main heart rate display
    hr_box = win.addViewBox(row=1, col=0, colspan=2, rowspan=2)
    hr_text = pg.TextItem(text="--", anchor=(0.5, 0.5))
    hr_text.setFont(QtGui.QFont('Arial', 96, QtGui.QFont.Bold))
    hr_text.setColor('#E91E63')
    hr_box.addItem(hr_text)
    hr_text.setPos(0.5, 0.5)
    
    # BPM label
    bpm_box = win.addViewBox(row=3, col=0, colspan=2)
    bpm_text = pg.TextItem(text="BPM", anchor=(0.5, 0))
    bpm_text.setFont(QtGui.QFont('Arial', 24))
    bpm_text.setColor('#9E9E9E')
    bpm_box.addItem(bpm_text)
    bpm_text.setPos(0.5, 0.8)
    
    # Zone indicator
    zone_box = win.addViewBox(row=1, col=2)
    zone_text = pg.TextItem(text="---", anchor=(0.5, 0.5))
    zone_text.setFont(QtGui.QFont('Arial', 18, QtGui.QFont.Bold))
    zone_box.addItem(zone_text)
    zone_text.setPos(0.5, 0.5)
    
    # Trend arrow
    trend_box = win.addViewBox(row=2, col=2)
    trend_text = pg.TextItem(text="→", anchor=(0.5, 0.5))
    trend_text.setFont(QtGui.QFont('Arial', 48))
    trend_text.setColor('#9E9E9E')
    trend_box.addItem(trend_text)
    trend_text.setPos(0.5, 0.5)
    
    # Heart rate graph
    hr_plot = win.addPlot(title="Heart Rate History", row=4, col=0, colspan=3)
    hr_plot.setLabel('left', 'BPM')
    hr_plot.setLabel('bottom', 'Time')
    hr_plot.setYRange(40, 160)
    hr_plot.showGrid(y=True, alpha=0.3)
    hr_curve = hr_plot.plot(pen=pg.mkPen(color='#E91E63', width=3))
    
    # Add zone lines
    hr_plot.addLine(y=60, pen=pg.mkPen('#00BCD4', width=1, style=QtCore.Qt.DashLine))
    hr_plot.addLine(y=100, pen=pg.mkPen('#FFC107', width=1, style=QtCore.Qt.DashLine))
    hr_plot.addLine(y=140, pen=pg.mkPen('#F44336', width=1, style=QtCore.Qt.DashLine))
    
    # Status bar
    status_box = win.addViewBox(row=5, col=0, colspan=3)
    status_text = pg.TextItem(text="Connecting...", anchor=(0.5, 0.5))
    status_text.setFont(QtGui.QFont('Arial', 12))
    status_box.addItem(status_text)
    status_text.setPos(0.5, 0.5)
    
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
    
    print("Monitoring heart rate...")
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