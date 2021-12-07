from datetime import datetime, timedelta
import logging
import operator
import json
import itertools
import requests
import urllib.parse
from bs4 import BeautifulSoup

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import (CONF_NAME, STATE_UNKNOWN)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import PlatformNotReady
from homeassistant.util import Throttle

import homeassistant.helpers.config_validation as cv

__version__ = '0.0.2'

_LOGGER = logging.getLogger(__name__)

CONF_OVEREENKOMST_ID = 'overeenkomst_id'
CONF_USERNAME = 'username'
CONF_PASSWORD = 'password'

DEFAULT_NAME = 'Energieverbruik'
DEFAULT_DATE_FORMAT = "%y-%m-%dT%H:%M:%S"

ATTR_NAME = 'name'
ATTR_UPDATE_CYCLE = 'update_cycle'
ATTR_ICON = 'icon'
ATTR_MEASUREMENT_DATE = 'date'
ATTR_UNIT_OF_MEASUREMENT = 'unit_of_measurement'

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=1800)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_USERNAME, default=CONF_USERNAME): cv.string,
    vol.Optional(CONF_PASSWORD, default=CONF_USERNAME): cv.string,
    vol.Optional(CONF_OVEREENKOMST_ID, default=''): cv.string,
})


def setup_platform(hass, config, add_entities, discovery_info=None):
    name = config.get(CONF_NAME)
    overeenkomst_id = config.get(CONF_OVEREENKOMST_ID)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)

    greenchoice_api = GreenchoiceApiData(overeenkomst_id, username, password)

    greenchoice_api.update()

    if greenchoice_api is None:
        raise PlatformNotReady

    if not greenchoice_api.result:
        _LOGGER.error(f'No results found from data request.')
        if greenchoice_api._found_overeenkomst_id:
            _LOGGER.error(f'Found overeenkomst_ids:\n{greenchoice_api._found_overeenkomst_id}')

    else:
        sensors = []
        for entityName in greenchoice_api.result:
            sensors.append(GreenchoiceSensor(greenchoice_api, name, overeenkomst_id, username, password, entityName))
        add_entities(sensors, True)


class GreenchoiceSensor(SensorEntity):
    def __init__(self, greenchoice_api, name, overeenkomst_id, username, password, measurement_type):
        self._json_data = greenchoice_api
        self._name = name
        self._overeenkomst_id = overeenkomst_id
        self._username = username
        self._password = password
        self._measurement_type = measurement_type
        self._measurement_date = None
        self._unit_of_measurement = None
        self._state = None
        self._icon = None
        self._device_class = None
        self._state_class = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def overeenkomst_id(self):
        return self._overeenkomst_id

    @property
    def username(self):
        return self._username

    @property
    def password(self):
        return self._password

    @property
    def icon(self):
        return self._icon

    @property
    def state(self):
        return self._state

    @property
    def measurement_type(self):
        return self._measurement_type

    @property
    def measurement_date(self):
        return self._measurement_date

    @property
    def attr_state_class(self):
        return self._attr_state_class

    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

    @property
    def device_class(self):
        return self._device_class

    def update(self):
        """Get the latest data from the Greenchoice API."""
        self._json_data.update()

        data = self._json_data.result

        if self._username == CONF_USERNAME or self._username is None:
            _LOGGER.error("Need a username!")
        elif self._password == CONF_PASSWORD or self._password is None:
            _LOGGER.error("Need a password!")
        elif self._overeenkomst_id == CONF_OVEREENKOMST_ID or self._overeenkomst_id is None:
            _LOGGER.error("Need a overeenkomst id (Check the logs for found ids)!")

        if data is None or self._measurement_type not in data:
            self._state = STATE_UNKNOWN
        else:
            self._state = data[self._measurement_type]
            self._measurement_date = datetime.now()

        if self._measurement_type == "cost_energy_kwh":
            self._icon = 'mdi:currency-eur'
            self._name = 'Energy Costs per kWh'
            self._device_class = 'monetary'
            self._unit_of_measurement = "€"
        if self._measurement_type == "cost_energy_daily_base":
            self._icon = 'mdi:currency-eur'
            self._name = 'Energy Costs daily base'
            self._device_class = 'monetary'
            self._unit_of_measurement = "€"
        if self._measurement_type == "cost_gas_m3":
            self._icon = 'mdi:currency-eur'
            self._name = 'Gas Costs per m³'
            self._device_class = 'monetary'
            self._unit_of_measurement = "€"
        if self._measurement_type == "cost_gas_daily_base":
            self._icon = 'mdi:currency-eur'
            self._name = 'Gas Costs daily base'
            self._device_class = 'monetary'
            self._unit_of_measurement = "€"

        if self._measurement_type == "usage_energy_total":
            self._icon = 'mdi:lightning-bolt'
            self._name = 'Total Energy Usage'
            self._device_class = 'energy'
            self._unit_of_measurement = "kWh"
            self._attr_state_class = "total_increasing"
        if self._measurement_type == "usage_gas_total":
            self._icon = 'mdi:fire'
            self._name = 'Total Gas Usage'
            self._device_class = 'gas'
            self._unit_of_measurement = "m³"
            self._attr_state_class = "total_increasing"


