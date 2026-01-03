#!/usr/bin/env python3

#
# Created by Claude (Anthropic) - 2025
#

import argparse
import json
import os
from functools import cmp_to_key

import mfobjc
import mflocales

#
# Constants
#

website_repo = './../mac-mouse-fix-website'

#
# Helpers
#

def get_all_xcstrings_files() -> list[str]:
    """Get all .xcstrings files from both mac-mouse-fix and mac-mouse-fix-website repos."""
    main_files = mflocales.find_xcstrings_files('.')
    website_files = mflocales.find_xcstrings_files(website_repo)
    all_files = main_files + website_files
    all_files = sorted(all_files)

    return all_files

def get_all_xcstrings_files_with_ids() -> list[tuple[str, str]]:
    """
    Get all .xcstrings files with short identifiers.
    Returns list of (fileid, path) tuples.
    """
    paths = get_all_xcstrings_files()

    # Count occurrences of each base name
    name_counts: dict[str, int] = {}
    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]
        name_counts[name] = name_counts.get(name, 0) + 1

    # Assign unique ids
    name_seen: dict[str, int] = {}
    result: list[tuple[str, str]] = []

    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]

        if name_counts[name] > 1:
            # Duplicate name - add suffix
            idx = name_seen.get(name, 0) + 1
            name_seen[name] = idx
            fileid = f"{name}_{idx}"
        else:
            fileid = name

        result.append((fileid, path))

    return result


def get_xcstrings_path_by_fileid(fileid: str) -> str | None:
    """
    Get the file path for a given fileid.
    Returns None if not found.
    """
    files = get_all_xcstrings_files_with_ids()
    for fid, path in files:
        if fid == fileid:
            return path
    return None


def parse_key_with_variant(key: str) -> tuple[str, str | None]:
    """
    Parse a key that may contain a >variant suffix for pluralizable strings.
    Returns (base_key, variant) where variant is None for non-pluralizable keys.

    Examples:
        "some.key" -> ("some.key", None)
        "some.key>one" -> ("some.key", "one")
        "some.key>other" -> ("some.key", "other")
    """
    if '>' in key:
        parts = key.rsplit('>', 1)
        return (parts[0], parts[1])
    return (key, None)


def parse_string_path(path: str) -> tuple[str, str, str]:
    """
    Parse a string path in the format "fileid/key/locale" into its components.
    Returns (fileid, key, locale).

    Note: This assumes keys don't contain '/' characters. [Jan 2026]

    Examples:
        "Localizable/some.key/tr" -> ("Localizable", "some.key", "tr")
        "Localizable/some.key>one/de" -> ("Localizable", "some.key>one", "de")
    """
    parts = path.split('/')
    if len(parts) < 3:
        raise ValueError(f"Invalid path format: '{path}'. Expected 'fileid/key/locale'.")

    fileid = parts[0]
    locale = parts[-1]
    key = '/'.join(parts[1:-1])  # Everything in between (handles keys with / just in case)

    return (fileid, key, locale)


def get_all_columns_and_locales() -> tuple[list[str], list[str], list[tuple[str, dict]]]:
    """
    Load all xcstrings files and return available columns, locales, and file data.
    Returns (all_columns, locales, file_data) where file_data is list of (fileid, content).
    """
    files = get_all_xcstrings_files_with_ids()

    all_locales: set[str] = set()
    file_data: list[tuple[str, dict]] = []

    for fileid, path in files:
        with open(path, 'r', encoding='utf-8') as f:
            content = json.load(f)
            file_data.append((fileid, content))

            for key, string_info in content.get('strings', {}).items():
                localizations = string_info.get('localizations', {})
                all_locales.update(localizations.keys())

    # Sort locales (en first, then alphabetically)
    locales = sorted(all_locales, key=lambda l: (l != 'en', l))

    # Build all available columns
    all_columns = ['fileid', 'key', 'comment', 'en']
    for locale in locales:
        if locale == 'en':
            continue
        all_columns.append(f'{locale}_state')
        all_columns.append(locale)

    return all_columns, locales, file_data

#
# Commands
#

def cmd_list_files(_args):
    files = get_all_xcstrings_files_with_ids()

    if not files:
        print("No .xcstrings files found.")
        return

    max_id_len = max(len(fileid) for fileid, _ in files)

    print(f"Found {len(files)} .xcstrings file(s):\n")
    for fileid, path in files:
        print(f"  {fileid.ljust(max_id_len)}  ({path})")


def cmd_list_cols(_args):
    all_columns, _, _ = get_all_columns_and_locales()

    if not all_columns:
        print("No .xcstrings files found.")
        return

    print("Available columns:\n")
    for col in all_columns:
        print(f"  {col}")


