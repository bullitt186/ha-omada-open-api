# World Heatmap Card Devcontainer Wiring

This repository's devcontainer is configured to support joint development with
the sibling custom-card repository:

```text
/Users/bullitt/Documents/Repositories/ha-omada-open-api
/Users/bullitt/Documents/Repositories/ha-world-heatmap-card
```

Inside the devcontainer the card repository is mounted at:

```text
/workspaces/ha-world-heatmap-card
```

The Home Assistant container mounts the card build output from:

```text
../../ha-world-heatmap-card/dist
```

to:

```text
/config/www/ha-world-heatmap-card
```

Use this Home Assistant dashboard resource URL:

```text
/local/ha-world-heatmap-card/world-heatmap-card.js
```

with resource type:

```text
module
```

The card repository should build a single ES module at:

```text
dist/world-heatmap-card.js
```

If Home Assistant starts before the card has been built, the mounted directory
may be empty and the resource will 404 until the Vite build creates the file.
