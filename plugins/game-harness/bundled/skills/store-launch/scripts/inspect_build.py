#!/usr/bin/env python3
"""Show what a built app actually contains, so store disclosures rest on evidence.

Usage: python inspect_build.py <app.ipa | app.aab | app.apk> [--hosts]

IPA: display name, bundle ID, version, device families, usage-description keys,
     tracking prompt, export-compliance key, ad app ID, privacy manifests and,
     with --hosts, server host names found in the binaries.
AAB/APK: package, permissions (including the advertising ID permission) and
     billing/ads markers found in the manifest and dex files.

Only reads the archive; nothing is extracted or modified.
"""
import plistlib
import re
import sys
import zipfile

# Windows consoles default to a legacy code page; force UTF-8 so Korean text and status marks print.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

HOST = re.compile(rb'(?<![A-Za-z0-9.\-])([a-z0-9][a-z0-9\-]{0,40}(?:\.[a-z0-9][a-z0-9\-]{0,40}){1,5}\.(?:com|net|org|io|dev|app))(?![A-Za-z0-9\-])')
NOISE = ('apple.com', 'w3.org', 'example.com', 'mozilla.org', 'github.com', 'xml.org', 'unicode.org', 'ietf.org')


def hosts_in(data):
    found = set()
    for match in HOST.finditer(data):
        host = match.group(1).decode('ascii', 'replace')
        if '.' in host and not host.endswith(NOISE) and not host[0].isdigit():
            found.add(host)
    return found


def inspect_ipa(archive, want_hosts):
    names = archive.namelist()
    info_name = next((n for n in names if re.fullmatch(r'Payload/[^/]+\.app/Info\.plist', n)), None)
    if not info_name:
        print('No Payload/*.app/Info.plist found; is this an IPA?')
        return
    info = plistlib.loads(archive.read(info_name))
    families = {1: 'iPhone', 2: 'iPad'}
    print('== Info.plist')
    for key in ('CFBundleDisplayName', 'CFBundleIdentifier', 'CFBundleShortVersionString', 'CFBundleVersion', 'MinimumOSVersion'):
        print(f'{key}: {info.get(key, "<absent>")}')
    print('Device families:', ', '.join(families.get(f, str(f)) for f in info.get('UIDeviceFamily', [])) or '<absent>')
    print('Languages listed:', info.get('CFBundleLocalizations', '<absent>'), '/ development region:', info.get('CFBundleDevelopmentRegion', '<absent>'))
    print('Export compliance key (ITSAppUsesNonExemptEncryption):', info.get('ITSAppUsesNonExemptEncryption', '<absent: App Store Connect will ask per build>'))
    print('Tracking prompt text (NSUserTrackingUsageDescription):', info.get('NSUserTrackingUsageDescription', '<absent: the app cannot ask for tracking>'))
    usage = sorted(k for k in info if k.endswith('UsageDescription'))
    print('Permission prompts declared:', usage or 'none')
    print('AdMob app ID (GADApplicationIdentifier):', info.get('GADApplicationIdentifier', '<absent>'))
    print('SKAdNetwork entries:', len(info.get('SKAdNetworkItems', [])))
    for key in sorted(k for k in info if k.startswith(('GOOGLE_ANALYTICS_', 'FIREBASE_', 'Firebase'))):
        print(f'{key}: {info[key]}')

    print('\n== Privacy manifests')
    manifests = [n for n in names if n.endswith('PrivacyInfo.xcprivacy')]
    if not manifests:
        print('none found')
    for name in manifests:
        try:
            data = plistlib.loads(archive.read(name))
        except Exception as error:  # a malformed manifest is itself worth knowing
            print(f'{name}: unreadable ({error})')
            continue
        types = [t.get('NSPrivacyCollectedDataType', '').replace('NSPrivacyCollectedDataType', '') for t in data.get('NSPrivacyCollectedDataTypes', [])]
        print(f'{name.split(".app/")[-1]}\n  tracking={data.get("NSPrivacyTracking")} tracking_domains={len(data.get("NSPrivacyTrackingDomains", []))} collected={types or "none declared"}')
    print('Note: an SDK can send data that its manifest does not declare. Read the package code as well.')

    if want_hosts:
        print('\n== Host names found in binaries and metadata')
        found = {}
        for name in names:
            if name.endswith('/') or archive.getinfo(name).file_size < 256:
                continue
            base = name.rsplit('/', 1)[-1]
            if '.' in base and not base.endswith(('.dat', '.plist', '.json', '.dylib')):
                continue
            for host in hosts_in(archive.read(name)):
                found.setdefault(host, name.split('.app/')[-1])
        for host in sorted(found):
            print(f'{host}  <- {found[host][:70]}')
        print('A host name in the binary shows the code exists, not that it runs. Use it as a list of things to explain.')


def inspect_android(archive):
    names = archive.namelist()
    manifests = [n for n in names if n.endswith('AndroidManifest.xml')]
    blob = b''.join(archive.read(n) for n in manifests)
    text = blob + blob.replace(b'\x00', b'')  # binary XML stores UTF-16; keep both views
    print('== Manifest files:', manifests or 'none found')
    packages = sorted(set(m.decode() for m in re.findall(rb'[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,4}', text) if m.startswith(b'com.') and b'google' not in m and b'android' not in m))[:5]
    print('Package-like names (first few):', packages)
    permissions = sorted(set(m.decode() for m in re.findall(rb'(?:android\.permission|com\.google\.android\.gms\.permission|com\.android\.vending)\.[A-Z_]+', text)))
    print('\n== Permissions')
    for permission in permissions:
        print(permission)
    ad_id = any(p.endswith('.AD_ID') for p in permissions)
    print('\nAdvertising ID permission:', 'PRESENT. An app aimed at children must not transmit the advertising ID.' if ad_id else 'not found')
    print('Billing permission:', 'present' if any(p.endswith('.BILLING') for p in permissions) else 'not found')
    dex = [n for n in names if n.endswith('.dex')]
    markers = {'Google Play Billing': b'com/android/billingclient', 'Google Mobile Ads': b'com/google/android/gms/ads', 'Firebase Analytics': b'com/google/firebase/analytics', 'User Messaging Platform': b'com/google/android/ump'}
    print('\n== SDK markers in dex files')
    data = b''.join(archive.read(n) for n in dex)
    for label, marker in markers.items():
        print(f'{label}:', 'found' if marker in data else 'not found')
    print('Note: version name and code are easiest to read with bundletool or aapt2; this script does not decode them.')


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    with zipfile.ZipFile(path) as archive:
        if any(n.startswith('Payload/') for n in archive.namelist()):
            inspect_ipa(archive, '--hosts' in sys.argv)
        else:
            inspect_android(archive)
    return 0


if __name__ == '__main__':
    sys.exit(main())
