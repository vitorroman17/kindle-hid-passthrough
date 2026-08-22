#!/usr/bin/env python3
"""Regenerate the KPM manifests from __version__ in config.py.

    ./scripts/gen_kpm_manifests.py

kpm/manifest.json is build output. kpm/repo.json is committed, because KPM
fetches the repository index straight from raw.githubusercontent.com.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / 'kpm'

ID = 'kindle-hid-passthrough'
NAME = 'Kindle HID Passthrough'
AUTHOR = 'Lucas Zampieri'
DESCRIPTION = ('Userspace Bluetooth HID host. Pairs gamepads, keyboards and remotes and '
               'passes their input straight to Linux via UHID, with a touchscreen manager '
               'app and a KOReader plugin.')
REPO_DESCRIPTION = 'Releases of Kindle HID Passthrough, a userspace Bluetooth HID host for Kindle.'
PLATFORMS = ['kindlehf', 'kindlepw2']
ARTIFACT_URL = ('https://github.com/zampierilucas/kindle-hid-passthrough/releases/'
                'latest/download/kindle-hid-passthrough.kpkg')


def version():
    src = (ROOT / 'kindle_hid_passthrough/config.py').read_text()
    match = re.search(r'^__version__ = "(\d+)\.(\d+)\.(\d+)"$', src, re.M)
    if not match:
        raise SystemExit('could not read __version__ from kindle_hid_passthrough/config.py')
    return [int(part) for part in match.groups()]


def manifests():
    package = {
        'manifest_version': 2,
        'id': ID,
        'name': NAME,
        'author': AUTHOR,
        'description': DESCRIPTION,
        'version': version(),
        'dependencies': [],
        'supported_platforms': PLATFORMS,
    }
    repo = {
        'manifest_version': 1,
        'id': ID,
        'name': NAME,
        'description': REPO_DESCRIPTION,
        'packages': {
            ID: {
                'name': NAME,
                'author': AUTHOR,
                'description': DESCRIPTION,
                'artifacts': [{
                    'url': ARTIFACT_URL,
                    'version': package['version'],
                    'dependencies': [],
                    'supported_platforms': PLATFORMS,
                }],
            },
        },
    }
    return package, repo


def main():
    package, repo = manifests()
    for name, data in (('manifest.json', package), ('repo.json', repo)):
        (DEST / name).write_text(json.dumps(data, indent=2) + '\n')
        print(f'wrote {DEST / name}')


if __name__ == '__main__':
    main()
