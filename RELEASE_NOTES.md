## What's New in v1.7.1

### Bug Fixes

- Cloud setup failing with `-7131 Controller ID not exist` now shows a clear, specific message instead of the generic "invalid authentication" error. This happens because free Omada Cloud/Central Essentials accounts don't support Open API at all — no Omada ID will ever resolve there, so re-checking credentials wasn't going to help. The "Select Controller Type" setup screen now also warns about this upfront, along with the fact that OC200 hardware controllers don't support Open API either.

### Improvements

- Reorganized the documentation: the README now focuses on what the integration does and how to set it up, while contributor/development info moved to a new `CONTRIBUTING.md` and the full troubleshooting runbook moved to a new `TROUBLESHOOTING.md`.
- Expanded the README's Features section with a table mapping each capability to the hardware it requires (gateway, PoE switch, access point, etc.), and documented the Omada Cloud/Central Essentials and OC200 Open API limitations.
