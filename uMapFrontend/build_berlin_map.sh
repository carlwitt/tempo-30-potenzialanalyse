#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

exec "${PYTHON:-python3}" "$SCRIPT_DIR/build_umap_configuration.py" \
    --backup "$SCRIPT_DIR/umap_backup_tempo-30-potenziale-berlin.umap" \
    --output "$SCRIPT_DIR/tempo-30-potenziale-berlin.umap" \
    --remote-base "https://tempo-30.adfc-berlin.de/uMap" \
    --area-name "Berlin" \
    --map-name "Tempo 30 Potenziale Berlin" \
    --accident-start-year 2022 \
    --accident-end-year 2025 \
    "$@"