class GreenchoiceApiData:
    def __init__(self, overeenkomst_id, username, password):
        self._overeenkomst_id = overeenkomst_id
        self._username = username
        self._password = password
        self._found_overeenkomst_id = []
        self.result = {}

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        session = requests.Session()
        self.result = {}

        """ Get session parameters and verification token """
        try:
            url = "https://mijn.greenchoice.nl/contract/levering"
            headers = {}
            payload = {}
            response = session.get(url, headers=headers, data=payload)

            parsed_html = BeautifulSoup(response.text, 'html.parser')
            returnUrl = urllib.parse.unquote(parsed_html.find('input', attrs={"id": "ReturnUrl"})['value'])
            sessionParameters = {x[0] : x[1] for x in [x.split("=") for x in returnUrl.split('?')[1].split("&")]}
            verificationToken = parsed_html.find('input', attrs={"name": "__RequestVerificationToken"})['value']

            _LOGGER.debug(f'sessionParameters: {sessionParameters}\nverificationToken: {verificationToken}')

            if verificationToken is not None and returnUrl is not None:

                """ Send login request """
                try:
                    url = "https://sso.greenchoice.nl/Account/Login"
                    payload = {
                        'ReturnUrl': '/connect/authorize/callback',
                        'Username': self._username,
                        'Password': self._password,
                        '__RequestVerificationToken': verificationToken,
                    }
                    headers = {'content-type': 'application/x-www-form-urlencoded'}
                    response = session.post(url, headers=headers, data=payload)

                    """ Get credentials """
                    try:
                        url = "https://sso.greenchoice.nl/connect/authorize/callback"
                        payload = {
                            'client_id': sessionParameters["client_id"],
                            'redirect_uri': sessionParameters["redirect_uri"],
                            'response_type': sessionParameters["response_type"],
                            'scope': sessionParameters["scope"],
                        }
                        headers = {}
                        response = session.get(url, headers=headers, params=payload)
                        parsed_html = BeautifulSoup(response.text, 'html.parser')
                        CRED_code = parsed_html.find('input', attrs={"name": "code"})['value']
                        CRED_state = parsed_html.find('input', attrs={"name": "state"})['value']
                        CRED_session_state = parsed_html.find('input', attrs={"name": "session_state"})['value']

                        _LOGGER.debug(f'CRED_code: {CRED_code}\nCRED_state: {CRED_state}\nCRED_session_state: {CRED_session_state}')

                        if CRED_code is not None and CRED_state is not None and CRED_session_state is not None:

                            """ Sign in using credentials """
                            try:
                                url = 'https://mijn.greenchoice.nl/signin-oidc'
                                payload = {
                                    'code': CRED_code,
                                    'state': CRED_state,
                                    'session_state': CRED_session_state
                                }
                                headers = {}
                                response = session.post(url, headers=headers, data=payload)

                                if self._overeenkomst_id == '':
                                    """ Get overeenkomst_id """
                                    try:
                                        url = "https://mijn.greenchoice.nl/microbus/init"
                                        payload = {}
                                        headers = {}
                                        response = session.get(url, headers=headers, data=payload)
                                        returnData = json.loads(response.text)

                                        for address in returnData["klantgegevens"][0]["adressen"]:
                                            self._found_overeenkomst_id.append(f'overeenkomst_id: {address["overeenkomstId"]} at {address["straat"]} {address["huisnummer"]}')
                                        _LOGGER.debug(f'Found following overeenkomst_ids:\n{self._found_overeenkomst_id}')

                                    except requests.exceptions.RequestException as e:
                                        self.result = f'Unable to get overeenkomst_id.\n{e}'
                                        _LOGGER.error(self.result)

                                else:
                                    """ Get price data """
                                    try:
                                        url = "https://mijn.greenchoice.nl/microbus/request"
                                        payload = json.dumps({
                                            "name": "GetTariefOvereenkomst",
                                            "message": {
                                                "overeenkomstId": self._overeenkomst_id
                                            }
                                        })
                                        headers = {'content-type': 'application/json;charset=UTF-8'}
                                        response = session.post(url, headers=headers, data=payload)
                                        returnData = json.loads(response.text)
                                        self.result["cost_energy_kwh"] = returnData["stroom"]["leveringEnkelAllin"]
                                        self.result["cost_energy_daily_base"] = returnData["stroom"]["vastrechtPerDagIncBtw"] + returnData["stroom"]["netbeheerPerDagIncBtw"] - (returnData["stroom"]["rebTeruggaveIncBtw"] / returnData["stroom"]["daysInYear"])
                                        self.result["cost_gas_m3"] = returnData["gas"]["leveringAllin"]
                                        self.result["cost_gas_daily_base"] = returnData["gas"]["vastrechtPerDagIncBtw"] + returnData["gas"]["netbeheerPerDagIncBtw"]

                                        _LOGGER.debug(f'cost_energy_kwh: {self.result["cost_energy_kwh"]}\ncost_energy_daily_base: {self.result["cost_energy_daily_base"]}\ncost_gas_m3: {self.result["cost_gas_m3"]}\ncost_gas_daily_base: {self.result["cost_gas_daily_base"]}')

                                    except requests.exceptions.RequestException as e:
                                        self.result = f'Unable to get price data.\n{e}'
                                        _LOGGER.error(self.result)

                                    """ Get Energy usage data """
                                    try:
                                        url = "https://mijn.greenchoice.nl/microbus/request"
                                        payload = json.dumps({
                                            "name": "ProductkostenOphalenRequest",
                                            "message": {
                                                "productType": 1,
                                                "periodeType": 1,
                                                "jaar": int(datetime.now().strftime("%Y"))
                                            }
                                        })
                                        headers = {'content-type': 'application/json;charset=UTF-8'}
                                        response = session.post(url, headers=headers, data=payload)
                                        returnData = json.loads(response.text)
                                        self.result["usage_energy_total"] = returnData["series"][0]["values"][datetime.now().strftime("%Y")]

                                        _LOGGER.debug(f'usage_energy_total: {self.result["usage_energy_total"]}')

                                    except requests.exceptions.RequestException as e:
                                        self.result = f'Unable to get Energy usage data.\n{e}'
                                        _LOGGER.error(self.result)

                                    """ Get Gas usage data """
                                    try:
                                        url = "https://mijn.greenchoice.nl/microbus/request"
                                        payload = json.dumps({
                                            "name": "ProductkostenOphalenRequest",
                                            "message": {
                                                "productType": 2,
                                                "periodeType": 1,
                                                "jaar": int(datetime.now().strftime("%Y"))
                                            }
                                        })
                                        headers = {'content-type': 'application/json;charset=UTF-8'}
                                        response = session.post(url, headers=headers, data=payload)
                                        returnData = json.loads(response.text)
                                        self.result["usage_gas_total"] = returnData["series"][0]["values"][datetime.now().strftime("%Y")]

                                    except requests.exceptions.RequestException as e:
                                        self.result = f'Unable to get Gas usage data.\n{e}'
                                        _LOGGER.error(self.result)

                            except requests.exceptions.RequestException as e:
                                self.result = f'Unable to send credentials to login page.\n{e}'
                                _LOGGER.error(self.result)

                        else:
                            self.result = f'Could not parse credentials from response.'
                            _LOGGER.error(self.result)

                    except requests.exceptions.RequestException as e:
                        self.result = f'Unable to get credentials response.\n{e}'
                        _LOGGER.error(self.result)

                except requests.exceptions.RequestException as e:
                    self.result = f'Unable to send login request.\n{e}'
                    _LOGGER.error(self.result)

            else:
                self.result = f'Could not parse verification token and session parameters from response.'
                _LOGGER.error(self.result)

        except requests.exceptions.RequestException as e:
            self.result = f'Could not start session.\n{e}'
            _LOGGER.error(self.result)

        session.close()