def escape_cell(value: str) -> str:
    """Escape tabs and newlines in cell values for TSV output."""
    if value is None:
        return ""
    return value.replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def get_plural_variants_for_locale(loc_data: dict) -> dict[str, dict] | None:
    """
    Extract plural variants from a locale's data if it's a pluralizable string.
    Returns a dict mapping variant names (e.g., 'one', 'other') to their stringUnit dicts,
    or None if this is not a pluralizable string.
    """
    substitutions = loc_data.get('substitutions', {})
    pluralizable = substitutions.get('pluralizable', {})
    variations = pluralizable.get('variations', {})
    plural = variations.get('plural', {})

    if not plural:
        return None

    return plural


def is_pluralizable_string(string_info: dict) -> bool:
    """Check if a string is pluralizable by looking at any of its localizations."""
    localizations = string_info.get('localizations', {})
    for loc_data in localizations.values():
        if get_plural_variants_for_locale(loc_data) is not None:
            return True
    return False


def get_all_plural_variants_for_string(string_info: dict, requested_locales: list[str]) -> list[str]:
    """
    Get the union of all plural variant names across the requested locales for a pluralizable string.
    Returns variants in a canonical order: zero, one, two, few, many, other.
    """
    canonical_order = ['zero', 'one', 'two', 'few', 'many', 'other']

    all_variants: set[str] = set()
    localizations = string_info.get('localizations', {})

    for locale in requested_locales:
        loc_data = localizations.get(locale, {})
        variants = get_plural_variants_for_locale(loc_data)
        if variants:
            all_variants.update(variants.keys())

    # Sort by canonical order
    result = [v for v in canonical_order if v in all_variants]
    # Add any unexpected variants at the end (shouldn't happen, but just in case)
    for v in sorted(all_variants):
        if v not in result:
            result.append(v)

    return result


def extract_note_from_comment(comment: str) -> str:
    """
    Removes unnecessary autogenerated old-style plist stuff from comments generated by Interface Builder.

    When an old-style plist is detected, removes everything, except for the value for the 'Note', which is the actuall note left by the developer.
    
    Example input:
        Class = "NSMenuItem"; title = "Regular"; ObjectID = "17P-PJ-tV1"; Note = "Scrolling > Smoothness > Regular Option";
    Example output:
        Scrolling > Smoothness > Regular Option

    We implemented the same thing in mf-xcloc-editor [Jan 3 2026]
    
    """

    dict = mfobjc.NSPropertyListSerialization_loads(comment)
    if not mfobjc.isclass(dict, 'NSDictionary'): return comment

    note = mfobjc.NSDictionary_stringForKey(dict, 'Note')
    if not note: return ""
    
    return note


