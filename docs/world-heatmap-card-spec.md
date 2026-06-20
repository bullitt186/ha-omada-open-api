# Reusable World Heatmap Custom Card Specification

## Summary

Build a reusable Home Assistant custom card that renders geographic activity as
a static world map with a canvas heatmap overlay. The card must be independent
from `ha-omada-open-api` and usable with any Home Assistant entity that exposes
compatible heatmap point data.

The visual and behavior reference is the local POC in
`poc/threat-heatmap/index.html`. The production card should reuse the proven
ideas from the POC, but normal dashboard view must show only the map and heatmap,
not the tuning controls or right-side data list.

## Data Contract

The card reads one Home Assistant entity. By default it expects heatmap data in
entity attributes, not in the entity state.

Required attribute shape:

```json
{
  "points": [
    {
      "lat": 35.0,
      "lon": 105.0,
      "value": 23,
      "country": "CN"
    }
  ],
  "max": 435,
  "window_start": 1779397184,
  "window_end": 1781989184,
  "total_rows": 667
}
```

Required point fields:

- `lat`: latitude in decimal degrees.
- `lon`: longitude in decimal degrees.
- `value`: raw numeric intensity for that coordinate.

Optional point fields:

- `country`
- `label`
- `sample_ips`
- `top_signatures`
- `top_activities`
- `severities`
- `latest_time`

The card must ignore points with missing or invalid `lat`, `lon`, or `value`.
It must not render invalid points at `(0, 0)`.

## Card Configuration

The normal card config must support every visible tuning option from the POC as
YAML/UI-editor configuration.

Example:

```yaml
type: custom:world-heatmap-card
entity: sensor.omada_threat_heatmap_daily
title: Threat Map
map_style: dark
crop: threats_xy
scale: log
radius: 24
blur: 14
opacity: 0.16
floor: 0.32
height: 360
```

Required config:

- `entity`: entity ID containing heatmap attributes.

Optional config:

- `title`: optional card title. Default: no visible title in normal view.
- `points_attribute`: default `points`.
- `max_attribute`: default `max`.
- `window_start_attribute`: default `window_start`.
- `window_end_attribute`: default `window_end`.
- `map_style`: `dark`, `muted`, `contrast`, `light`, or `grid`. Default `dark`.
- `crop`: `threats_xy`, `threats_lat`, `world`, `no_antarctica`, or
  `temperate`. Default `threats_xy`.
- `scale`: `log`, `sqrt`, or `linear`. Default `log`.
- `radius`: simpleheat point radius in CSS pixels. Default `24`.
- `blur`: simpleheat blur radius in CSS pixels. Default `14`.
- `opacity`: simpleheat minimum opacity as a `0.0` to `0.4` float. Default
  `0.16`.
- `floor`: minimum normalized intensity for visible non-zero points as a `0.0`
  to `0.6` float. Default `0.32`.
- `height`: CSS height in pixels or CSS length. Default should fit HA sections
  views cleanly, around `320px` to `380px`.
- `show_title`: boolean. Default `false`.
- `show_bounds`: boolean for debugging only. Default `false`.
- `map_image_url`: optional equirectangular world map image override.

All config options above should be available in the visual card editor as form
controls. In normal dashboard rendering, the card must not show those controls.

## Frontend Technology

Use these technologies for the external custom card implementation:

- **TypeScript** for all source code.
- **Lit** for the Home Assistant Web Component and card editor.
- **Vite** for local development, bundling, and library builds.
- **simpleheat** as the heatmap rendering primitive.
- **Canvas 2D** for the heatmap overlay.
- **Shadow DOM** for style isolation.
- **ES module output** for Home Assistant dashboard resources and HACS.

Avoid framework dependencies beyond Lit. Do not use React, Vue, Svelte, D3, or
Leaflet for v1. The goal is a small reusable custom card with predictable HA
dashboard behavior, not a full map application.

Recommended project structure:

