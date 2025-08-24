"""
Example 6: Real-time Visualization with qasync
Proper integration of PyQtGraph, asyncio and Bleak using qasync

This properly handles the Windows event loop integration.
Install: pip install qasync
"""

import sys
import os
import asyncio
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Qt imports
from PyQt5 import QtWidgets
import pyqtgraph as pg

# Async Qt integration
try:
    import qasync
    QASYNC_AVAILABLE = True
except ImportError:
    print("qasync not installed. Install with: pip install qasync")
    QASYNC_AVAILABLE = False
    sys.exit(1)

# Muse imports
from bleak import BleakClient, BleakScanner
from muse_realtime_decoder import MuseRealtimeDecoder

# BLE UUIDs and commands
CONTROL_CHAR_UUID = "273e0001-4c4d-454d-96be-f03bac821358"
SENSOR_CHAR_UUID = "273e0013-4c4d-454d-96be-f03bac821358"

COMMANDS = {
    'v6': bytes.fromhex('0376360a'),
    's': bytes.fromhex('02730a'),
    'h': bytes.fromhex('02680a'),
    'p1034': bytes.fromhex('0670313033340a'),
    'dc001': bytes.fromhex('0664633030310a'),
    'L1': bytes.fromhex('034c310a'),
}


class MuseVisualizerWindow(pg.GraphicsLayoutWidget):
    """PyQtGraph window with Muse BLE integration"""
    
    def __init__(self, loop):
        """Initialize with event loop"""
        super().__init__(show=True, title="Muse S Real-time Monitor")
        self.loop = loop
        self.resize(1400, 900)
        self.setWindowTitle('Muse S Real-time Data')
        
        # BLE
        self.client = None
        self.decoder = MuseRealtimeDecoder()
        self.device_address = None
        self.packet_count = 0
        
        # Data buffers
        self.eeg_buffers = {
            'TP9': [],
            'AF7': [],
            'AF8': [],
            'TP10': []
        }
        self.max_points = 2560  # 10 seconds at 256 Hz
        
        # Setup plots
        self.setup_plots()
        
        # Setup update timer
        self.timer = pg.QtCore.QTimer()
        self.timer.timeout.connect(self.update_plots)
        self.timer.start(33)  # 30 Hz update
        
        # Start device discovery
        self.loop.create_task(self.find_and_connect())
    
    def setup_plots(self):
        """Setup plot layouts"""
        self.eeg_plots = {}
        self.eeg_curves = {}
        
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4']
        
        for i, (channel, color) in enumerate(zip(self.eeg_buffers.keys(), colors)):
            plot = self.addPlot(title=f"EEG {channel}", row=i, col=0, colspan=2)
            plot.setLabel('left', 'Amplitude', units='μV')
            plot.setLabel('bottom', 'Samples')
            plot.setYRange(-500, 500)
            plot.showGrid(x=True, y=True, alpha=0.3)
            
            curve = plot.plot(pen=pg.mkPen(color=color, width=2))
            self.eeg_plots[channel] = plot
            self.eeg_curves[channel] = curve
        
        # Status plot for text
        self.status_plot = self.addPlot(title="Status", row=4, col=0, colspan=2)
        self.status_plot.hideAxis('left')
        self.status_plot.hideAxis('bottom')
        self.status_text = pg.TextItem(text="Searching for device...", color='w')
        self.status_plot.addItem(self.status_text)
    
    def update_plots(self):
        """Update all plots"""
        for channel, data in self.eeg_buffers.items():
            if data:
                self.eeg_curves[channel].setData(data)
    
    def handle_notification(self, sender, data):
        """Handle BLE notification"""
        self.packet_count += 1
        
        # Decode packet
        decoded = self.decoder.decode(bytes(data), datetime.now())
        
        # Update EEG buffers
        if decoded.eeg:
            for channel, samples in decoded.eeg.items():
                if channel in self.eeg_buffers:
                    self.eeg_buffers[channel].extend(samples)
                    # Keep only last max_points
                    if len(self.eeg_buffers[channel]) > self.max_points:
                        self.eeg_buffers[channel] = self.eeg_buffers[channel][-self.max_points:]
            
            # Update status
            self.status_text.setText(f"Packets: {self.packet_count}")
    
    async def find_and_connect(self):
        """Find and connect to Muse device"""
        try:
            # Find device
            self.status_text.setText("Scanning for Muse devices...")
            devices = await BleakScanner.discover(timeout=5.0)
            
            muse_device = None
            for device in devices:
                if device.name and "Muse" in device.name:
                    muse_device = device
                    break
            
            if not muse_device:
                self.status_text.setText("No Muse device found")
                return
            
            self.device_address = muse_device.address
            self.status_text.setText(f"Found: {muse_device.name}")
            
            # Connect
            await self.connect_and_stream()
            
        except Exception as e:
            self.status_text.setText(f"Error: {e}")
    
    async def connect_and_stream(self):
        """Connect and start streaming"""
        try:
            # Create client with the loop
            self.client = BleakClient(self.device_address, loop=self.loop)
            
            self.status_text.setText(f"Connecting to {self.device_address}...")
            await self.client.connect()
            
            if not self.client.is_connected:
                self.status_text.setText("Failed to connect")
                return
            
            self.status_text.setText("Connected! Initializing...")
            
            # Initialize device
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['h'])
            await asyncio.sleep(0.5)
            
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['p1034'])
            await asyncio.sleep(0.5)
            
            # Start streaming (send twice)
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['dc001'])
            await asyncio.sleep(0.2)
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['dc001'])
            await asyncio.sleep(0.2)
            
            await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['L1'])
            
            # Start notifications
            await self.client.start_notify(SENSOR_CHAR_UUID, self.handle_notification)
            
            self.status_text.setText("Streaming...")
            
        except Exception as e:
            self.status_text.setText(f"Connection error: {e}")
    
    async def cleanup(self):
        """Clean up on close"""
        if self.client and self.client.is_connected:
            try:
                await self.client.stop_notify(SENSOR_CHAR_UUID)
                await self.client.write_gatt_char(CONTROL_CHAR_UUID, COMMANDS['h'])
                await self.client.disconnect()
            except:
                pass
    
    def closeEvent(self, event):
        """Handle window close"""
        # Schedule cleanup
        self.loop.create_task(self.cleanup())
        super().closeEvent(event)


async def main():
    """Main async function"""
    # Get the event loop
    loop = asyncio.get_event_loop()
    
    # Create and show window
    window = MuseVisualizerWindow(loop)
    
    # Keep running until window closes
    while window.isVisible():
        await asyncio.sleep(0.1)
    
    # Cleanup
    await window.cleanup()


if __name__ == "__main__":
    print("Muse S Visualization with qasync")
    print("=" * 60)
    
    # Create Qt application
    app = QtWidgets.QApplication(sys.argv)
    
    # Create async event loop
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    try:
        # Run main async function
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\nStopped by user")
    finally:
        loop.close()