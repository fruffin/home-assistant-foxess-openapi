# FoxESS OpenAPI for Home Assistant

[![HACS](https://github.com/fruffin/home-assistant-foxess-openapi/actions/workflows/hacs.yml/badge.svg)](https://github.com/fruffin/home-assistant-foxess-openapi/actions/workflows/hacs.yml)
[![Hassfest](https://github.com/fruffin/home-assistant-foxess-openapi/actions/workflows/hassfest.yml/badge.svg)](https://github.com/fruffin/home-assistant-foxess-openapi/actions/workflows/hassfest.yml)

Custom Home Assistant integration for FoxESS solar and battery systems using the FoxESS Open API.

FoxESS OpenAPI is config-flow first, creates a proper Home Assistant device for the configured inverter serial number, and exposes sensors for inverter status, PV strings, phase metrics, battery state, power flows, temperatures, daily energy totals, and API response time.

## Features

- UI-based setup; no YAML configuration required.
- Home Assistant device metadata based on the configured FoxESS serial number.
- Configurable refresh intervals from the device details page.
- Force-refresh button for ad hoc API updates.
- Optional support for extended PV strings up to PV18.
- Optional second-battery sensors are only created when FoxESS reports values for them.

## Installation

### HACS custom repository

1. Open HACS.
2. Open the three-dot menu and choose **Custom repositories**.
3. Add this repository URL:

   ```text
   https://github.com/fruffin/home-assistant-foxess-openapi
   ```

4. Select **Integration** as the category.
5. Install **FoxESS OpenAPI** from HACS.
6. Restart Home Assistant.
7. Add the integration from **Settings > Devices & services > Add integration**.

### Manual install

Copy `custom_components/foxess_openapi` into your Home Assistant `custom_components` directory and restart Home Assistant.

## Configuration

Add the integration from **Settings > Devices & services > Add integration**, then provide:

- FoxESS Open API key
- Inverter/device serial number
- Optional display name
- Optional extended PV string support for PV7-PV18

Generate an API key in FoxESS Cloud under your user profile's API management area. The integration signs each Open API request with the token, timestamp, and signature headers required by FoxESS.

## Polling

FoxESS Open API access is rate limited, so the integration uses a shared coordinator and spaces API calls at least one second apart.

The default refresh cadence is:

- Realtime values: every 5 minutes
- Device metadata and monthly report totals: every 15 minutes
- Generation summary and battery SoC settings: every 60 minutes

These intervals are exposed as configuration number entities on the FoxESS device, so they can be changed from the device details page. The device also exposes a force-refresh button that immediately refreshes all FoxESS Open API datasets.

Normal refresh intervals can be reduced to 1 minute, but the defaults are more conservative to avoid burning through the FoxESS daily API allowance of 1440 calls per day.

## Branding

The integration ships with local FoxESS brand icon and logo under `custom_components/foxess_openapi/brand`.

Home Assistant versions before 2026.3 do not support local brand assets for custom integrations. Those versions may show a generic integration icon.

## Compatibility

This integration has been tested on Home Assistant 2026.5.

## Development

Run the local checks before publishing changes:

```bash
python3 -m ruff check custom_components/foxess_openapi
python3 -m ruff format --check custom_components/foxess_openapi
python3 -m compileall custom_components/foxess_openapi
```
