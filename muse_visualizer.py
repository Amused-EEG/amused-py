"""
Muse Real-time Visualizer
Interactive visualization for EEG, PPG, and IMU data streams

Supports multiple backends:
- PyQtGraph (fastest, best for real-time)
- Plotly/Dash (web-based, interactive)
- Matplotlib (simple, compatible)
"""

import numpy as np
import asyncio
from collections import deque
from datetime import datetime
from typing import Optional, Dict, List, Callable
import threading
import queue

# Try to import visualization backends
PYQTGRAPH_AVAILABLE = False
PLOTLY_AVAILABLE = False
MATPLOTLIB_AVAILABLE = False

try:
    import pyqtgraph as pg
    from pyqtgraph.Qt import QtCore, QtWidgets
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    pass

try:
    import plotly.graph_objs as go
    from plotly.subplots import make_subplots
    import dash
    from dash import dcc, html
    from dash.dependencies import Input, Output
    PLOTLY_AVAILABLE = True
except ImportError:
    pass

try:
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    pass


class DataBuffer:
    """Circular buffer for streaming data"""
    
    def __init__(self, maxlen: int = 1000, channels: int = 1):
        """
        Initialize data buffer
        
        Args:
            maxlen: Maximum number of samples to keep
            channels: Number of data channels
        """
        self.buffers = [deque(maxlen=maxlen) for _ in range(channels)]
        self.timestamps = deque(maxlen=maxlen)
        self.maxlen = maxlen
        self.channels = channels
    
    def add_samples(self, samples: List[float], timestamp: Optional[float] = None):
        """Add new samples to buffer"""
        if timestamp is None:
            timestamp = datetime.now().timestamp()
        
        self.timestamps.append(timestamp)
        
        if self.channels == 1:
            self.buffers[0].append(samples if isinstance(samples, (int, float)) else samples[0])
        else:
            for i, sample in enumerate(samples[:self.channels]):
                self.buffers[i].append(sample)
    
    def get_data(self) -> tuple:
        """Get current buffer data as numpy arrays"""
        times = np.array(self.timestamps) if self.timestamps else np.array([])
        data = [np.array(buf) if buf else np.array([]) for buf in self.buffers]
        return times, data


