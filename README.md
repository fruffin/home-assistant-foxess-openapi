# FoxESS OpenAPI for Home Assistant

Custom Home Assistant integration for FoxESS solar and battery systems using the FoxESS Open API.

This integration is intentionally config-flow first: add it from **Settings > Devices & services > Add integration**, then provide:

- FoxESS Open API key
- Inverter/device serial number
- Optional display name
- Optional extended PV string support for PV7-PV18

The configured inverter is represented as a Home Assistant device identified by its serial number. Sensors are grouped under that device and cover inverter status, PV strings, phase metrics, battery state, power flows, energy totals, temperatures, and API response time.

## API Key

Generate an API key in FoxESS Cloud under your user profile's API management area. The integration signs each Open API request with the token/timestamp/signature headers required by FoxESS.

## Polling

FoxESS Open API access is rate limited, so the integration uses a shared coordinator and spaces API calls at least one second apart.

The default refresh cadence is:

- Realtime values: every 5 minutes
- Device metadata and monthly report totals: every 15 minutes
- Generation summary and battery SoC settings: every 60 minutes

These intervals are exposed as configuration number entities on the FoxESS device,
so they can be changed from the device details page. The device also exposes a
force-refresh button that immediately refreshes all FoxESS Open API datasets.
Normal refresh intervals are limited to 5 minutes or more to avoid burning
through the FoxESS daily API allowance.

## Installation

Copy `custom_components/foxess_openapi` into your Home Assistant `custom_components` directory and restart Home Assistant.
