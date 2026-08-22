#!/bin/sh
[ "$1" = upgrade ] && exit 0
exec sh scripts/install.sh uninstallAll
