"""
Muse Device Discovery for GUI Applications
Handles the Windows event loop conflicts when using with PyQt/PyQtGraph

This module provides GUI-safe device discovery that works with Qt applications.
"""

import asyncio
import threading
from typing import List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor
import queue
from bleak import BleakScanner

from muse_discovery import MuseDevice


def scan_in_thread(timeout: float = 5.0, callback: Optional[Callable] = None) -> List[MuseDevice]:
    """
    Scan for Muse devices in a separate thread (GUI-safe)
    
    This function runs the async scan in a new thread with its own event loop,
    avoiding conflicts with Qt's event loop.
    
    Args:
        timeout: Scan timeout in seconds
        callback: Optional callback with (devices) when complete
        
    Returns:
        List of discovered Muse devices
        
    Example:
        # In a PyQt application
        devices = scan_in_thread()
        
        # Or with a callback
        def on_devices_found(devices):
            print(f"Found {len(devices)} devices")
        scan_in_thread(callback=on_devices_found)
    """
    result_queue = queue.Queue()
    
    def scan_thread():
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Run the async scan
            devices = loop.run_until_complete(_async_scan(timeout))
            result_queue.put(devices)
            
            if callback:
                callback(devices)
        finally:
            loop.close()
    
    # Start scan in background thread
    thread = threading.Thread(target=scan_thread, daemon=True)
    thread.start()
    thread.join(timeout + 1)  # Wait for completion
    
    # Get results
    try:
        return result_queue.get_nowait()
    except queue.Empty:
        return []


async def _async_scan(timeout: float) -> List[MuseDevice]:
    """Internal async scan function"""
    print(f"Scanning for Muse devices ({timeout}s)...")
    
    devices = []
    try:
        discovered = await BleakScanner.discover(timeout=timeout)
        
        for device in discovered:
            if device.name and "Muse" in device.name:
                muse = MuseDevice(
                    name=device.name,
                    address=device.address,
                    rssi=getattr(device, 'rssi', -100)
                )
                devices.append(muse)
                print(f"  Found: {muse}")
    
    except Exception as e:
        print(f"Scan error: {e}")
    
    if not devices:
        print("No Muse devices found")
    
    return devices


class MuseDeviceScanner:
    """
    GUI-friendly Muse device scanner
    
    This class provides methods for integrating device discovery
    into GUI applications without blocking the UI.
    
    Example with PyQt:
        scanner = MuseDeviceScanner()
        
        # Connect to a button
        scan_button.clicked.connect(scanner.start_scan)
        
        # Connect to results
        scanner.on_devices_found = self.update_device_list
    """
    
    def __init__(self):
        """Initialize scanner"""
        self.scanning = False
        self.devices = []
        self.on_devices_found = None
        self.on_scan_started = None
        self.on_scan_error = None
        self._scan_thread = None
    
    def start_scan(self, timeout: float = 5.0):
        """
        Start scanning for devices (non-blocking)
        
        Args:
            timeout: Scan timeout in seconds
        """
        if self.scanning:
            print("Already scanning...")
            return
        
        self.scanning = True
        self.devices = []
        
        if self.on_scan_started:
            self.on_scan_started()
        
        # Run scan in background
        self._scan_thread = threading.Thread(
            target=self._scan_worker,
            args=(timeout,),
            daemon=True
        )
        self._scan_thread.start()
    
    def _scan_worker(self, timeout: float):
        """Worker thread for scanning"""
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                devices = loop.run_until_complete(_async_scan(timeout))
                self.devices = devices
                
                if self.on_devices_found:
                    self.on_devices_found(devices)
            finally:
                loop.close()
                
        except Exception as e:
            print(f"Scan error: {e}")
            if self.on_scan_error:
                self.on_scan_error(str(e))
        finally:
            self.scanning = False
    
    def is_scanning(self) -> bool:
        """Check if currently scanning"""
        return self.scanning
    
    def get_devices(self) -> List[MuseDevice]:
        """Get last scan results"""
        return self.devices


# PyQt Integration Example
def create_qt_scanner_widget():
    """
    Example: Create a Qt widget for device scanning
    
    Returns a QWidget with scan functionality
    """
    try:
        from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QListWidget, QLabel
        from PyQt5.QtCore import QTimer, pyqtSignal, QObject
        
        class ScannerSignals(QObject):
            devices_found = pyqtSignal(list)
        
        class MuseScannerWidget(QWidget):
            def __init__(self):
                super().__init__()
                self.scanner = MuseDeviceScanner()
                self.signals = ScannerSignals()
                
                # Setup UI
                layout = QVBoxLayout()
                
                self.scan_button = QPushButton("Scan for Muse Devices")
                self.scan_button.clicked.connect(self.on_scan_clicked)
                
                self.status_label = QLabel("Ready to scan")
                
                self.device_list = QListWidget()
                
                layout.addWidget(self.scan_button)
                layout.addWidget(self.status_label)
                layout.addWidget(self.device_list)
                
                self.setLayout(layout)
                
                # Connect scanner callbacks
                self.scanner.on_scan_started = self.on_scan_started
                self.scanner.on_devices_found = self.on_devices_found
                self.scanner.on_scan_error = self.on_scan_error
            
            def on_scan_clicked(self):
                self.scanner.start_scan()
            
            def on_scan_started(self):
                self.scan_button.setEnabled(False)
                self.status_label.setText("Scanning...")
                self.device_list.clear()
            
            def on_devices_found(self, devices):
                self.scan_button.setEnabled(True)
                
                if devices:
                    self.status_label.setText(f"Found {len(devices)} device(s)")
                    for device in devices:
                        self.device_list.addItem(f"{device.name} ({device.address})")
                else:
                    self.status_label.setText("No devices found")
            
            def on_scan_error(self, error):
                self.scan_button.setEnabled(True)
                self.status_label.setText(f"Error: {error}")
            
            def get_selected_device(self) -> Optional[MuseDevice]:
                """Get currently selected device"""
                current = self.device_list.currentRow()
                if current >= 0 and current < len(self.scanner.devices):
                    return self.scanner.devices[current]
                return None
        
        return MuseScannerWidget
        
    except ImportError:
        print("PyQt5 not installed")
        return None


# Async wrapper for GUI applications
async def scan_async_safe(timeout: float = 5.0) -> List[MuseDevice]:
    """
    Async device scan that's safe to use with GUI event loops
    
    This creates a separate thread for the scan to avoid conflicts.
    
    Args:
        timeout: Scan timeout
        
    Returns:
        List of devices
        
    Example:
        # In an async GUI callback
        devices = await scan_async_safe()
    """
    loop = asyncio.get_event_loop()
    
    # Run in executor to avoid blocking
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = loop.run_in_executor(
            executor,
            scan_in_thread,
            timeout
        )
        return await future


# Demo
if __name__ == "__main__":
    import sys
    
    # Test thread-safe scanning
    print("Testing thread-safe scanning...")
    devices = scan_in_thread(timeout=5.0)
    
    if devices:
        print(f"\nFound {len(devices)} device(s):")
        for device in devices:
            print(f"  {device}")
    
    # Test Qt widget if available
    try:
        from PyQt5.QtWidgets import QApplication
        
        print("\nTesting Qt integration...")
        app = QApplication(sys.argv)
        
        WidgetClass = create_qt_scanner_widget()
        if WidgetClass:
            widget = WidgetClass()
            widget.setWindowTitle("Muse Device Scanner")
            widget.show()
            
            sys.exit(app.exec_())
    except ImportError:
        print("PyQt5 not available for GUI test")