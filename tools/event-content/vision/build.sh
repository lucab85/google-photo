#!/usr/bin/env bash
# Build the Apple Vision analyser. macOS only (needs the Xcode command line tools).
set -euo pipefail
cd "$(dirname "$0")"
swiftc -O -o vanalyze main.swift
echo "built $(pwd)/vanalyze"