class PyQtGraphVisualizer:
    """High-performance real-time visualizer using PyQtGraph"""
    
    def __init__(self, window_size: int = 1000, update_rate: int = 30):
        """
        Initialize PyQtGraph visualizer
        
        Args:
            window_size: Number of samples to display
            update_rate: Display refresh rate in Hz
        """
        if not PYQTGRAPH_AVAILABLE:
            raise ImportError("PyQtGraph not installed. Install with: pip install pyqtgraph")
        
        self.window_size = window_size
        self.update_rate = update_rate
        
        # Data buffers
        self.eeg_buffer = DataBuffer(maxlen=window_size, channels=4)
        self.ppg_buffer = DataBuffer(maxlen=window_size, channels=3)
        self.imu_buffer = DataBuffer(maxlen=window_size, channels=6)
        self.heart_rate_buffer = DataBuffer(maxlen=60, channels=1)  # 60 seconds of HR
        
        # Setup GUI
        self.app = QtWidgets.QApplication([])
        self.win = pg.GraphicsLayoutWidget(show=True, title="Muse S Real-time Monitor")
        self.win.resize(1400, 900)
        self.win.setWindowTitle('Muse S Real-time Data Visualizer')
        
        # Enable antialiasing for smoother plots
        pg.setConfigOptions(antialias=True)
        
        self._setup_plots()
        self._setup_timer()
    
    def _setup_plots(self):
        """Setup plot layouts"""
        # EEG plots (4 channels)
        self.eeg_plots = []
        eeg_colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4']
        
        for i in range(4):
            if i == 0:
                p = self.win.addPlot(title=f"EEG Channel {i+1}", row=0, col=0, colspan=2)
            else:
                p = self.win.addPlot(title=f"EEG Channel {i+1}", row=i, col=0, colspan=2)
            
            p.setLabel('left', 'Amplitude', units='μV')
            p.setLabel('bottom', 'Time', units='s')
            p.setYRange(-500, 500)
            p.showGrid(x=True, y=True, alpha=0.3)
            
            curve = p.plot(pen=pg.mkPen(color=eeg_colors[i], width=2))
            self.eeg_plots.append(curve)
        
        # PPG/Heart Rate plot
        self.ppg_plot = self.win.addPlot(title="PPG & Heart Rate", row=0, col=2, rowspan=2)
        self.ppg_plot.setLabel('left', 'PPG', units='AU')
        self.ppg_plot.setLabel('bottom', 'Time', units='s')
        self.ppg_plot.showGrid(x=True, y=True, alpha=0.3)
        
        # Three PPG channels (IR, NIR, Red)
        self.ppg_curves = []
        ppg_colors = ['#FF0000', '#8B0000', '#FFA500']  # Red, Dark Red, Orange
        for i, color in enumerate(ppg_colors):
            curve = self.ppg_plot.plot(pen=pg.mkPen(color=color, width=2))
            self.ppg_curves.append(curve)
        
        # Heart rate trend plot
        self.hr_plot = self.win.addPlot(title="Heart Rate Trend", row=2, col=2)
        self.hr_plot.setLabel('left', 'BPM')
        self.hr_plot.setLabel('bottom', 'Time', units='s')
        self.hr_plot.setYRange(40, 120)
        self.hr_plot.showGrid(x=True, y=True, alpha=0.3)
        self.hr_curve = self.hr_plot.plot(
            pen=pg.mkPen(color='#FF1744', width=3),
            symbol='o',
            symbolSize=5,
            symbolBrush='#FF1744'
        )
        
        # IMU plots (Accelerometer and Gyroscope)
        self.accel_plot = self.win.addPlot(title="Accelerometer", row=3, col=2)
        self.accel_plot.setLabel('left', 'Acceleration', units='g')
        self.accel_plot.setLabel('bottom', 'Time', units='s')
        self.accel_plot.showGrid(x=True, y=True, alpha=0.3)
        self.accel_plot.addLegend()
        
        self.accel_curves = []
        accel_colors = ['#FF5252', '#69F0AE', '#448AFF']  # X, Y, Z
        for i, (color, axis) in enumerate(zip(accel_colors, ['X', 'Y', 'Z'])):
            curve = self.accel_plot.plot(
                pen=pg.mkPen(color=color, width=2),
                name=f'Accel {axis}'
            )
            self.accel_curves.append(curve)
        
        # Frequency spectrum plot
        self.spectrum_plot = self.win.addPlot(title="EEG Frequency Spectrum", row=4, col=0, colspan=3)
        self.spectrum_plot.setLabel('left', 'Power', units='μV²/Hz')
        self.spectrum_plot.setLabel('bottom', 'Frequency', units='Hz')
        self.spectrum_plot.setXRange(0, 60)
        self.spectrum_plot.showGrid(x=True, y=True, alpha=0.3)
        self.spectrum_curve = self.spectrum_plot.plot(
            pen=pg.mkPen(color='#FFC107', width=2),
            fillLevel=0,
            brush=(255, 193, 7, 50)
        )
        
        # Add frequency band indicators
        bands = [
            ('Delta', 0.5, 4, '#9C27B0'),
            ('Theta', 4, 8, '#3F51B5'),
            ('Alpha', 8, 12, '#4CAF50'),
            ('Beta', 12, 30, '#FF9800'),
            ('Gamma', 30, 60, '#F44336')
        ]
        
        for name, f_min, f_max, color in bands:
            region = pg.LinearRegionItem([f_min, f_max], brush=pg.mkBrush(color + '30'))
            region.setMovable(False)
            self.spectrum_plot.addItem(region)
    
    def _setup_timer(self):
        """Setup update timer"""
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._update_plots)
        self.timer.start(int(1000 / self.update_rate))  # Convert Hz to ms
    
    def _update_plots(self):
        """Update all plots with latest data"""
        # Update EEG plots
        times, eeg_data = self.eeg_buffer.get_data()
        if len(times) > 0:
            # Normalize time to start from 0
            times = times - times[0] if len(times) > 0 else times
            
            for i, curve in enumerate(self.eeg_plots):
                if i < len(eeg_data) and len(eeg_data[i]) > 0:
                    curve.setData(times, eeg_data[i])
            
            # Update spectrum if we have EEG data
            if len(eeg_data[0]) > 128:  # Need enough samples for FFT
                self._update_spectrum(eeg_data[0])
        
        # Update PPG plots
        times, ppg_data = self.ppg_buffer.get_data()
        if len(times) > 0:
            times = times - times[0]
            for i, curve in enumerate(self.ppg_curves):
                if i < len(ppg_data) and len(ppg_data[i]) > 0:
                    curve.setData(times, ppg_data[i])
        
        # Update heart rate
        times, hr_data = self.heart_rate_buffer.get_data()
        if len(times) > 0:
            times = times - times[0]
            if len(hr_data[0]) > 0:
                self.hr_curve.setData(times, hr_data[0])
        
        # Update IMU plots
        times, imu_data = self.imu_buffer.get_data()
        if len(times) > 0:
            times = times - times[0]
            # First 3 channels are accelerometer
            for i in range(3):
                if i < len(imu_data) and len(imu_data[i]) > 0:
                    self.accel_curves[i].setData(times, imu_data[i])
    
    def _update_spectrum(self, eeg_data: np.ndarray):
        """Update frequency spectrum plot"""
        # Compute FFT
        fs = 256  # EEG sampling rate
        freqs = np.fft.fftfreq(len(eeg_data), 1/fs)
        fft = np.abs(np.fft.fft(eeg_data))
        
        # Only keep positive frequencies up to 60 Hz
        mask = (freqs > 0) & (freqs < 60)
        freqs = freqs[mask]
        fft = fft[mask]
        
        # Apply smoothing
        if len(fft) > 10:
            from scipy.ndimage import gaussian_filter1d
            fft = gaussian_filter1d(fft, sigma=1)
        
        self.spectrum_curve.setData(freqs, fft)
    
    def update_eeg(self, data: Dict):
        """Update EEG data"""
        if 'channels' in data:
            channels = data['channels']
            timestamp = data.get('timestamp', datetime.now().timestamp())
            
            # Add each channel's samples
            for ch_name, samples in channels.items():
                ch_idx = int(ch_name[-1]) if ch_name.startswith('ch') else 0
                if ch_idx < 4:
                    for sample in samples:
                        self.eeg_buffer.buffers[ch_idx].append(sample)
                        self.eeg_buffer.timestamps.append(timestamp)
    
    def update_ppg(self, data: Dict):
        """Update PPG data"""
        if 'samples' in data:
            samples = data['samples']
            timestamp = data.get('timestamp', datetime.now().timestamp())
            
            # Assuming samples are for IR channel
            for sample in samples:
                self.ppg_buffer.buffers[0].append(sample)
                self.ppg_buffer.timestamps.append(timestamp)
    
    def update_heart_rate(self, heart_rate: float):
        """Update heart rate value"""
        self.heart_rate_buffer.add_samples(heart_rate)
    
    def update_imu(self, data: Dict):
        """Update IMU data"""
        timestamp = data.get('timestamp', datetime.now().timestamp())
        
        if 'accel' in data:
            accel = data['accel']
            for i, val in enumerate(accel[:3]):
                self.imu_buffer.buffers[i].append(val)
                self.imu_buffer.timestamps.append(timestamp)
        
        if 'gyro' in data:
            gyro = data['gyro']
            for i, val in enumerate(gyro[:3]):
                self.imu_buffer.buffers[i+3].append(val)
                self.imu_buffer.timestamps.append(timestamp)
    
    def run(self):
        """Start the visualization"""
        self.app.exec_()
    
    def close(self):
        """Close the visualization window"""
        self.win.close()
        self.app.quit()


