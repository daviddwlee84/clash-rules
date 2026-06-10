# clash-rules — single source of truth for Clash/mihomo + Shadowrocket rule-sets.
# `just` wraps the build/validate steps. https://just.systems/

# List available recipes
default:
    @just --list

# Validate + build all rules/*.list into dist/ (clash + shadowrocket formats)
build:
    uv run scripts/build.py

# Validate only (build also validates; this fails fast without writing dist/)
check:
    uv run scripts/build.py >/dev/null

# Show rule counts per category
stats:
    @for f in rules/*.list; do printf '%s\t%s\n' "$(basename $f)" "$(grep -cvE '^\s*(#|$)' $f)"; done

# Remove build output
clean:
    rm -rf dist
