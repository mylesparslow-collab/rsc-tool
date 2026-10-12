#!/bin/bash
# Double-click to open the RSC app. Put this on Nick's Desktop.
cd "$HOME/rsc-tool" || exit 1
exec ./.venv/bin/rsc serve
