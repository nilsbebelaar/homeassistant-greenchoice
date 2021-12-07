from datetime import datetime, timedelta
import logging
import operator
import json
import itertools
import requests
import urllib.parse
from bs4 import BeautifulSoup

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (CONF_NAME, STATE_UNKNOWN)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

import homeassistant.helpers.config_validation as cv

__version__ = '0.0.2'

_LOGGER = logging.getLogger(__name__)
_RESOURCE = 'mijn.greenchoice.nl'

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
    vol.Optional(CONF_OVEREENKOMST_ID, default=CONF_OVEREENKOMST_ID): cv.string,
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

    sensors = []
    sensors.append(GreenchoiceSensor(greenchoice_api, name, overeenkomst_id, username, password, "costEnergyKwh"))
    sensors.append(GreenchoiceSensor(greenchoice_api, name, overeenkomst_id, username, password, "costEnergyDailyBase"))
    sensors.append(GreenchoiceSensor(greenchoice_api, name, overeenkomst_id, username, password, "costGasM3"))
    sensors.append(GreenchoiceSensor(greenchoice_api, name, overeenkomst_id, username, password, "costGasDailyBase"))
    sensors.append(GreenchoiceSensor(greenchoice_api, name, overeenkomst_id, username, password, "usageEnergyTotal"))
    sensors.append(GreenchoiceSensor(greenchoice_api, name, overeenkomst_id, username, password, "usageGasTotal"))
    add_entities(sensors, True)


class GreenchoiceSensor(Entity):
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
    def state_class(self):
        return self._state_class

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
            _LOGGER.error("Need a overeenkomst id (see docs how to get one)!")

        if data is None or self._measurement_type not in data:
            self._state = STATE_UNKNOWN
        else:
            self._state = data[self._measurement_type]
            self._measurement_date = datetime.now()

        if self._measurement_type == "costEnergyKwh":
            self._icon = 'mdi:currency-eur'
            self._name = 'costEnergyKwh'
            self._device_class = 'monetary'
            self._unit_of_measurement = "€"
        if self._measurement_type == "costEnergyDailyBase":
            self._icon = 'mdi:currency-eur'
            self._name = 'costEnergyDailyBase'
            self._device_class = 'monetary'
            self._unit_of_measurement = "€"
        if self._measurement_type == "costGasM3":
            self._icon = 'mdi:currency-eur'
            self._name = 'costGasM³'
            self._device_class = 'monetary'
            self._unit_of_measurement = "€"
        if self._measurement_type == "costGasDailyBase":
            self._icon = 'mdi:currency-eur'
            self._name = 'costGasDailyBase'
            self._device_class = 'monetary'
            self._unit_of_measurement = "€"

        if self._measurement_type == "usageEnergyTotal":
            self._icon = 'mdi:lightning-bolt'
            self._name = 'usageEnergyTotal'
            self._device_class = 'energy'
            self._unit_of_measurement = "kWh"
            self._state_class = "total_increasing"
        if self._measurement_type == "usageGasTotal":
            self._icon = 'mdi:fire'
            self._name = 'usageGasTotal'
            self._device_class = 'gas'
            self._unit_of_measurement = "m³"
            self._state_class = "total_increasing"


class GreenchoiceApiData:
    def __init__(self, overeenkomst_id, username, password):
        self._overeenkomst_id = overeenkomst_id
        self._username = username
        self._password = password
        self.result = {}

    # @Throttle(MIN_TIME_BETWEEN_UPDATES)
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
                                    self.result["costEnergyKwh"] = returnData["stroom"]["leveringEnkelAllin"]
                                    self.result["costEnergyDailyBase"] = returnData["stroom"]["vastrechtPerDagIncBtw"] + returnData["stroom"]["netbeheerPerDagIncBtw"] - (returnData["stroom"]["rebTeruggaveIncBtw"] / returnData["stroom"]["daysInYear"])
                                    self.result["costGasM3"] = returnData["gas"]["leveringAllin"]
                                    self.result["costGasDailyBase"] = returnData["gas"]["vastrechtPerDagIncBtw"] + returnData["gas"]["netbeheerPerDagIncBtw"]

                                    _LOGGER.debug(f'costEnergyKwh: {self.result["costEnergyKwh"]}\ncostEnergyDailyBase: {self.result["costEnergyDailyBase"]}\ncostGasM3: {self.result["costGasM3"]}\ncostGasDailyBase: {self.result["costGasDailyBase"]}')

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
                                    self.result["usageEnergyTotal"] = returnData["series"][0]["values"][datetime.now().strftime("%Y")]

                                    _LOGGER.debug(f'usageEnergyTotal: {self.result["usageEnergyTotal"]}')

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
                                    self.result["usageGasTotal"] = returnData["series"][0]["values"][datetime.now().strftime("%Y")]

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
