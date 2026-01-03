#
# Reimplementation of importstrings.py that doesn't depend on `xcodebuild -importLocalizations`:
#  
#   Discussion: 
#       Currently doesn't actually do imports [Dec 2025]
#       Instead, it just lists mismatches between the .xcstrings files and the .xcloc file.
#       Benefits over the mismatch-detection by xcodebuild -importLocalizations:
#           - This runs faster
#           - This also finds mismatches in the COMMENT in addition to the SOURCE.
#       
#   Keep in mind: [Dec 2025]
#       The mismatches that this detects are NOT imported by xcodebuild -importLocalizations. (So you may have to import the manually.)




import argparse
import glob
from re import split, sub
import xml.etree.ElementTree as ET
import mfutils
from pathlib import Path
from dataclasses import dataclass
import json

import textwrap

from difflib import SequenceMatcher


# 
# Color-printing helpers (copied from importstrings.py)
#

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

#
# mfxml helpers
#

def mfxml_tag(el):
    assert el.tag.startswith('{urn:oasis:names:tc:xliff:document:1.2}')
    return el.tag[len('{urn:oasis:names:tc:xliff:document:1.2}'):None]

def mfxml_findtext(el, tag):
    return el.findtext('{urn:oasis:names:tc:xliff:document:1.2}' + tag)

def mfxml_findattrib(el: ET.Element, tag):
    found = el.find('{urn:oasis:names:tc:xliff:document:1.2}' + tag)
    if found is None: return {}
    return found.attrib

def mfxml_print(el):
    for child in el:
        chchs = [chch for chch in child]
        print(f"tag: {mfxml_tag(child)}, children: {len(chchs)}, attrib: {child.attrib}, text: {child.text}")

#
# mfdict helpers
#

def mfdict_getkp(dict, keypath: str):

    _applied_kp = ''
    
    result = dict
    for key in keypath.split('.'):
        if not key in result: assert False, f"Keypath component '{key}' (of keypath: '{keypath}', already applied: '{_applied_kp}') not found in {json.dumps(result, indent=4)}"
        result = result[key]
        _applied_kp += f'.{key}' if len(_applied_kp) else key
    return result

#
# Main program
#

