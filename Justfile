# clash-rules: offline data/policy build and private review workflow.
set positional-arguments

default:
    @just --list

build:
    python3 scripts/build.py

check:
    python3 scripts/build.py --check

test:
    python3 -m unittest discover -s tests -v

native-check *args:
    python3 scripts/native_check.py "$@"

sync-upstreams *args:
    python3 scripts/sync_upstreams.py "$@"

compose-profile *args:
    python3 scripts/compose_profile.py "$@"

propose-rule *args:
    python3 scripts/propose_rule.py "$@"

publish-preview:
    python3 scripts/publish.py