def cmd_inspect(args):
    """Inspect all string units from all .xcstrings files."""

    # Load data
    all_columns, locales, file_data = get_all_columns_and_locales()

    def print_help_and_exit(err):
        print(
            f"Invalid args passed to 'mfstrings inspect' command:"
            f"\n"
            f"\n{err}"
            f"\n"
            f"\nUsage: ./run mfstrings inspect --cols <columns> [--sortcol <column>] [--pretty]"
            f"\n"
            f"\nAvailable columns:"
            f"\n  - {'\n  - '.join(all_columns)}"
            f"\n"
            f"\nExample:"
            f"\n  ./run mfstrings inspect --cols fileid,key,comment,en,tr_state,tr --sortcol comment"
            f"\n"
            f"\nOutput is sorted by the first column unless --sortcol is specified."
            f"\n"
            f"\n--pretty tries to make the output more human-readable. Without --pretty, the output is a TSV (Tab separated values) table"
        )
        exit(1)

    if not file_data:
        print_help_and_exit("No .xcstrings files found.")

    # Determine which columns to show
    if not args.cols:
        print_help_and_exit("Missing --cols arg")

    columns = args.cols.split(',')

    # Validate columns
    for col in columns:
        if col not in all_columns:
            print_help_and_exit(f"Unknown column: {col}")

    # Determine which locales are being requested (for plural variant union)
    requested_locales = ['en']  # Always include 'en'
    for col in columns:
        if col in locales and col != 'en':
            requested_locales.append(col)
        elif col.endswith('_state'):
            locale = col[:-6]  # Remove '_state' suffix
            if locale in locales and locale not in requested_locales:
                requested_locales.append(locale)

    # Build all rows first (so we can sort)
    rows: list[dict[str, str]] = []

    for fileid, content in file_data:
        strings = content.get('strings', {})

        for key in strings.keys():
            string_info = strings[key]

            # Skip strings marked as "don't translate"
            if string_info.get('shouldTranslate') == False:
                continue

            comment = extract_note_from_comment(string_info.get('comment', ''))
            localizations = string_info.get('localizations', {})

            # Check if this is a pluralizable string
            if is_pluralizable_string(string_info):
                # Get union of all plural variants across requested locales
                all_variants = get_all_plural_variants_for_string(string_info, requested_locales)

                # Create one row per variant
                for variant in all_variants:
                    row_data: dict[str, str] = {
                        'fileid': fileid,
                        'key': f'{key}>{variant}',
                        'comment': comment,
                    }

                    # Get English value for this variant
                    en_loc_data = localizations.get('en', {})
                    en_variants = get_plural_variants_for_locale(en_loc_data)
                    if en_variants and variant in en_variants:
                        variant_string_unit = en_variants[variant].get('stringUnit', {})
                        row_data['en'] = variant_string_unit.get('value', '')
                    else:
                        row_data['en'] = '-'

                    # Get values for other locales
                    for locale in locales:
                        if locale == 'en':
                            continue
                        loc_data = localizations.get(locale, {})
                        loc_variants = get_plural_variants_for_locale(loc_data)

                        if loc_variants and variant in loc_variants:
                            variant_string_unit = loc_variants[variant].get('stringUnit', {})
                            state = variant_string_unit.get('state', '')
                            if state == '':
                                state = 'new'
                            row_data[f'{locale}_state'] = state
                            row_data[locale] = variant_string_unit.get('value', '')
                        else:
                            # This locale doesn't have this variant
                            row_data[f'{locale}_state'] = '-'
                            row_data[locale] = '-'

                    # Store row data (filter to requested columns)
                    filtered_row_data = {col: row_data.get(col, '') for col in columns}
                    rows.append(filtered_row_data)
            else:
                # Non-pluralizable string: single row as before
                row_data: dict[str, str] = {
                    'fileid': fileid,
                    'key': key,
                    'comment': comment,
                    'en': localizations.get('en', {}).get('stringUnit', {}).get('value', ''),
                }

                for locale in locales:
                    if locale == 'en':
                        continue
                    loc_data = localizations.get(locale, {})
                    string_unit = loc_data.get('stringUnit', {})
                    state = string_unit.get('state', '')
                    if state == '':
                        state = 'new'
                    row_data[f'{locale}_state'] = state
                    row_data[locale] = string_unit.get('value', '')

                # Store row data (filter to requested columns)
                filtered_row_data = {col: row_data.get(col, '') for col in columns}
                rows.append(filtered_row_data)

    # Validate --sortcol
    if args.sortcol:
        if not args.sortcol in columns:
            print_help_and_exit(f"Column '{args.sortcol}' which was passed to --sortcol, was not found in columns passed to --col: {columns}")

    # Sort
    def mfcmp(a, b):
        if args.sortcol:  # Sort by --sortcol
            if (x := mfobjc.NSString_localizedStandardCompare(a[args.sortcol], b[args.sortcol])): return x

        for col in columns:  # Sort by first, second, ... column
            if (x := mfobjc.NSString_localizedStandardCompare(a[col], b[col])): return x
        return 0
    rows.sort(key=cmp_to_key(mfcmp))

    # Output
    if args.pretty:
        # Pretty table with | separators
        print('\t|\t'.join(columns))
        for row in rows:
            row_values = [escape_cell(row.get(col, '')) for col in columns]
            print('\t|\t'.join(row_values))
    else:
        # TSV output
        print('\t'.join(columns))
        for row in rows:
            row_values = [escape_cell(row.get(col, '')) for col in columns]
            print('\t'.join(row_values))


