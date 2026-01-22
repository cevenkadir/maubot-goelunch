# Göttingen Lunch Menu Maubot Plugin (`goelunch`)

A [maubot](https://github.com/maubot/maubot) plugin for Element/Matrix that prints the Studentenwerk Göttingen canteen menus.

It fetches the cached menu HTML endpoint provided by Studierendenwerk Göttingen:

`https://www.studierendenwerk-goettingen.de/fileadmin/templates/php/mensaspeiseplan/cached/{lang}/{YYYY-MM-DD}/alle.html`

and parses canteen tables (`<table class="sp_tab">`) to extract menu items.

## Features

- `!lunch` → prints **today’s** menu for `default_canteen`
- `!lunch tomorrow` → prints **tomorrow’s** menu for `default_canteen`
- `!lunch YYYY-MM-DD` → prints that day for `default_canteen`
- `!lunch <canteen>` → prints **today** for that canteen
- `!lunch tomorrow <canteen>` / `!lunch YYYY-MM-DD <canteen>`
- Instance-specific configuration editable from the maubot Web UI

No third-party Python dependencies are required (uses maubot’s built-in HTTP client and a targeted HTML parser).

## Commands

### `!lunch [date] [canteen...]`

Examples:

- `!lunch`
- `!lunch tomorrow`
- `!lunch 2026-01-23`
- `!lunch Zentralmensa`
- `!lunch tomorrow Mensa am Turm`
- `!lunch 2026-01-23 CGiN`

**Date formats:**
- `today` (default)
- `tomorrow`
- `YYYY-MM-DD`

**Canteen matching:**
- Case-insensitive
- Exact match preferred
- If not exact, a unique substring match works (e.g. `turm` → `Mensa am Turm` if unambiguous)

## Configuration

The plugin uses maubot’s instance configuration system (`base-config.yaml` as defaults).  
Edit the config in the maubot Manager UI: **Instances → (your instance) → Config → Save**.

### `base-config.yaml`

```yaml
lang: "en" # "en" or "de"
default_canteen: "CGiN"
max_items: 30
request_timeout: 30
```

## Disclaimer: LLM-assisted code

Parts of this repository (including the initial versions of the scraper/parser and the maubot plugin code) were generated and/or refined with assistance from a Large Language Model (LLM), specifically OpenAI GPT-5.2.