class PlotlyDashVisualizer:
    """Web-based interactive visualizer using Plotly and Dash"""
    
    def __init__(self, port: int = 8050, update_interval: int = 1000):
        """
        Initialize Plotly/Dash visualizer
        
        Args:
            port: Port for web server
            update_interval: Update interval in milliseconds
        """
        if not PLOTLY_AVAILABLE:
            raise ImportError("Plotly/Dash not installed. Install with: pip install plotly dash")
        
        self.port = port
        self.update_interval = update_interval
        
        # Data buffers
        self.eeg_buffer = DataBuffer(maxlen=1000, channels=4)
        self.ppg_buffer = DataBuffer(maxlen=500, channels=1)
        self.heart_rate_buffer = DataBuffer(maxlen=60, channels=1)
        
        # Setup Dash app
        self.app = dash.Dash(__name__)
        self._setup_layout()
        self._setup_callbacks()
    
    def _setup_layout(self):
        """Setup Dash layout"""
        self.app.layout = html.Div([
            html.H1('Muse S Real-time Data Visualization', 
                   style={'text-align': 'center', 'color': '#2c3e50'}),
            
            html.Div([
                # EEG Plots
                dcc.Graph(id='eeg-graph', style={'height': '400px'}),
                
                # PPG and Heart Rate
                html.Div([
                    dcc.Graph(id='ppg-graph', style={'height': '300px', 'width': '50%', 'display': 'inline-block'}),
                    dcc.Graph(id='hr-graph', style={'height': '300px', 'width': '50%', 'display': 'inline-block'}),
                ]),
                
                # Frequency Spectrum
                dcc.Graph(id='spectrum-graph', style={'height': '300px'}),
            ]),
            
            # Auto-update interval
            dcc.Interval(
                id='interval-component',
                interval=self.update_interval,  # in milliseconds
                n_intervals=0
            ),
            
            # Info panel
            html.Div(id='info-panel', style={
                'position': 'fixed',
                'top': '10px',
                'right': '10px',
                'background': 'rgba(255,255,255,0.9)',
                'padding': '10px',
                'border-radius': '5px',
                'box-shadow': '0 2px 4px rgba(0,0,0,0.1)'
            })
        ])
    
    def _setup_callbacks(self):
        """Setup Dash callbacks for updating plots"""
        
        @self.app.callback(
            [Output('eeg-graph', 'figure'),
             Output('ppg-graph', 'figure'),
             Output('hr-graph', 'figure'),
             Output('spectrum-graph', 'figure'),
             Output('info-panel', 'children')],
            [Input('interval-component', 'n_intervals')]
        )
        def update_graphs(n):
            # Create EEG figure
            times, eeg_data = self.eeg_buffer.get_data()
            
            fig_eeg = make_subplots(
                rows=4, cols=1,
                subplot_titles=[f'EEG Channel {i+1}' for i in range(4)],
                vertical_spacing=0.05
            )
            
            if len(times) > 0:
                times = times - times[0]
                colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4']
                
                for i in range(4):
                    if i < len(eeg_data) and len(eeg_data[i]) > 0:
                        fig_eeg.add_trace(
                            go.Scatter(x=times, y=eeg_data[i], 
                                     line=dict(color=colors[i], width=2),
                                     name=f'Ch{i+1}'),
                            row=i+1, col=1
                        )
            
            fig_eeg.update_layout(
                title='EEG Signals',
                showlegend=False,
                height=400,
                margin=dict(t=50, b=30, l=50, r=30)
            )
            fig_eeg.update_xaxes(title_text='Time (s)', row=4, col=1)
            fig_eeg.update_yaxes(title_text='μV')
            
            # Create PPG figure
            times, ppg_data = self.ppg_buffer.get_data()
            fig_ppg = go.Figure()
            
            if len(times) > 0:
                times = times - times[0]
                if len(ppg_data[0]) > 0:
                    fig_ppg.add_trace(go.Scatter(
                        x=times, y=ppg_data[0],
                        line=dict(color='#FF1744', width=2),
                        name='PPG'
                    ))
            
            fig_ppg.update_layout(
                title='PPG Signal',
                xaxis_title='Time (s)',
                yaxis_title='Amplitude',
                height=300,
                margin=dict(t=50, b=30, l=50, r=30)
            )
            
            # Create Heart Rate figure
            times, hr_data = self.heart_rate_buffer.get_data()
            fig_hr = go.Figure()
            
            if len(times) > 0:
                times = times - times[0]
                if len(hr_data[0]) > 0:
                    fig_hr.add_trace(go.Scatter(
                        x=times, y=hr_data[0],
                        mode='lines+markers',
                        line=dict(color='#FF5252', width=3),
                        marker=dict(size=8, color='#FF1744'),
                        name='Heart Rate'
                    ))
            
            fig_hr.update_layout(
                title='Heart Rate Trend',
                xaxis_title='Time (s)',
                yaxis_title='BPM',
                yaxis_range=[40, 120],
                height=300,
                margin=dict(t=50, b=30, l=50, r=30)
            )
            
            # Create Spectrum figure (simplified for now)
            fig_spectrum = go.Figure()
            fig_spectrum.update_layout(
                title='Frequency Spectrum',
                xaxis_title='Frequency (Hz)',
                yaxis_title='Power',
                height=300,
                margin=dict(t=50, b=30, l=50, r=30)
            )
            
            # Info panel
            info = html.Div([
                html.P(f'Update: {n}'),
                html.P(f'EEG Samples: {len(self.eeg_buffer.timestamps)}'),
                html.P(f'PPG Samples: {len(self.ppg_buffer.timestamps)}'),
            ])
            
            return fig_eeg, fig_ppg, fig_hr, fig_spectrum, info
    
    def update_eeg(self, data: Dict):
        """Update EEG data"""
        if 'channels' in data:
            for ch_name, samples in data['channels'].items():
                ch_idx = int(ch_name[-1]) if ch_name.startswith('ch') else 0
                if ch_idx < 4:
                    for sample in samples:
                        self.eeg_buffer.buffers[ch_idx].append(sample)
                        self.eeg_buffer.timestamps.append(datetime.now().timestamp())
    
    def update_ppg(self, data: Dict):
        """Update PPG data"""
        if 'samples' in data:
            for sample in data['samples']:
                self.ppg_buffer.add_samples(sample)
    
    def update_heart_rate(self, heart_rate: float):
        """Update heart rate"""
        self.heart_rate_buffer.add_samples(heart_rate)
    
    def run(self, debug: bool = False):
        """Start the web server"""
        print(f"Starting web visualization at http://localhost:{self.port}")
        self.app.run_server(debug=debug, port=self.port)


