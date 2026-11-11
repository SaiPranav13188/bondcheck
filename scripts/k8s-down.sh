#!/usr/bin/env bash
# Delete the local kind cluster (and with it every BondCheck resource and the database volume).
set -euo pipefail
kind delete cluster --name bondcheck
