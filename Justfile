# clash-rules — single source of truth for Clash/mihomo + Shadowrocket rule-sets.
# `just` wraps the build/validate steps. https://just.systems/

# List available recipes
default:
    @just --list

# Validate + build all rules/*.list into dist/ (clash + shadowrocket formats)
build:
    python3 scripts/build.py

# Validate only (build also validates; this fails fast without writing dist/)
check:
    python3 scripts/build.py >/dev/null

# Re-run the one-shot migration from the DockerCompose-V2Ray legacy config
migrate legacy="":
    python3 scripts/migrate_from_legacy.py {{legacy}}

# Show rule counts per category
stats:
    @for f in rules/*.list; do printf '%s\t%s\n' "$(basename $f)" "$(grep -cvE '^\s*(#|$)' $f)"; done

# Remove build output
clean:
    rm -rf dist
