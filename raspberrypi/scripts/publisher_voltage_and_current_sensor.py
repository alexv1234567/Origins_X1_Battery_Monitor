import smbus
import time
import zmq
import concurrent.futures

INA226_I2C_ADDR     = 0x40
REG_CONFIG          = 0x00
REG_SHUNT_VOLTAGE   = 0x01
REG_BUS_VOLTAGE     = 0x02
RESET_COMMAND       = 0x8000

# Shunt resistor parameters
SHUNT_RESISTOR = 0.1      # Ohms
SHUNT_LSB      = 2.5e-6   # INA226 shunt voltage 

# Tolerance used to judge if the reading is "stable" and unchanging
TOLERANCE = 0.001  
STABLE_THRESHOLD = 3  # cycles of unchanging voltage to force reinit

FAILURE_THRESHOLD = 3  # consecutive failures -> reinit
VALID_READ_COUNT_FOR_RECONNECT = 2  # confirm reconnection after N valid reads

try:
    bus = smbus.SMBus(1)
except FileNotFoundError:
    print("Error: I2C bus not found.")
    exit(1)


#I2C helpers

def write_register(register, value):
    data = [(value >> 8) & 0xFF, value & 0xFF]
    bus.write_i2c_block_data(INA226_I2C_ADDR, register, data)

def read_register(register):
    data = bus.read_i2c_block_data(INA226_I2C_ADDR, register, 2)
    value = (data[0] << 8) | data[1]
    return value


# INA226 Functions

def reset_ina226():
    try:
        write_register(REG_CONFIG, RESET_COMMAND)
        time.sleep(0.1)
        print("INA226 has been reset.")
    except Exception as e:
        print("Failed to reset INA226:", e)

def configure_ina226():
    config_value = 0x4127  
    try:
        write_register(REG_CONFIG, config_value)
        time.sleep(0.1)
        print(f"INA226 configured (CONFIG=0x{config_value:04X}).")
    except Exception as e:
        print("Failed to configure INA226:", e)

def measure_bus_voltage():
    try:
        raw = read_register(REG_BUS_VOLTAGE)
        voltage_mV = raw * 1.25
        voltage_V  = voltage_mV / 1000.0
        return voltage_V
    except Exception:
        return None

def measure_shunt_current():
    try:
        raw = read_register(REG_SHUNT_VOLTAGE)
        if raw > 0x7FFF:
            raw -= 0x10000
        shunt_voltage_V = raw * SHUNT_LSB
        current_A = shunt_voltage_V / SHUNT_RESISTOR
        return current_A
    except Exception:
        return None

def is_sensor_present():
    try:
        _ = read_register(REG_CONFIG)
        return True
    except Exception:
        return False

# State of Charge (SoC) Estimation

def estimate_soc(voltage):
    """
    Example for a multi-cell battery:
      min_v = 14.8   # 0% 
      max_v = 16.85  # 100%
    Adjust as needed for your battery configuration.
    """
    min_v = 14.8
    max_v = 16.85

    if voltage is None:
        return 0.0
    if voltage <= min_v:
        return 0.0
    elif voltage >= max_v:
        return 100.0
    else:
        return (voltage - min_v) / (max_v - min_v) * 100.0


# Main Script (Publisher)

if __name__ == "__main__":
    reset_ina226()
    configure_ina226()

    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    # IP address/port for publisher must be the same as the subscriber
    socket.bind("tcp://192.168.1.15:5555")

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    def safe_read_voltage(timeout=1.0):
        future = executor.submit(measure_bus_voltage)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return None

    def safe_read_current(timeout=1.0):
        future = executor.submit(measure_shunt_current)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return None

    sensor_connected = False
    consecutive_failures = 0
    valid_read_count = 0
    last_voltage = None
    stable_count = 0

    try:
        while True:
            voltage = safe_read_voltage()
            current = safe_read_current()

            if (voltage is None or voltage < 0.1):
                consecutive_failures += 1
                valid_read_count = 0
                stable_count = 0

                if sensor_connected:
                    sensor_connected = False
                    print("Battery Disconnected")

                if (consecutive_failures >= FAILURE_THRESHOLD) and is_sensor_present():
                    print("Reinitializing sensor due to consecutive failures...")
                    reset_ina226()
                    configure_ina226()
                    time.sleep(0.5)
                    consecutive_failures = 0

                voltage_str = "Battery Disconnected"
                current_str = "N/A"
                soc_str = "N/A"

            else:
                consecutive_failures = 0
                valid_read_count += 1

                soc_percentage = estimate_soc(voltage)

                voltage_str = f"{voltage:.3f} V"
                current_str = f"{current:.6f} A" if current is not None else "N/A"
                soc_str = f"{soc_percentage:.1f}%"

                if last_voltage is not None and abs(voltage - last_voltage) < TOLERANCE:
                    stable_count += 1
                else:
                    stable_count = 0

                if stable_count >= STABLE_THRESHOLD:
                    print("Forcing sensor reinitialization (unchanging voltage).")
                    reset_ina226()
                    configure_ina226()
                    time.sleep(0.25)
                    voltage = safe_read_voltage()
                    current = safe_read_current()
                    stable_count = 0

                if not sensor_connected and valid_read_count >= VALID_READ_COUNT_FOR_RECONNECT:
                    sensor_connected = True
                    print("Battery Reconnected")

                last_voltage = voltage

            publish_str = f"Voltage: {voltage_str}, Current: {current_str}, SoC: {soc_str}"
            print(f"Publishing: {publish_str}")
            socket.send_string(publish_str)

            # Interval 1 second
            time.sleep(1)

    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        executor.shutdown(wait=False)
        bus.close()
        socket.close()
        context.term()