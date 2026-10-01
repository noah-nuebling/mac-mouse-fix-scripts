#!/usr/bin/env python3

#
# Script for importing .xcloc files into the Xcode project. 
#   
#   As of [Dec 2025], this 
#       - simply calls `xcodebuild -importLocalizations` 
#       - Prints the WARNINGS from `xcodebuild` (such as mismatched source-string) in stderr
#       - Manually finds mismatches, (also COMMENT mismatches, which xcodebuild doesn't find I think [Sep 2026]) reports them and flags them as 'needs_review'
#       - Makes the 'needs_review' state of plural parents match their children [Sep 2026]
#

import mfutils
import mflocales

import argparse
import tempfile
import os
import glob
from dataclasses import dataclass
from pathlib import Path
import textwrap
import json

import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

# 
# Color-printing helpers
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
# xml helpers
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
# dict helpers
#

def mfkeypath(dict, keypath: str):
    # Returns None if the keypath doesn't exist
    result = dict
    for key in keypath.split('/'):
        if key not in result: return None
        result = result[key]
    return result

def main(): 

    # Parse repo
    repo_path = os.getcwd()
    repo_name = os.path.basename(repo_path)

    # Validate repo
    assert repo_name in ['mac-mouse-fix', 'mac-mouse-fix-website'], f"Script expects to be ran from mac-mouse-fix or mac-mouse-fix-website repo. (I think). Was run from: {repo_path}"

    # Parse args
    parser = argparse.ArgumentParser()
    parser.add_argument('--xcloc-path', required=True, help="Path to the xcloc file you'd like to import")
    parser.add_argument('--skip-import', action='store_true', help="Only do the post-processing and validation (if you already imported before)")
    parser.add_argument('--skip-post-processing', action='store_true', help="Only do the import via xcodebuild -importLocalizations, and then finish")
    args = parser.parse_args()

    if not args.skip_import:
        # Get temp dir
        temp_dir_persistent = tempfile.gettempdir() + '/mmf-importstrings-persistent'
        if not os.path.isdir(temp_dir_persistent): os.mkdir(temp_dir_persistent)

        # Import using Xcode
        stdout, ret, stderr = mfutils.runclt(
            ' '.join([""
                ,f"xcrun xcodebuild -importLocalizations" # TODO: Consider setting the build-directory to a temp dir like in `uploadstrings.py`. I think that prevents nuking the build-cache. [Dec 2025]
                ,f"-scheme '{mflocales.xcodebuild_any_build_scheme(repo_path)}'"
                ,f"-derivedDataPath '{mflocales.xcodebuild_derived_data_path(temp_dir_persistent, repo_name)}'" # Using separate derivedData should speed up workflow. Same reason as for our `xcodebuild -exportLocalizations` usage inside uploadstrings.py [Dec 2025] || Idea: Could maybe use same temp dir as uploadstrings.py to speed things up in some cases.
                ,f"-localizationPath '{args.xcloc_path}'"
            ]),
            print_live_output=True,
            manually_handle_errors=True
        )
        assert not ret, f"xcodebuild -importLocalizations failed with code {ret}"

        # Print Xcode errors
        if stderr:
            print(f"\nxcodebuild -importLocalizations finished with stderr:\n{stderr}")
        
        print("")

    # Do post-processing
    if not args.skip_post_processing:
        print("Post-processing .xcstrings ...")
        print("")

        # Load xliff file
        xliff_paths = glob.glob(f"{glob.escape(args.xcloc_path)}/**/*.xliff", recursive=True)
        assert len(xliff_paths) == 1, f"Found unexpected number of xliff paths found in '{args.xcloc_path}'. xliff paths: {xliff_paths}"
        xliff_path = xliff_paths[0];
        xliff_obj = ET.fromstring(Path(xliff_path).read_text())

        # Load xcstrings files
        xcstrings_objs = { xcstrings_path: mfutils.read_xcstrings_file(xcstrings_path) for xcstrings_path in glob.glob("**/*.xcstrings", recursive=True)}
            
        # DEBUG
        print(f"Comparing .xliff at '{xliff_paths[0]}' with .xcstrings files: {json.dumps(list(xcstrings_objs.keys()), indent=4)}")
        print("")

        # Load all trans_units from the xliff file

        @dataclass
        class TransUnit:
            key:      str | None
            source:   str | None
            target:   str | None
            note:     str | None
            state:    str | None
            filepath: str | None
            targetlocale: str | None # This is the same for the entire file, so storing it on TransUnit doesn't make that much sense [Sep 2026]

        trans_units: list[TransUnit] = []

        for file in xliff_obj:
            filepath = file.attrib['original']
            targetlocale = file.attrib['target-language']
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
                            filepath=filepath,
                            targetlocale=targetlocale
                        ))

        # Iterate all the trans units

        mismatch_warnings = []
        for trans_unit in trans_units:
            
            if trans_unit.state == 'mf-dont-translate': 
                continue;

            sub_keypath = None
            key_to_search_for = None
            if (splitidx := trans_unit.key.find('|==|')) != -1:
                key_to_search_for = trans_unit.key[:splitidx]
                sub_keypath       = trans_unit.key[splitidx + len('|==|'):]
                splitidx2 = sub_keypath.find('.plural.')
                assert splitidx2 != -1, f"Unexpected format for key containing '|==|' (only plurals are supported): '{trans_unit.key}'"
                sub_keypath = sub_keypath[:splitidx2] + '.variations' + sub_keypath[splitidx2:] # Very hacky. Not sure why this works. But it does [Dec 2025]
                sub_keypath = sub_keypath.replace('.', '/')
            else:
                key_to_search_for = trans_unit.key

            xcstrings_entry = None
            xcstrings_entries_with_matching_key = []
            if 1:
                # Get all subtrees from the xcstrings file that have the same string key as this xml trans-unit (same key)
                for filepath, xcstrings_obj in xcstrings_objs.items():
                    x = xcstrings_obj['strings'].get(key_to_search_for, None)
                    if x: xcstrings_entries_with_matching_key.append({ "filepath": filepath, "xcstrings_entry": x })
                
                # Multiple matches: Disambiguate (Find xcstrings entry that best matches the xml trans-unit)
                if (len(xcstrings_entries_with_matching_key) > 1):
                    filtered = []
                    for xcstrings_entry in xcstrings_entries_with_matching_key:
                        if trans_unit.filepath.endswith(".xib"):
                            # Try to sort of simulat the path mapping that Xcode does from .xib file to its .xcstrings file [Sep 2026]
                            if (os.path.splitext(os.path.basename(trans_unit.filepath))[0] == os.path.splitext(os.path.basename(xcstrings_entry["filepath"]))[0] and 
                                xcstrings_entry["filepath"].endswith(".xcstrings") and
                                trans_unit.filepath.split('/')[:-2] == xcstrings_entry["filepath"].split('/')[:-2]
                            ):
                                filtered.append(xcstrings_entry)
                        else:
                            if trans_unit.filepath == xcstrings_entry["filepath"]:
                                filtered.append(xcstrings_entry)
                    
            
                    # Couldn't disambiguate - report
                    if (len(filtered) != 1):
                        mismatch_warnings.append(f"KEY mismatch - key {key_to_search_for} expected to be at '{trans_unit.filepath}' by the .xcloc file found in multiple .xcstrings files {[x['filepath'] for x in xcstrings_entries_with_matching_key]}.")
                        continue
                        
                    xcstrings_entries_with_matching_key = filtered

            # No matches - report
            if (not xcstrings_entries_with_matching_key):
                mismatch_warnings.append(f"KEY mismatch - key {key_to_search_for} expected to be at '{trans_unit.filepath}' by the .xcloc file not found in any .xcstrings file.")
                continue
            
            # Success - extract
            xcstrings_entry = xcstrings_entries_with_matching_key[0]['xcstrings_entry']

            # Sloppy addition
            def dbg_wrap_in_quotes(s): # Make it more obvious where string starts and ends to debug weird `COMMENT mismatch` errors
                return s
                # return "```\n" + s + "\n```"

            # Found the matching subtree of the xcstrings file for this xml trans-unit - check it for mismatches.
            if 1:
                
                # Get relevant string units in xcstrings file
                stringunit_en = None
                if sub_keypath: stringunit_en = mfkeypath(xcstrings_entry, f"localizations/en/{sub_keypath}/stringUnit")
                else:           stringunit_en = mfkeypath(xcstrings_entry, "localizations/en/stringUnit")
                stringunit_translation = None
                if sub_keypath: stringunit_translation = mfkeypath(xcstrings_entry, f"localizations/{trans_unit.targetlocale}/{sub_keypath}/stringUnit")
                else:           stringunit_translation = mfkeypath(xcstrings_entry, f"localizations/{trans_unit.targetlocale}/stringUnit")

                
                # Check comment mismatch
                if 1:
                    xcstrings_comment = xcstrings_entry.get('comment', '')
                    xcstrings_comment = xcstrings_comment.strip()
                    trans_unit_note = (trans_unit.note or '').strip()
                    if xcstrings_comment != trans_unit_note:
                        diff_xliff, diff_xcstrings = highlight_diff(trans_unit_note, xcstrings_comment)
                        if stringunit_translation: stringunit_translation['state'] = 'needs_review'
                        mismatch_warnings.append(f"""COMMENT mismatch for key '{trans_unit.key}':\n    XLIFF:\n{textwrap.indent(dbg_wrap_in_quotes(diff_xliff), '        ')}\n    XCSTRINGS:\n{textwrap.indent(dbg_wrap_in_quotes(diff_xcstrings), '        ')}\n""")
                # Check source mismatch
                if 1:
                    xcstrings_source = stringunit_en['value']
                    if xcstrings_source != trans_unit.source:
                        diff_xliff, diff_xcstrings = highlight_diff(trans_unit.source, xcstrings_source)
                        if stringunit_translation: stringunit_translation['state'] = 'needs_review' # [Sep 2026] `xcodebuild -importLocalizations` already flags source mismatches, so I guess this isn't necessary
                        mismatch_warnings.append(f"""SOURCE mismatch for key '{trans_unit.key}'\n    XLIFF:\n{textwrap.indent(diff_xliff, '        ')}\n    XCSTRINGS:\n{textwrap.indent(diff_xcstrings, '        ')}\n""")

        
        # Update the state of plural parents to match their children (mf-xcloc-editor only shows the children's state) [Sep 2026]
        for filepath, xcstrings_obj in xcstrings_objs.items():
            for key in mfkeypath(xcstrings_obj, 'strings'):
                for locale in mfkeypath(xcstrings_obj, f'strings/{key}/localizations') or []:
                    alltranslated = True
                    isplural = False
                    for amount in mfkeypath(xcstrings_obj, f'strings/{key}/localizations/{locale}/substitutions/pluralizable/variations/plural') or []: # Assumes all pluralizable strings use `@pluralizable` as the substitutible which is the case for MMF [Sep 2026]
                        childstate = mfkeypath(xcstrings_obj, f'strings/{key}/localizations/{locale}/substitutions/pluralizable/variations/plural/{amount}/stringUnit/state')
                        if childstate: isplural = True
                        if childstate != 'translated':
                            alltranslated = False
                            break
                    if isplural: mfkeypath(xcstrings_obj, f'strings/{key}/localizations/{locale}/stringUnit')['state'] = 'translated' if alltranslated else 'needs_review'
        print(f"(Made plural parent state match children.)")
        print("")

        # Write the xcstrings file back to file (so our 'needs_review' annotations stick) [Sep 2026]
        for filepath, xcstrings_obj in xcstrings_objs.items(): # Just write them all back, this code is currently not sophisticated enough to track what changed [Sep 2026]
            mfutils.write_xcstrings_file(filepath, xcstrings_obj)

        # Print any detected mismatches
        mismatch_warnings.sort()
        mismatch_warnings = [f'\n(Mismatch {i})\n{mismatch_warnings[i]}' for i in range(len(mismatch_warnings))]
        print(f"Found mismatches:")
        print(''.join(mismatch_warnings))
        print("")
        print(f"(COMMENT and SOURCE mismatches have been flagged as 'needs_review' in the .xcstrings files - locale '{trans_units[0].targetlocale}')")
        print("")

    # Finish
    print("Done")


if __name__ == "__main__":
    main()