```text
src/
  world-heatmap-card.ts
  world-heatmap-card-editor.ts
  heatmap-renderer.ts
  projection.ts
  types.ts
  defaults.ts
  styles.ts
```

Implementation guidance:

- Keep Home Assistant card lifecycle code in `world-heatmap-card.ts`.
- Keep Canvas/simpleheat drawing code in `heatmap-renderer.ts`.
- Keep crop/projection math in `projection.ts` and unit-test it separately.
- Keep config defaults and validation in `defaults.ts`.
- Bundle `simpleheat` into the card output instead of relying on a CDN.
- Register the card with `customElements.define("world-heatmap-card", ...)`.
- Register `window.customCards` metadata so the card appears in the HA custom
  card picker.
- Provide `getConfigElement()` and a Lit-based editor component for visual
  configuration.

Build output should produce a single distributable JavaScript module, for
example:

```text
dist/world-heatmap-card.js
```

Home Assistant resource usage:

```yaml
url: /local/world-heatmap-card.js
type: module
```

## Rendering Behavior

- Use a static equirectangular/Plate-Carree world map as the background.
- Use `simpleheat` or an equivalent canvas implementation for the overlay.
- Project coordinates with the active crop bounds:

```js
x = ((lon - west) / (east - west)) * width
y = ((north - lat) / (north - south)) * height
```

- Use raw `value` for display/metadata, but transform heat intensity according
  to `scale`:
  - `linear`: `value`
  - `sqrt`: `Math.sqrt(value)`
  - `log`: `Math.log1p(value)`
- Apply `floor` after normalization so low-volume countries remain visible:

```js
normalized = scaledValue / maxScaledValue
boosted = floor + normalized * (1 - floor)
heatValue = boosted * maxScaledValue
```

- Recompute canvas size and redraw when:
  - entity attributes change,
  - card config changes,
  - element size changes,
  - device pixel ratio affects canvas dimensions.

## Crop Modes

Crop modes must affect both the coordinate projection and the map background.
The map layer must be clipped with `overflow: hidden`, matching the POC fix.

- `world`: full `north=90`, `south=-90`, `west=-180`, `east=180`.
- `no_antarctica`: `north=85`, `south=-60`, full longitude.
- `temperate`: `north=70`, `south=-55`, full longitude.
- `threats_lat`: latitude bounds from current points plus padding, full
  longitude.
- `threats_xy`: latitude and longitude bounds from current points plus padding.

Recommended default padding:

- latitude padding: `7` degrees.
- longitude padding: `12` degrees.

Clamp automatic latitude bounds to `north <= 85` and `south >= -60`. Clamp
longitude to `-180..180`.

## UI Requirements

Normal dashboard view:

- Show only the map/heatmap surface.
- Do not show the POC control bar.
- Do not show the right-hand point list.
- Show a small loading or error state only when data is missing or invalid.

Card editor:

- Expose all config options listed above.
- Use dropdowns for enum options.
- Use sliders or numeric inputs for radius, blur, opacity, floor, and height.
- Validate that `entity` is set.
- Optionally suggest this card for entities whose attributes include a `points`
  array with `lat`, `lon`, and `value`.

## Acceptance Criteria

- The card can render the JSON generated by `poc/threat-heatmap/export_threat_heatmap.py`.
- With the current POC data, `CN` at `lat=35`, `lon=105`, value `23` is visible
  while `US` value `435` remains stronger but not the only visible hotspot.
- `crop: threats_xy` removes irrelevant polar regions and clips the map
  correctly.
- Switching to `crop: world` shows the full world map with points still aligned.
- The card remains visually useful in `dark`, `muted`, `contrast`, `light`, and
  `grid` map styles.
- The card works in Home Assistant sections and panel views without layout
  overflow.

## Out of Scope for v1

- Fetching Omada data directly.
- Home Assistant backend services.
- Live animation.
- Tooltips, click drilldowns, and side panels.
- Non-equirectangular projections.
