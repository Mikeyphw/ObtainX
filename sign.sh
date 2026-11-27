#!/usr/bin/env bash
# Legacy arbitrary-directory signing is retired; R12 uses isolated protected-main signing.
set -euo pipefail
printf '%s\n' 'R12: direct legacy signing is disabled. Use the reviewed protected release-candidate workflow documented in docs/R12_RELEASE_QUALIFICATION.md.' >&2
exit 2
