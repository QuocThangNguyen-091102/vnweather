import requests
import pandas as pd

url = "https://archive-api.open-meteo.com/v1/archive"
params = {
    "latitude": 21.03,       # Hà Nội
    "longitude": 105.85,
    "start_date": "2024-01-01",
    "end_date": "2024-01-31",
    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
    "timezone": "Asia/Bangkok",
}

resp = requests.get(url, params=params, timeout=30)
resp.raise_for_status()

df = pd.DataFrame(resp.json()["daily"])
print(df.head())
print(len(df), "dòng")