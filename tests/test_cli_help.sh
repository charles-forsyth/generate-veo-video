#!/bin/bash
set -e

# Run the script directly with --help to verify syntax and argparse
echo "Running smoke test: generate_veo3_video.py --help"
python3 generate_veo3_video.py --help > /dev/null

echo "Smoke test passed!"