class MuseVisualizer:
    """Main visualizer class with backend selection"""
    
    def __init__(self, backend: str = 'auto', **kwargs):
        """
        Initialize visualizer with specified backend
        
        Args:
            backend: 'pyqtgraph', 'plotly', 'matplotlib', or 'auto'
            **kwargs: Backend-specific arguments
        """
        self.backend = backend
        self.visualizer = None
        
        if backend == 'auto':
            if PYQTGRAPH_AVAILABLE:
                backend = 'pyqtgraph'
            elif PLOTLY_AVAILABLE:
                backend = 'plotly'
            elif MATPLOTLIB_AVAILABLE:
                backend = 'matplotlib'
            else:
                raise ImportError("No visualization backend available. Install pyqtgraph, plotly, or matplotlib")
        
        if backend == 'pyqtgraph':
            if not PYQTGRAPH_AVAILABLE:
                raise ImportError("PyQtGraph not installed. Install with: pip install pyqtgraph")
            self.visualizer = PyQtGraphVisualizer(**kwargs)
        
        elif backend == 'plotly':
            if not PLOTLY_AVAILABLE:
                raise ImportError("Plotly/Dash not installed. Install with: pip install plotly dash")
            self.visualizer = PlotlyDashVisualizer(**kwargs)
        
        elif backend == 'matplotlib':
            if not MATPLOTLIB_AVAILABLE:
                raise ImportError("Matplotlib not installed. Install with: pip install matplotlib")
            # For simplicity, fall back to PyQtGraph if available
            if PYQTGRAPH_AVAILABLE:
                self.visualizer = PyQtGraphVisualizer(**kwargs)
            else:
                raise NotImplementedError("Matplotlib backend not fully implemented. Use pyqtgraph or plotly")
        
        else:
            raise ValueError(f"Unknown backend: {backend}")
        
        print(f"Initialized {backend} visualizer")
    
    def update_eeg(self, data: Dict):
        """Update EEG data"""
        if self.visualizer and hasattr(self.visualizer, 'update_eeg'):
            self.visualizer.update_eeg(data)
    
    def update_ppg(self, data: Dict):
        """Update PPG data"""
        if self.visualizer and hasattr(self.visualizer, 'update_ppg'):
            self.visualizer.update_ppg(data)
    
    def update_heart_rate(self, heart_rate: float):
        """Update heart rate"""
        if self.visualizer and hasattr(self.visualizer, 'update_heart_rate'):
            self.visualizer.update_heart_rate(heart_rate)
    
    def update_imu(self, data: Dict):
        """Update IMU data"""
        if self.visualizer and hasattr(self.visualizer, 'update_imu'):
            self.visualizer.update_imu(data)
    
    def run(self):
        """Start the visualization"""
        if self.visualizer:
            self.visualizer.run()
    
    def close(self):
        """Close the visualization"""
        if self.visualizer and hasattr(self.visualizer, 'close'):
            self.visualizer.close()