def cmd_edit(args):
    """Edit a string's translation value and/or state in an .xcstrings file."""

    # Validate arguments
    if not args.value and not args.state:
        print("Error: At least one of --value or --state must be provided.")
        exit(1)

    valid_states = ['translated', 'needs_review']
    if args.state and args.state not in valid_states:
        print(f"Error: --state must be one of: {', '.join(valid_states)}")
        exit(1)

    # Parse the path
    try:
        fileid, key, locale = parse_string_path(args.path)
    except ValueError as e:
        print(f"Error: {e}")
        exit(1)

    # Find the xcstrings file
    file_path = get_xcstrings_path_by_fileid(fileid)
    if not file_path:
        print(f"Error: No .xcstrings file found with fileid '{fileid}'")
        print("Use './run mfstrings list-files' to see available fileids.")
        exit(1)

    # Parse the key (handle >variant suffix)
    base_key, variant = parse_key_with_variant(key)

    # Load the xcstrings file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = json.load(f)

    # Find the string
    strings = content.get('strings', {})
    if base_key not in strings:
        print(f"Error: Key '{base_key}' not found in {args.fileid}")
        exit(1)

    string_info = strings[base_key]
    localizations = string_info.setdefault('localizations', {})
    loc_data = localizations.setdefault(locale, {})

    # Handle pluralizable vs regular strings
    if variant:
        # Pluralizable string - edit a specific variant
        # Check if this string is actually pluralizable
        if not is_pluralizable_string(string_info):
            print(f"Error: Key '{base_key}' is not a pluralizable string, but variant '{variant}' was specified.")
            exit(1)

        # Ensure the structure exists for this locale
        # Structure: localizations/<locale>/substitutions/pluralizable/variations/plural/<variant>/stringUnit
        loc_data.setdefault('stringUnit', {'state': 'translated', 'value': '%#@pluralizable@'})
        substitutions = loc_data.setdefault('substitutions', {})
        pluralizable = substitutions.setdefault('pluralizable', {'formatSpecifier': 'd', 'variations': {'plural': {}}})
        variations = pluralizable.setdefault('variations', {})
        plural = variations.setdefault('plural', {})
        variant_data = plural.setdefault(variant, {'stringUnit': {}})
        string_unit = variant_data.setdefault('stringUnit', {})

        # Apply edits
        if args.value is not None:
            string_unit['value'] = args.value
        if args.state:
            string_unit['state'] = args.state

        print(f"Updated {fileid}/{base_key}>{variant} [{locale}]")

    else:
        # Regular (non-pluralizable) string
        if is_pluralizable_string(string_info):
            print(f"Error: Key '{base_key}' is a pluralizable string. Please specify a variant using '{base_key}>one', '{base_key}>other', etc.")
            exit(1)

        # Ensure stringUnit exists
        string_unit = loc_data.setdefault('stringUnit', {})

        # Apply edits
        if args.value is not None:
            string_unit['value'] = args.value
        if args.state:
            string_unit['state'] = args.state

        print(f"Updated {fileid}/{base_key} [{locale}]")

    # Write the file back
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(content, f, indent=2, ensure_ascii=False)
        f.write('\n')  # Add trailing newline

    # Print what was changed
    if args.value is not None:
        print(f"  value: {args.value}")
    if args.state:
        print(f"  state: {args.state}")


def main():

    # Validate cwd
    #   (Similar validation in uploadstrings.py > main())
    repo_name = os.path.basename(os.getcwd())
    assert repo_name == 'mac-mouse-fix', 'This script should be run from the mac-mouse-fix repo'
    assert os.path.isdir(website_repo), f'The mac-mouse-fix-website repo should be at {website_repo}'

    if 1:
        parser = argparse.ArgumentParser(
            description='Tool for inspecting and editing .xcstrings localization files.',
        )

        if 1:
            subparsers = parser.add_subparsers(dest='command', help='Available commands')

            # list-files command
            list_files_parser = subparsers.add_parser('list-files', help='List all .xcstrings files')
            list_files_parser.set_defaults(func=cmd_list_files)

            # list-cols command
            list_cols_parser = subparsers.add_parser('list-cols', help='List available columns for inspect command')
            list_cols_parser.set_defaults(func=cmd_list_cols)

            # inspect command
            inspect_parser = subparsers.add_parser('inspect', help='Inspect all string units (TSV output)') # - [ ] TODO: Consider adding a file-filter if this slows down the Claude's (currently takes 450ms) [Jan 2025]
            inspect_parser.add_argument('--pretty', action='store_true', help='Human-readable output with | separators')
            inspect_parser.add_argument('--cols', type=str, help='Comma-separated list of columns to show, in order (e.g., "tr_state,fileid,key,en,tr"). Omit this arg to see available columns. Output is sorted by first column unless --sortcol is specified.')
            inspect_parser.add_argument('--sortcol', type=str, help='Column to sort the table by. This column must also be passed to --cols.')
            inspect_parser.set_defaults(func=cmd_inspect)

            # edit command
            edit_parser = subparsers.add_parser('edit', help='Edit a translation value and/or state')
            edit_parser.add_argument('--path', type=str, required=True, help='Path to the string: "fileid/key/locale". For pluralizable strings, use "fileid/key>variant/locale" (e.g., "Localizable/some.key>one/tr")')
            edit_parser.add_argument('--value', type=str, help='The new translation value')
            edit_parser.add_argument('--state', type=str, help='The new state: "translated" or "needs_review"')
            edit_parser.set_defaults(func=cmd_edit)

        # Parse and execute
        args = parser.parse_args()

        if args.command is None:
            parser.print_help()
            return

        args.func(args)


if __name__ == '__main__':
    main()
