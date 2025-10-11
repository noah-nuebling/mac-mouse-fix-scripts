
"""
- About
    - This embeds the script inside a notarized .app bundle.
    - This is necessary to be able to share the script, since a simple .command file is quarantined after downloading.
    - Also see: 
        - https://scriptingosx.com/2022/04/launching-scripts-2-launching-scripts-from-finder/) 

- Note: Could simplify folder structure inside the .app bundle.
    - We could simply store the script at .app/script instead of ./app/Contents/MacOS/script, but then the stapling of the notarization info doesn't work, which makes it so the user needs internet when opening the script for the first time I think. (Which is not too bad.)

- Example usage: See how we compress localization_compression_script.py [Oct 2025]    
    
"""

from mfutils import runclt
import argparse
from typing import Any
from pathlib import Path
import plistlib
import tempfile
import os

# Define fail macro
def fail(reason):           print(f"\nError: {reason}"); exit(1)
def hfail(parser, reason):      parser.print_help(); fail(reason)

# Parse args
args: Any = None
if 1:
    parser = argparse.ArgumentParser(description='Embed a script in a signed and notarized .app bundle – This allows scripts to be distributed without being blocked by GateKeeper. (However, they will still be translocated while quarantined.)')
    parser.add_argument('script_path',    help='Path to the script to embed')
    parser.add_argument('--app-path',     required=True, help='Path for the .app bundle to create')
    parser.add_argument('--bundle-id',    required=True, help='CFBundleIdentifier for the app bundle')
    parser.add_argument('--app-password', default=os.environ.get('APP_PASSWORD'), help="Password for the notary service. Has to be an 'App-specific password' created on Apple.com. Can also be specified using env variable APP_PASSWORD || [Oct 2025]")
    parser.add_argument('--version',      default='1.0', help='App version (default: 1.0)')
    parser.add_argument('--build-number', default='1', help='Build number version (default: 1)')
    parser.add_argument('--skip-notarization', action='store_true', help='Skip signing and notarization (for testing)')
    args = parser.parse_args()

    # Validate args
    if not args.app_password and not args.skip_notarization: hfail(parser, "Missing argument: --app-password (or use --skip-notarization for testing)\n")

# Validate script
if 1:
    script_path = Path(args.script_path)

    if not script_path.exists():                    fail(f"Script not found: {args.script_path}")
    if Path(script_path).read_bytes()[:2] != b'#!': fail(f"Script must start with shebang (#!): {args.script_path}")
    if not os.access(script_path, os.X_OK):         fail(f"Script is not executable: {args.script_path}. Run: chmod +x {args.script_path}")

# Create new app bundle containing the script
if 1:
    runclt(f'rm -rf "{args.app_path}"')
    runclt(f'mkdir -p "{args.app_path}/Contents/MacOS"')
    runclt(f'cp "{args.script_path}" "{args.app_path}/Contents/MacOS/{Path(args.app_path).stem}"') # Insert the script as the executable
    Path(f'{args.app_path}/Contents/Info.plist').write_bytes(plistlib.dumps({ # Add dummy Info.plist file. If you leave it empty, notarization still succeeds, but then Gatekeeper rejects it when it's quarantined. [Oct 2025]
        'CFBundleName':                 Path(args.app_path).stem,
        'CFBundleExecutable':           Path(args.app_path).stem,
        'CFBundleIdentifier':           args.bundle_id,
        'CFBundleShortVersionString':   args.version,
        'CFBundleVersion':              args.build_number,
        'CFBundlePackageType':          'APPL',
    }))

    print(f'Embedded script inside app bundle at: {args.app_path}')

# Skip notarization
if args.skip_notarization:
    print(f'Skipped signing and notarization. App bundle created at "{args.app_path}"')
    exit(0)

# Sign, notarize, and staple the app bundle
if 1:

    print(f'Notarizing and stapling .app bundle at "{args.app_path}"...')

    runclt(f'codesign --force --deep --sign "Developer ID Application: Noah Nuebling (LM5Z78756B)" "{args.app_path}"', fail_on_stderr=False)

    zip_path = tempfile.NamedTemporaryFile(suffix=".zip", delete=False).name

    try:
        runclt(f'ditto -c -k --keepParent "{args.app_path}" "{zip_path}"')
        runclt(f'xcrun notarytool submit "{zip_path}" --apple-id noah.n.developer@gmail.com --team-id LM5Z78756B --password {args.app_password} --wait')
        runclt(f'xcrun stapler staple "{args.app_path}"')

        print(f'Notarized and stapled .app bundle at "{args.app_path}"')
    finally:
        # Clean up temp zip file
        runclt(f'rm -f "{zip_path}"')
