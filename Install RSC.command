#!/bin/bash
# Double-click me. Sets up the RSC tool on this Mac and opens it. No questions.
cd "$(dirname "$0")" || exit 1
chmod +x deploy/install.sh
if ./deploy/install.sh --yes; then
  echo; echo "All set. You can close this window."
else
  echo; echo "Something stopped the install. Take a picture of this window and send it to Myles."
  read -r -p "Press Return to close." _
fi