if __name__ == "__main__":
    # Test visualization with simulated data
    import time
    
    print("Muse Visualizer Test")
    print("=" * 60)
    print("Available backends:")
    print(f"  PyQtGraph: {PYQTGRAPH_AVAILABLE}")
    print(f"  Plotly: {PLOTLY_AVAILABLE}")
    print(f"  Matplotlib: {MATPLOTLIB_AVAILABLE}")
    
    # Create visualizer
    viz = MuseVisualizer(backend='auto')
    
    # Simulate data updates in a thread
    def simulate_data():
        while True:
            # Simulate EEG data
            eeg_data = {
                'channels': {
                    'ch0': [np.random.randn() * 100 for _ in range(12)],
                    'ch1': [np.random.randn() * 100 for _ in range(12)],
                    'ch2': [np.random.randn() * 100 for _ in range(12)],
                    'ch3': [np.random.randn() * 100 for _ in range(12)],
                },
                'timestamp': datetime.now().timestamp()
            }
            viz.update_eeg(eeg_data)
            
            # Simulate PPG data
            ppg_data = {
                'samples': [50000 + np.random.randn() * 1000 for _ in range(7)],
                'timestamp': datetime.now().timestamp()
            }
            viz.update_ppg(ppg_data)
            
            # Simulate heart rate
            hr = 70 + np.random.randn() * 10
            viz.update_heart_rate(hr)
            
            # Simulate IMU data
            imu_data = {
                'accel': [np.random.randn() * 0.1 for _ in range(3)],
                'gyro': [np.random.randn() * 10 for _ in range(3)],
                'timestamp': datetime.now().timestamp()
            }
            viz.update_imu(imu_data)
            
            time.sleep(0.1)  # 10 Hz update rate
    
    # Start data simulation in background
    import threading
    data_thread = threading.Thread(target=simulate_data, daemon=True)
    data_thread.start()
    
    # Run visualization
    viz.run()