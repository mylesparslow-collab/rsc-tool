#!/bin/bash
cd "$(dirname "$0")" || exit 1
bash deploy/uninstall.sh
read -r -p "Press Return to close." _