if 1:

    # Parse args
    parser = argparse.ArgumentParser()
    parser.add_argument("--xcloc-path", required=True, help="Path to the xcloc file")
    parser.add_argument("--no-source-mismatches", action='store_true', help="Don't list mismatches in the source (English) strings.")
    parser.add_argument("--no-comment-mismatches", action='store_true', help="Don't list mismatches in the string comments.")
    parser.add_argument("--no-key-mismatches",     action='store_true', help="Don't list mismatches in the string keys.")
    args = parser.parse_args()

    # Load xliff file
    xliff_paths = glob.glob(f"{glob.escape(args.xcloc_path)}/**/*.xliff", recursive=True)
    assert len(xliff_paths) == 1, f"Found unexpected number of xliff paths found in '{args.xcloc_path}'. xliff paths: {xliff_paths}"
    xliff_path = xliff_paths[0];
    xliff_obj = ET.fromstring(Path(xliff_path).read_text())

    # Load xcstrings files
    xcstrings_objs = { xcstrings_path: mfutils.read_xcstrings_file(xcstrings_path) for xcstrings_path in glob.glob("**/*.xcstrings", recursive=True)}
        
    # DEBUG
    print("XLIFF:", xliff_paths)
    print("XCSTRINGS:", xcstrings_objs.keys())

    print("-------")

    # Load all trans_units from the xliff file

    @dataclass
    class TransUnit:
        key:    str | None
        source: str | None
        target: str | None
        note:   str | None
        state:  str | None
        file:   str | None

    trans_units: list[TransUnit] = []

    for file in xliff_obj:
        file_path = file.attrib['original']
        for ch in file:
            assert mfxml_tag(ch) in ['header', 'body']
            if mfxml_tag(ch) == 'body':
                for trans_unit in ch:
                    assert mfxml_tag(trans_unit) == 'trans-unit'
                    trans_units.append(TransUnit(
                        key=trans_unit.attrib['id'],
                        source=mfxml_findtext(trans_unit, 'source'),
                        target=mfxml_findtext(trans_unit, 'target'),
                        note=mfxml_findtext(trans_unit, 'note'),
                        state=('mf-dont-translate' if (trans_unit.attrib.get('translate', '') == 'no') else mfxml_findattrib(trans_unit, 'target').get('state', None)),
                        file=file_path
                    ))

    # Iterate all the trans units

    mismatch_warnings = []
    for trans_unit in trans_units:
        
        if trans_unit.state == 'mf-dont-translate': 
            continue;

        sub_keypath = None
        key_to_search_for = None
        if (splitidx := trans_unit.key.find('|==|')) != -1:
            key_to_search_for = trans_unit.key[None : splitidx]
            sub_keypath       = trans_unit.key[splitidx + len('|==|') : None]
            if (splitidx2 := sub_keypath.find('.plural.')) != -1:
                sub_keypath = sub_keypath[:splitidx2] + '.variations' + sub_keypath[splitidx2:] # Very hacky. Not sure why this works. But it does [Dec 2025]
        else:
            key_to_search_for = trans_unit.key

        xcstrings_entries = []
        if 1:
            for file_path, xcstrings_obj in xcstrings_objs.items():
                x = xcstrings_obj['strings'].get(key_to_search_for, None)
                if x: xcstrings_entries.append(x)
                

        mismatch_warning = ''
        
        # Extract xcstrings_entry and check key mismatches
        xcstrings_entry = None
        if len(xcstrings_entries) == 1:
            xcstrings_entry = xcstrings_entries[0];
        else:
            if len(xcstrings_entries) > 1:
                xcstrings_entry = [x for x in xcstrings_entries if trans_unit.source == x['localizations']['en']['stringUnit']['value']][0]
            else:
                xcstrings_entry = None
            if 1 and not args.no_key_mismatches:
                mismatch_warnings.append(f"""KEY mismatch for key Found {RED}{len(xcstrings_entries)}{RESET} entries in xcstrings files for {RED}'{trans_unit.key}'{RESET}\n""")

        if xcstrings_entry != None:
            # Check comment mismatch
            if 1 and not args.no_comment_mismatches:
                xcstrings_comment = xcstrings_entry.get('comment', '');
                if xcstrings_comment != trans_unit.note:
                    diff_xliff, diff_xcstrings = highlight_diff(trans_unit.note, xcstrings_comment)
                    mismatch_warnings.append(f"""COMMENT mismatch for key '{trans_unit.key}':\n    XLIFF:\n{textwrap.indent(diff_xliff, '        ')}\n    XCSTRINGS:\n{textwrap.indent(diff_xcstrings, '        ')}\n""")

            # Check source mismatch
            if 1 and not args.no_source_mismatches:
                xcstrings_source = None
                if sub_keypath:
                    xcstrings_source = mfdict_getkp(xcstrings_entry, f"localizations.en.{sub_keypath}.stringUnit.value")
                else:
                    xcstrings_source = mfdict_getkp(xcstrings_entry, "localizations.en.stringUnit.value")

                if xcstrings_source != trans_unit.source:
                    diff_xliff, diff_xcstrings = highlight_diff(trans_unit.source, xcstrings_source)
                    mismatch_warnings.append(f"""SOURCE mismatch for key '{trans_unit.key}'\n    XLIFF:\n{textwrap.indent(diff_xliff, '        ')}\n    XCSTRINGS:\n{textwrap.indent(diff_xcstrings, '        ')}\n""")

    mismatch_warnings.sort()
    mismatch_warnings = [f'\n(Mismatch {i})\n{mismatch_warnings[i]}' for i in range(len(mismatch_warnings))]
    # Print any detected mismatches
    print(f"Mismatches:")
    print(''.join(mismatch_warnings))