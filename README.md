# Battery Monitoring System

This project implements a battery monitoring system using an INA226 sensor for measuring voltage and current, publishing the data over ZeroMQ, and displaying real-time visualizations with a PyQt-based GUI.

## File Names
- **Publisher:** `publisher_voltage_and_current_sensor.py`
- **Subscriber:** `subscriber_voltage_and_current_sensor.py`

## Prerequisites

### Required Python Packages
Install the necessary dependencies using pip:
```sh
pip install pyzmq zmq smbus futures time pyqtgraph PyQt6
```
This includes dependencies used for both the publisher and subscriber.

## Hardware Connections

The INA226 sensor communicates with the system via I2C. The required connections are as follows:

| INA226 Pin | Raspberry Pi Pin |
|------------|------------------|
| VCC        | 3.3V (Pin 1) or 5V (Pin 2/4) |
| GND        | GND (Pin 6, 9, 14, 20, etc.) |
| SDA        | SDA (Pin 3 - GPIO2) |
| SCL        | SCL (Pin 5 - GPIO3) |
| VBUS       | Max voltage pin of the LiPo battery |

Make sure I2C is enabled on your Raspberry Pi before running the scripts.

## Explanation of Key Variables

| Variable | Description |
|----------|-------------|
| `INA226_I2C_ADDR` | I2C address of the INA226 sensor |
| `REG_CONFIG` | Configuration register for INA226 |
| `REG_SHUNT_VOLTAGE` | Register for shunt voltage measurement |
| `REG_BUS_VOLTAGE` | Register for bus voltage measurement |
| `SHUNT_RESISTOR` | Value of the shunt resistor (Ohms) |
| `SHUNT_LSB` | Least Significant Bit value for shunt voltage |
| `TOLERANCE` | Tolerance level for detecting stable readings |
| `STABLE_THRESHOLD` | Number of stable readings before forcing sensor reinit |
| `FAILURE_THRESHOLD` | Consecutive failures before sensor reinit |
| `VALID_READ_COUNT_FOR_RECONNECT` | Required valid reads to confirm reconnection |

## Publisher Code (`publisher_voltage_and_current_sensor.py`)

The publisher reads voltage and current data from the INA226 sensor over I2C and publishes the information using ZeroMQ.

### Key Components
- **I2C Communication**: Uses `smbus` to communicate with the INA226 sensor.
- **Voltage & Current Measurement**:
  - `measure_bus_voltage()`: Reads bus voltage from the sensor.
  - `measure_shunt_current()`: Reads current by measuring the shunt voltage.
- **ZeroMQ Publisher**:
  - `socket.bind("tcp://192.168.1.15:5555")`: Binds to a specified IP and port for broadcasting.
  - Data format: `"Voltage: 15.234 V, Current: 0.1150 A, SoC: 40.2%"`
- **State of Charge (SoC) Calculation**:
  - `estimate_soc(voltage)`: Estimates battery charge level based on voltage.
- **Reinitialization Logic**:
  - If sensor readings are unstable or connection is lost, the sensor is reset and reconfigured.
- **Runs in a loop**, publishing data every second.

## Subscriber Code (`subscriber_voltage_and_current_sensor.py`)

The subscriber connects to the publisher and processes incoming sensor data for visualization.

### Key Components
- **ZeroMQ Subscriber**:
  - `socket.connect("tcp://192.168.1.15:5555")`: Connects to the publisher.
  - Listens for messages and emits a signal upon receiving new data.
- **Graphical Interface (PyQt & PyQtGraph)**:
  - `pyqtgraph` is used for real-time plotting of voltage, current, and SoC.
  - Data is displayed with rolling updates and exponential smoothing for stability.
- **Battery Time Estimation**:
  - Based on current consumption and estimated remaining charge, the GUI displays an estimated runtime remaining.
- **Real-time Data Updates**:
  - Uses a `QTimer` to refresh plots five times per second.

## Running the Application

1. **Start the Publisher** (on a machine connected to the INA226 sensor):
   ```sh
   python publisher_voltage_and_current_sensor.py
   ```
2. **Start the Subscriber** (on any machine in the same network):
   ```sh
   python subscriber_voltage_and_current_sensor.py
   ```

The subscriber GUI will display live data, updating in real-time from the publisher.

## Notes
- Ensure both publisher and subscriber are on the same network.
- The IP address in `tcp://192.168.1.15:5555` should be updated as needed.
- The INA226 sensor must be properly connected via I2C.
- If no data is received, check the I2C connection and the ZeroMQ network settings.

## Troubleshooting
- **No sensor detected?**
  - Ensure I2C is enabled on the device (`sudo i2cdetect -y 1`).
- **Subscriber not receiving data?**
  - Verify the correct IP address and port settings in both scripts.
- **Data updates are slow or inconsistent?**
  - Ensure the network connection is stable and not experiencing packet loss.

