#!/usr/bin/env python3

#
# Script for importing .xcloc files into the Xcode project. 
#   
#   As of [Dec 2025], this 
#       - simply calls `xcodebuild -importLocalizations` 
#       - Prints the WARNINGS from `xcodebuild` (such as mismatched source-string) in an easy-to-audit way.
#

import mfutils
import re
from difflib import SequenceMatcher
import subprocess
import shlex
import argparse
import os

import io

# ANSI colors
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RESET = '\033[0m'
BOLD = '\033[1m'

def highlight_diff(old: str, new: str) -> tuple[str, str]:
    """Return old and new with differences highlighted."""
    matcher = SequenceMatcher(None, old, new)
    old_parts, new_parts = [], []
    
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == 'equal':
            old_parts.append(old[i1:i2])
            new_parts.append(new[j1:j2])
        elif op == 'delete':
            old_parts.append(f"{RED}{old[i1:i2]}{RESET}")
        elif op == 'insert':
            new_parts.append(f"{GREEN}{new[j1:j2]}{RESET}")
        elif op == 'replace':
            old_parts.append(f"{RED}{old[i1:i2]}{RESET}")
            new_parts.append(f"{GREEN}{new[j1:j2]}{RESET}")
    
    return ''.join(old_parts), ''.join(new_parts)

def split_warnings(text: str) -> list[str]:
    """Split text into individual warning blocks."""
    parts = re.split(r'(?=--- xcodebuild: WARNING:)', text)
    return [p.strip() for p in parts if p.strip() and p.startswith('--- xcodebuild: WARNING:')]

def parse_does_not_match(warning: str) -> tuple | None:
    match = re.match(
        r'''(?x)
            ---\ xcodebuild:\ WARNING:\ (.*?):
            \ Source\ string\ in\ the\ XLIFF\ "(.*?)"
            \ does\ not\ match\ source\ string\ in\ the\ project\ "(.*?)"
            \ \(Key:\ \"(.*?)\"\)
        ''',
        warning,
        re.DOTALL
    )
    return match.groups() if match else None

def parse_generic(warning: str) -> tuple | None:
    match = re.match(
        r'''(?x)
            ---\ xcodebuild:\ WARNING:\ (.*?):
            \ (.*?)\ 
            \(Key:\ \"(.*?)\"\)
        ''',
        warning
    )
    return match.groups() if match else None

def main(): 


    # Parse args
    parser = argparse.ArgumentParser()
    parser.add_argument('--xcloc-path', required=True, help="Path to the xcloc file you'd like to import.")
    args = parser.parse_args()

    _stderr = ""
    if 1:
        cmd = f"xcodebuild -importLocalizations -localizationPath '{args.xcloc_path}'" # TODO: Consider setting the build-directory to a temp dir like in `uploadstrings.py`. I think that prevents nuking the build-cache. [Dec 2025]
        
        print(f"\n--------------------------------------------------------")
        print(f"\nimportstrings.py: Running: {cmd}")
        
        proc = subprocess.Popen(shlex.split(cmd), stderr=subprocess.PIPE)
        proc.wait()
        _stderr = proc.stderr.read().decode('utf-8')
    
    print(f"\n--------------------------------------------------------")
    print(f"\nimportstrings.py: Raw stderr of 'xcodebuild -importLocalizations':\n\n{_stderr}")

    print(f"\n--------------------------------------------------------")
    print(f"\nimportstrings.py: Parsed WARNINGS of 'xcodebuild -importLocalizations':\n\n")

    warnings = split_warnings(_stderr)
    
    does_not_match_warning_count = 0
    generic_warning_count = 0
    
    parsed_warnings: list[str] = []

    for warning in warnings:
        
        parsed_warning = ""

        parsed = None

        if not parsed:
            parsed = parse_does_not_match(warning)
            if parsed:
                does_not_match_warning_count += 1
                file, xliff_str, project_str, key = parsed

                parsed_warning += f"{BOLD}Problem:{RESET}   (MF) Source strings do not match" + "\n"
                parsed_warning += f"{BOLD}Key:{RESET}       {key}" + "\n"
                parsed_warning += f"{BOLD}File:{RESET}      {file}" + "\n"

                old_highlighted, new_highlighted = highlight_diff(xliff_str, project_str)
                parsed_warning += f"{BOLD}XLIFF:{RESET}\n{old_highlighted}" + "\n"
                parsed_warning += f"{BOLD}Project:{RESET}\n{new_highlighted}" + "\n"
        
        if not parsed:
            parsed = parse_generic(warning)
            if parsed:
                generic_warning_count += 1
                file, msg, key = parsed

                parsed_warning += f"{BOLD}Problem:{RESET}   {msg}" + "\n"
                parsed_warning += f"{BOLD}Key:{RESET}       {key}" + "\n"
                parsed_warning += f"{BOLD}File:{RESET}      {file}" + "\n"
        
        if not parsed:
            assert False, f"Unexpected warning format: {warning}"
        
        parsed_warnings.append(parsed_warning)

        

    # Print parsed_warnings
    parsed_warnings.sort() # Sort by problem-type (Works because the "Problem:" is always first [Dec 2025])
    for i in range(len(parsed_warnings)):
        parsed_warnings[i] = "-" * 60 + f"\n(Problem {i})\n" + parsed_warnings[i]
    print("".join(parsed_warnings))

    # Print summary
    print(f"\n{BOLD}Summary:{RESET} {does_not_match_warning_count} 'does not match' warnings, {generic_warning_count} other warnings")

if __name__ == "__main__":
    main()