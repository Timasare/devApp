import streamlit as st
import requests
from geopy.geocoders import Nominatim
import numpy as np
from datetime import datetime

# === Location Utility ===
def get_coordinates(location):
    geolocator = Nominatim(user_agent="solar_estimator")
    loc = geolocator.geocode(location)
    if not loc:
        raise ValueError("Could not find location. Please enter a valid city or region.")
    return loc.latitude, loc.longitude

# === PVGIS Solar Irradiance (Primary) ===
def get_irradiance_pvgis(lat, lon):
    url = (
        f"https://re.jrc.ec.europa.eu/api/v5_2/seriescalc?"
        f"lat={lat}&lon={lon}&startyear=2020&endyear=2020"
        f"&month=1&day=1&hour=0&optimize=1&pvtechchoice=crystSi"
        f"&mountingplace=fixed&loss=14&outputformat=json"
    )
    response = requests.get(url)
    data = response.json()
    try:
        irradiance_values = [float(i['G(i)']) for i in data['outputs']['hourly']]
        annual_irradiance = sum(irradiance_values) / 1000  # Wh/m² to kWh/m²
        return round(annual_irradiance / 365, 2)
    except Exception:
        raise ValueError("PVGIS failed")

# === NASA POWER Fallback ===
def get_irradiance_nasa(lat, lon):
    url = (
        f"https://power.larc.nasa.gov/api/temporal/climatology/point?"
        f"parameters=ALLSKY_SFC_SW_DWN&community=RE&longitude={lon}&latitude={lat}"
        f"&format=JSON"
    )
    response = requests.get(url)
    data = response.json()
    try:
        values = list(data['properties']['parameter']['ALLSKY_SFC_SW_DWN'].values())
        avg_daily_irradiance = sum(values) / len(values)
        return round(avg_daily_irradiance, 2)
    except Exception:
        raise ValueError("NASA POWER fallback also failed")

# === Energy + Financial Estimations ===
def estimate_energy_potential(irradiance, area_m2, panel_efficiency):
    return irradiance * 365 * area_m2 * panel_efficiency

def size_components(energy_kWh_per_year):
    daily_energy = energy_kWh_per_year / 365
    panel_wattage = 350
    PSH = 4.5
    panels_needed = daily_energy / (panel_wattage * PSH / 1000)
    inverter_size_kW = daily_energy / PSH
    battery_size_kWh = daily_energy * 0.5
    return int(np.ceil(panels_needed)), round(inverter_size_kW, 2), round(battery_size_kWh, 2)

def calculate_lcoe(total_cost, annual_energy_kWh, system_lifetime=25):
    return total_cost / (annual_energy_kWh * system_lifetime)

def calculate_discounted_payback(total_cost, annual_savings, interest_rate, lifetime=25):
    cash_flows = np.array([annual_savings / ((1 + interest_rate) ** year) for year in range(1, lifetime + 1)])
    cumulative = np.cumsum(cash_flows)
    if cumulative[-1] < total_cost:
        return None
    return np.argmax(cumulative >= total_cost) + 1

# === Streamlit UI ===
st.set_page_config(page_title="Solar Energy Estimator", layout="centered")
st.title("🔋 Renewable Energy Estimator")
st.markdown("Estimate solar energy potential, component sizing, and project economics using free satellite data (PVGIS & NASA POWER).")

# === User Inputs ===
location = st.text_input("📍 Enter location", "Accra, Ghana")
area_m2 = st.number_input("📐 Area available (m²)", min_value=1.0, value=100.0)
interest_rate = st.number_input("💰 Interest rate (e.g., 0.08 = 8%)", min_value=0.0, value=0.08)
panel_efficiency = st.number_input("⚡ Panel efficiency (0.1 to 0.25)", min_value=0.1, max_value=0.25, value=0.18)

# === Process ===
if st.button("Estimate Solar Potential"):
    try:
        lat, lon = get_coordinates(location)
        st.markdown(f"📌 Coordinates: **Lat:** {lat:.4f}, **Lon:** {lon:.4f}")
        
        try:
            irradiance = get_irradiance_pvgis(lat, lon)
            st.success("✅ Data source: PVGIS")
        except:
            irradiance = get_irradiance_nasa(lat, lon)
            st.warning("⚠️ PVGIS failed. Used NASA POWER as fallback.")

        energy_kWh = estimate_energy_potential(irradiance, area_m2, panel_efficiency)
        panels, inverter_kW, battery_kWh = size_components(energy_kWh)

        cost_per_watt = 0.5
        bos_cost = 0.15
        battery_cost = 200
        system_capacity_kW = panels * 0.35
        total_cost = (system_capacity_kW * (cost_per_watt + bos_cost) * 1000 +
                      battery_kWh * battery_cost)

        lcoe = calculate_lcoe(total_cost, energy_kWh)
        savings = energy_kWh * 0.15
        payback = calculate_discounted_payback(total_cost, savings, interest_rate)

        # === Results ===
        st.subheader("🔍 Results Summary")
        st.markdown(f"**☀️ Avg. Irradiance:** `{irradiance:.2f}` kWh/m²/day")
        st.markdown(f"**⚡ Annual Energy Output:** `{energy_kWh:.0f}` kWh")
        st.markdown(f"**🧱 System Components:** `{panels}` panels | `{inverter_kW}` kW inverter | `{battery_kWh}` kWh battery")
        st.markdown(f"**💰 Estimated System Cost:** `${total_cost:,.2f}`")
        st.markdown(f"**📉 LCOE:** `${lcoe:.04f}` / kWh")
        st.markdown(f"**⏳ Discounted Payback Period:** `{payback if payback else 'Not recovered in 25 years'}` years")

    except Exception as e:
        st.error(f"❌ Error: {e}")
