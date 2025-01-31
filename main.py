import datetime
import requests
from bs4 import BeautifulSoup
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util
import voluptuous as vol
import plotly.graph_objects as go
from datetime import timedelta
import logging

DOMAIN = "price_chart"
URL = "https://elektra.p5.lt/"
SCAN_INTERVAL = timedelta(minutes=30)
UPDATE_TIMES = ["00:00", "14:00"]

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional('update_interval', default=30): vol.Coerce(int),
        vol.Optional('main_update_times', default=UPDATE_TIMES): vol.All(list, [str]),
        vol.Optional('price_controls', default=[]): vol.All(list, [{
            vol.Required('entity_id'): str,
            vol.Required('price_threshold'): vol.Coerce(float),
            vol.Required('action'): vol.In(['turn_on', 'turn_off']),
            vol.Optional('start_time', default='00:00'): str,
            vol.Optional('end_time', default='23:59'): str,
        }])
    })
})

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]
    price_controls = conf.get('price_controls', [])

    async def check_price_controls(current_prices):
        current_time = dt_util.now()
        current_hour = current_time.strftime('%H:00')

        if not current_prices or current_hour not in current_prices:
            return

        current_price = current_prices[current_hour]

        for control in price_controls:
            entity_id = control['entity_id']
            threshold = control['price_threshold']
            action = control['action']
            start_time = datetime.datetime.strptime(control['start_time'], '%H:%M').time()
            end_time = datetime.datetime.strptime(control['end_time'], '%H:%M').time()
            current_time = current_time.time()

            if start_time <= current_time <= end_time:
                should_activate = current_price <= threshold if action == 'turn_on' else current_price > threshold

                if should_activate:
                    service = f"homeassistant.{action}"
                    await hass.services.async_call(
                        'homeassistant',
                        action,
                        {'entity_id': entity_id}
                    )
                    _LOGGER.info(f"Triggered {action} for {entity_id} (price: {current_price}, threshold: {threshold})")
                    log_action(entity_id, action, current_price, threshold)

    async def async_update_prices(now=None):
        _LOGGER.info("Updating electricity prices...")
        today_data, tomorrow_data = await hass.async_add_executor_job(fetch_price_data)

        if today_data and tomorrow_data:
            today_periods, today_prices = today_data
            current_prices = dict(zip(today_periods, today_prices))

            await check_price_controls(current_prices)

            await generate_chart(today_data, tomorrow_data)
            hass.states.async_set(f"{DOMAIN}.last_update", dt_util.now().isoformat())
            _LOGGER.info("Price update successful")
        else:
            _LOGGER.warning("Failed to update prices")

    async def manual_device_control(call):
        entity_id = call.data.get('entity_id')
        action = call.data.get('action')
        if entity_id and action in ['turn_on', 'turn_off']:
            await hass.services.async_call(
                'homeassistant',
                action,
                {'entity_id': entity_id}
            )

    hass.services.async_register(DOMAIN, "update_prices", async_update_prices)
    hass.services.async_register(DOMAIN, "manual_device_control", manual_device_control)

    return True

def fetch_price_data():
    response = requests.get(URL)
    soup = BeautifulSoup(response.content, 'html.parser')
    today_data = ([], [])
    tomorrow_data = ([], [])
    return today_data, tomorrow_data

def log_action(entity_id, action, current_price, threshold):
    with open('action_history.log', 'a') as f:
        f.write(f"{dt_util.now().isoformat()}, {entity_id}, {action}, {current_price}, {threshold}\n")

async def generate_chart(today_data, tomorrow_data):
    today_periods, today_prices = today_data
    tomorrow_periods, tomorrow_prices = tomorrow_data

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=today_periods, y=today_prices, mode='lines+markers', name='Today'))
    fig.add_trace(go.Scatter(x=tomorrow_periods, y=tomorrow_prices, mode='lines+markers', name='Tomorrow'))
    fig.update_layout(title='Electricity Prices', xaxis_title='Time', yaxis_title='Price')
    fig.write_html('price_chart.html')
