import sys
import re
import time

import zmq
import pyqtgraph as pg
from pyqtgraph.Qt import QtGui, QtCore

from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import QThread, pyqtSignal


# Subscriber Thread

class BatterySubscriber(QThread):
    """
    A QThread that subscribes to your ZeroMQ publisher.
    Emits new_message(str) whenever a new message arrives.
    """
    new_message = pyqtSignal(str)

    def __init__(self, zmq_url="tcp://192.168.1.15:5555"):
        super().__init__()
        self.zmq_url = zmq_url
        self.running = True

    def run(self):
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.connect(self.zmq_url)
        # Subscribe to all messages
        socket.setsockopt_string(zmq.SUBSCRIBE, "")
        poller = zmq.Poller()
        poller.register(socket, zmq.POLLIN)

        while self.running:
            # Wait up to 100 ms for data
            socks = dict(poller.poll(100))
            if socket in socks and socks[socket] == zmq.POLLIN:
                message = socket.recv_string()
                self.new_message.emit(message)

        socket.close()
        context.term()

    def stop(self):
        self.running = False
        self.wait()


# Main Window

class MainWindow(QWidget):
    def __init__(self, zmq_url="tcp://192.168.1.15:5555"):
        super().__init__()

        self.setWindowTitle("Battery Monitor")
        self.resize(1000, 600)

        # Layout: label for time-left, plus three plot widgets
        layout = QVBoxLayout()
        self.setLayout(layout)

        
        self.time_left_label = QLabel("Time Left: --:--")
        layout.addWidget(self.time_left_label)

        # Create the 3 plot widgets using PyQtGraph.
        self.voltage_plot = pg.PlotWidget()
        self.voltage_plot.setTitle("Voltage (V)")
        layout.addWidget(self.voltage_plot)

        self.current_plot = pg.PlotWidget()
        self.current_plot.setTitle("Current (A)")
        layout.addWidget(self.current_plot)

        self.soc_plot = pg.PlotWidget()
        self.soc_plot.setTitle("State of Charge (%)")
        layout.addWidget(self.soc_plot)

        # Data storage
        self.time_data = []
        self.voltage_data = []
        self.current_data = []
        self.soc_data = []
        self.max_points = 300  # Rolling window of data

        # Create plot curves
        self.voltage_curve = self.voltage_plot.plot(pen='y', name="Voltage")
        self.current_curve = self.current_plot.plot(pen='r', name="Current")
        self.soc_curve = self.soc_plot.plot(pen='g', name="SoC")

        # Initialize filtered SoC attribute for smoothing
        self.filtered_soc = None

        # Start the ZeroMQ subscriber thread
        self.subscriber = BatterySubscriber(zmq_url)
        self.subscriber.new_message.connect(self.handle_new_message)
        self.subscriber.start()

        # Time reference for x-axis in seconds
        self.start_time = time.time()

        self.battery_capacity = 10.0  # [Ah]

        # Timer to update the plots 5x per second
        self.update_timer = QtCore.QTimer()
        self.update_timer.timeout.connect(self.update_plots)
        self.update_timer.start(200)

    def handle_new_message(self, msg):
        """
        Parse the incoming string from the publisher,
        e.g. "Voltage: 15.234 V, Current: 0.1150 A, SoC: 40.2%"
        and update sensor data. The SoC value is smoothed to reduce fluctuations.
        """
        match = re.search(
            r"Voltage:\s*([\d.]+)\s*V,\s*Current:\s*([\d.]+)\s*A,\s*SoC:\s*([\d.]+)%",
            msg
        )
        if match:
            try:
                voltage_val = float(match.group(1))
                current_val = float(match.group(2))
                soc_val = float(match.group(3))
            except ValueError:
                return  # Invalid parse

            elapsed_time = time.time() - self.start_time
            self.time_data.append(elapsed_time)
            self.voltage_data.append(voltage_val)
            self.current_data.append(current_val)

            # Apply exponential smoothing to the SoC value.
            alpha = 0.2  # Smoothing factor
            if self.filtered_soc is None:
                self.filtered_soc = soc_val
            else:
                self.filtered_soc = alpha * soc_val + (1 - alpha) * self.filtered_soc

            # Append the filtered SoC to our data for plotting.
            self.soc_data.append(self.filtered_soc)

            
            if len(self.time_data) > self.max_points:
                self.time_data = self.time_data[-self.max_points:]
                self.voltage_data = self.voltage_data[-self.max_points:]
                self.current_data = self.current_data[-self.max_points:]
                self.soc_data = self.soc_data[-self.max_points:]

            # Estimate battery time left using the filtered SoC value
            self.update_time_left(self.filtered_soc, current_val)

    def update_time_left(self, soc_percent, current_amp):
        """
        Simple approximation of time left:
          hours_left = (BatteryCapacity * SoC%) / 100 / current
        """
        if current_amp < 0.01 or soc_percent < 1.0:
            self.time_left_label.setText("Time Left: N/A")
            return

        hours_left = (self.battery_capacity * (soc_percent / 100.0)) / current_amp
        total_minutes = int(hours_left * 60)
        seconds = int((hours_left * 3600) % 60)

        if total_minutes < 60:
            self.time_left_label.setText(f"Time Left: {total_minutes} min {seconds} s")
        else:
            hrs = total_minutes // 60
            mins = total_minutes % 60
            self.time_left_label.setText(f"Time Left: {hrs} h {mins} min {seconds} s")

    def update_plots(self):
        """
        Update the data for the three plots (Voltage, Current, SoC)
        and update the plot titles to display the latest numerical values.
        """
        if not self.time_data:
            return

        # Update curves with new data
        self.voltage_curve.setData(self.time_data, self.voltage_data)
        self.current_curve.setData(self.time_data, self.current_data)
        self.soc_curve.setData(self.time_data, self.soc_data)

        # updated data point for each measurement
        last_voltage = self.voltage_data[-1]
        last_current = self.current_data[-1]
        last_soc = self.soc_data[-1]

        # Update the titles with the real-time numerical values right under the title.
        self.voltage_plot.setTitle(
            f"Voltage (V)<br><span style='font-size:14px; color:#FFF;'>{last_voltage:.3f} V</span>"
        )
        self.current_plot.setTitle(
            f"Current (A)<br><span style='font-size:14px; color:#FFF;'>{last_current:.4f} A</span>"
        )
        self.soc_plot.setTitle(
            f"State of Charge (%)<br><span style='font-size:14px; color:#FFF;'>{last_soc:.1f} %</span>"
        )

        # Update X-range based on time data
        x_min = self.time_data[0]
        x_max = self.time_data[-1]

        # Manually update Y-axis range for each plot
        v_min = min(self.voltage_data)
        v_max = max(self.voltage_data)
        v_range = v_max - v_min if v_max != v_min else 1.0
        v_margin = v_range * 0.1
        self.voltage_plot.setXRange(x_min, x_max, padding=0.01)
        self.voltage_plot.setYRange(v_min - v_margin, v_max + v_margin)

        c_min = min(self.current_data)
        c_max = max(self.current_data)
        c_range = c_max - c_min if c_max != c_min else 1.0
        c_margin = c_range * 0.1
        self.current_plot.setXRange(x_min, x_max, padding=0.01)
        self.current_plot.setYRange(c_min - c_margin, c_max + c_margin)

        s_min = min(self.soc_data)
        s_max = max(self.soc_data)
        s_range = s_max - s_min if s_max != s_min else 1.0
        s_margin = s_range * 0.1
        self.soc_plot.setXRange(x_min, x_max, padding=0.01)
        self.soc_plot.setYRange(s_min - s_margin, s_max + s_margin)

    def closeEvent(self, event):
        """
        Stop the subscriber thread on window close.
        """
        self.subscriber.stop()
        event.accept()

# Application Entry Point

def main():
    app = QApplication(sys.argv)
    window = MainWindow("tcp://192.168.1.15:5555")
    window.show()

    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        window.subscriber.stop()
        print("Application interrupted by user.")

if __name__ == "__main__":
    main()
