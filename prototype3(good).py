import time
import board
import busio
from adafruit_pm25.i2c import PM25_I2C
import adafruit_sgp30
import adafruit_scd4x
import requests

# ----- Hue Setup -----
BRIDGE_IP = "192.168.0.241"
USERNAME = "QvpSl2f-rjT69huClZBDnHkyawCRZfEY16H9d-xR"
LIGHT_ID = 2
url = f"http://{BRIDGE_IP}/api/{USERNAME}/lights/{LIGHT_ID}/state"

# ----- I2C Setup -----
i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)

# ----- Sensor Initializations -----
pm25 = PM25_I2C(i2c, reset_pin=None)
sgp30 = adafruit_sgp30.Adafruit_SGP30(i2c)
scd40 = adafruit_scd4x.SCD4X(i2c)

# Initialize SGP30 baseline logic
sgp30.iaq_init()
sgp30.set_iaq_baseline(0x8973, 0x8aae)  # Optional: replace with your saved baseline

# Start SCD40 measurement
scd40.start_periodic_measurement()

# Track last Hue state
last_color = None
last_bri = None
last_hue = None

print("Monitoring air quality (PM2.5, VOC, CO2) and controlling Hue light...\n")

# ----- Functions -----
def get_distinct_green_hue(pm25):
    if pm25 <= 2:
        return 31000  # Yellow-Green
    elif pm25 <= 4:
        return 25500  # Lime Green
    elif pm25 <= 6:
        return 22000  # Spring Green
    elif pm25 <= 8:
        return 18000  # Seafoam Green
    else:
        return 14000  # Teal Green

def map_pm25_to_brightness(pm25):
    if pm25 < 0:
        pm25 = 0
    elif pm25 > 10:
        return 25
    brightness = 254 - int((pm25 / 10) * (254 - 25))
    return max(25, min(brightness, 254))

# ----- Main Loop -----
while True:
    try:
        # Read PM2.5 data
        pm_data = pm25.read()
        pm25_value = pm_data["pm25 env"]

        # Read VOCs & eCO2
        tvoc = sgp30.TVOC
        eco2 = sgp30.eCO2

        # Read true CO2, temp, humidity
        if scd40.data_ready:
            co2 = scd40.CO2
            temperature = scd40.temperature
            humidity = scd40.relative_humidity
        else:
            co2 = temperature = humidity = None

        # Air quality logic based on PM2.5
        if pm25_value <= 12.0:
            air_quality = "Good"
            hue = get_distinct_green_hue(pm25_value)
            brightness = map_pm25_to_brightness(pm25_value)
            color_payload = {
                "on": True,
                "hue": hue,
                "sat": 254,
                "bri": brightness
            }
        elif 12.1 <= pm25_value <= 35.4:
            air_quality = "Okay"
            color_payload = {
                "on": True,
                "hue": 12750,  # Yellow
                "sat": 254,
                "bri": 100
            }
        else:
            air_quality = "Bad"
            color_payload = {
                "on": True,
                "hue": 0,      # Red
                "sat": 254,
                "bri": 80
            }

        # Print sensor data
        print(f"PM2.5: {pm25_value} ug/m^3 | TVOC: {tvoc} ppb | eCO2: {eco2} ppm", end='')
        if co2 is not None:
            print(f" | True CO2: {co2} ppm | Temp: {temperature:.1f}C | RH: {humidity:.1f}%")
        else:
            print(" | SCD40 data not ready")

        # Show Hue change details for "Good"
        if air_quality == "Good":
            print(f"Brightness: {color_payload['bri']} | Hue: {color_payload['hue']}")

        # Avoid redundant Hue commands
        current_hue = color_payload.get("hue", last_hue)
        current_bri = color_payload["bri"]
        if current_hue != last_hue or current_bri != last_bri or air_quality != last_color:
            response = requests.put(url, json=color_payload)
            print("Hue update:", response.json())
            last_color = air_quality
            last_bri = current_bri
            last_hue = current_hue

        print("-" * 40)

    except RuntimeError as e:
        print("Sensor read error:", e)
    except Exception as e:
        print("Unexpected error:", e)

    time.sleep(5)
