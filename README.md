# postbox

SvelteKit app that displays PBUS postal points on a MapLibre map. Data is pulled
from the public CSV and committed into `static/postalpoints_latest.csv` by the
scheduled GitHub Action.

## Local dev

```sh
npm install
npm run dev
```

## Build

```sh
npm run build
```

## Data update

The `download_postalpoints.py` script writes a dated CSV file and copies each
snapshot to `static/snapshots/` while maintaining an index in
`static/snapshots/index.csv`.
