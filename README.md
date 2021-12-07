# Home Assistant Greenchoice Sensor
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)

This is a Home Assistant custom component (sensor) that connects to the Greenchoice API to retrieve current **usage data** and **price data**.

The sensor will check every 30 minutes if a new reading can be retrieved but Greenchoice practically only gives us one reading a day over this API. The reading is also delayed by 1 or 2 days (this seems to vary).

Price data for Energy and Gas is split into a daily base price, and a price per kWh or m³, thus giving four entities to determine your daily costs if you have an accurate usage meter.

### Install:

1. Search for 'greenchoice' in [HACS](https://hacs.xyz/). ***OR*** Place the 'greenchoice' folder in your 'custom_compontents' directory if it exists or create a new one under your config directory.

2. The Greenchoice API can theoretically have multiple contracts under one user account, so we need to figure out the `overeenkomst_id` for the contract. The integration can find all ids that are associated with your account and log them.
Setup the component by adding the following to `configuration.yaml`:

  ```YAML
  sensor:
    - platform: greenchoice
      name: meterstanden
      password: !secret greenchoicepass
      username: !secret greenchoiceuser
  ```

  > Read more about storing secrets at [Storing Secrets](https://www.home-assistant.io/docs/configuration/secrets/)

3. Start Home Assistant and go to `Configuration > Logs`. You should see an error containing the `overeenkomst_id` and the address that id is associated with. Choose the right id and add it to `configuration.yaml`:

  ```YAML
  sensor:
    - platform: greenchoice
      name: meterstanden
      password: !secret greenchoicepass
      username: !secret greenchoiceuser
      overeenkomst_id: !secret greenchoicecontract
  ```

### Usage:

#### Cost tracking:
1. To combine the daily base price with the total amount of energy used per day, first create a utility meter that tracks daily usage:

  ```YAML
  utility_meter:
    daily_energy_usage:
      source: sensor.total_energy_usage
      name: Daily Energy Usage
      cycle: daily
    daily_gas_usage:
      source: sensor.total_gas_usage
      name: Daily Gas Usage
      cycle: daily
  ```

2. Create a template that multiplies the daily usage by the price per kWh or m³, and add the daily base price:

  ```YAML
  template:
    sensor:
     - name: "Daily Energy Costs"
       state_class: total_increasing
       device_class: monetary
       unit_of_measurement: '€'
       state: >
          {{(float(states('sensor.daily_energy_usage'), 0) * float(states('sensor.energy_costs_per_kwh'), 0) + float(states('sensor.energy_costs_daily_base'), 0)) | round(2)}}

     - name: "Daily Gas Costs"
       state_class: total_increasing
       device_class: monetary
       unit_of_measurement: '€'
       state: >
          {{(float(states('sensor.daily_gas_usage'), 0) * float(states('sensor.gas_costs_per_m3'), 0) + float(states('sensor.gas_costs_daily_base'), 0)) | round(2)}}
  ```

#### Energy Usage:
1. Go to `Configuration > Energy` and click `Add Consumption`
2. For *Consumed Energy*, select `Total Energy Usage`
3. Select `Use an entity tracking the total costs` and then select `Daily Energy Costs`
4. Do the same for your Gas entities

After a few hours, you should see data appearing in the Energy Dashboard. Keep in mind that the data will be delayed since the Usage Data via the greenchoice API is not realtime.
