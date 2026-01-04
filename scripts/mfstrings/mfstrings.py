#!/usr/bin/env python3

#
# Created by Claude (Anthropic) - 2025
#

import argparse
import json
import os
import re
import sys
from difflib import SequenceMatcher
from functools import cmp_to_key

import mfobjc
import mflocales
import mfutils

#
# Constants
#

website_repo = './../mac-mouse-fix-website'

# ANSI colors
RED = '\033[91m'
GREEN = '\033[92m'
RESET = '\033[0m'
BOLD = '\033[1m'
DIM = '\033[2m'

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


def get_file_content_at_ref(path: str, ref: str) -> str | None:
    """
    Get file content at a specific git ref using `git show`.
    Returns None if the file doesn't exist at that ref.
    """
    import subprocess

    # Determine which repo this file is in and get the relative path
    abs_path = os.path.abspath(path)

    # Check if it's in mac-mouse-fix-website
    if website_repo in path or abs_path.startswith(os.path.abspath(website_repo)):
        repo_root = os.path.abspath(website_repo)
        rel_path = os.path.relpath(abs_path, repo_root)
    else:
        repo_root = os.getcwd()  # mac-mouse-fix
        rel_path = os.path.relpath(abs_path, repo_root)

    try:
        result = subprocess.run(
            ['git', 'show', f'{ref}:{rel_path}'],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return None  # File doesn't exist at this ref


def get_all_columns_and_locales(git_ref: str | None = None) -> tuple[list[str], list[str], list[tuple[str, dict]]]:
    """
    Load all xcstrings files and return available columns, locales, and file data.
    Returns (all_columns, locales, file_data) where file_data is list of (fileid, content).

    If git_ref is provided, loads file contents from that git ref instead of the working directory.
    """
    files = get_all_xcstrings_files_with_ids()

    all_locales: set[str] = set()
    file_data: list[tuple[str, dict]] = []

    for fileid, path in files:
        if git_ref:
            content_str = get_file_content_at_ref(path, git_ref)
            if content_str is None:
                continue  # File doesn't exist at this ref
            content = json.loads(content_str)
        else:
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


def unescape_value(value: str) -> str:
    """Unescape \\n, \\t, \\r in input values (inverse of escape_cell)."""
    if value is None:
        return ""
    return value.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")


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


def get_string_unit_data(string_unit: dict) -> tuple[str, str]:
    """
    Extract state and value from a stringUnit dict.
    Returns (state, value) where state defaults to 'new' if empty.
    """
    state = string_unit.get('state', '')
    if state == '':
        state = 'new'
    value = string_unit.get('value', '')
    return state, value


def generate_inspect_output(columns: list[str], sortcol: str | None, git_ref: str | None = None) -> str:
    """
    Generate inspect output as TSV string.

    If git_ref is provided, loads file contents from that git ref instead of the working directory.
    """
    # Load data
    all_columns, locales, file_data = get_all_columns_and_locales(git_ref=git_ref)

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

                    # Get values for each locale (including English)
                    for locale in locales:
                        loc_data = localizations.get(locale, {})
                        loc_variants = get_plural_variants_for_locale(loc_data)

                        if loc_variants and variant in loc_variants:
                            string_unit = loc_variants[variant].get('stringUnit', {})
                            state, value = get_string_unit_data(string_unit)
                        else:
                            state, value = '-', '-'  # This locale doesn't have this variant

                        if locale == 'en':
                            row_data['en'] = value
                        else:
                            row_data[f'{locale}_state'] = state
                            row_data[locale] = value

                    # Store row data (filter to requested columns)
                    filtered_row_data = {col: row_data.get(col, '') for col in columns}
                    rows.append(filtered_row_data)
            else:
                # Non-pluralizable string: single row
                row_data: dict[str, str] = {
                    'fileid': fileid,
                    'key': key,
                    'comment': comment,
                }

                # Get values for each locale (including English)
                for locale in locales:
                    loc_data = localizations.get(locale, {})
                    string_unit = loc_data.get('stringUnit', {})
                    state, value = get_string_unit_data(string_unit)

                    if locale == 'en':
                        row_data['en'] = value
                    else:
                        row_data[f'{locale}_state'] = state
                        row_data[locale] = value

                # Store row data (filter to requested columns)
                filtered_row_data = {col: row_data.get(col, '') for col in columns}
                rows.append(filtered_row_data)

    # Sort
    def mfcmp(a, b):
        if sortcol:  # Sort by --sortcol
            if (x := mfobjc.NSString_localizedStandardCompare(a[sortcol], b[sortcol])): return x

        for col in columns:  # Sort by first, second, ... column
            if (x := mfobjc.NSString_localizedStandardCompare(a[col], b[col])): return x
        return 0
    rows.sort(key=cmp_to_key(mfcmp))

    # Generate output (always TSV - pretty printing is handled separately)
    lines = []
    lines.append('\t'.join(columns))
    for row in rows:
        row_values = [escape_cell(row.get(col, '')) for col in columns]
        lines.append('\t'.join(row_values))

    return '\n'.join(lines)


def highlight_matches(text: str, pattern: re.Pattern | None) -> str:
    """
    Highlight all matches of pattern in text with YELLOW color.
    Returns text unchanged if pattern is None.
    """
    if pattern is None:
        return text

    YELLOW = '\033[93m'
    result = []
    last_end = 0

    for match in pattern.finditer(text):
        # Add text before match
        result.append(text[last_end:match.start()])
        # Add highlighted match
        result.append(f"{YELLOW}{match.group()}{RESET}")
        last_end = match.end()

    # Add remaining text
    result.append(text[last_end:])
    return ''.join(result)


def apply_highlights(text: str, ranges: list[tuple[int, int, str]]) -> str:
    """
    Apply multiple color highlights to text.
    ranges is a list of (start, end, color) tuples.
    Later ranges override earlier ones where they overlap.
    """
    if not ranges:
        return text

    # Build a color map for each character position
    colors: list[str | None] = [None] * len(text)

    for start, end, color in ranges:
        for i in range(start, min(end, len(text))):
            colors[i] = color

    # Build the result string
    result = []
    current_color: str | None = None

    for i, char in enumerate(text):
        char_color = colors[i]
        if char_color != current_color:
            if current_color is not None:
                result.append(RESET)
            if char_color is not None:
                result.append(char_color)
            current_color = char_color
        result.append(char)

    if current_color is not None:
        result.append(RESET)

    return ''.join(result)


def print_row_pretty(columns: list[str], row_values: list[str], grep_pattern: re.Pattern | None = None):
    """
    Print a single row in human-readable format.
    The first column is printed as a bold header, the rest are indented below.
    row_values should be escaped TSV values matching the columns order.
    If grep_pattern is provided, matches will be highlighted.
    """
    # First column is the header
    header_val = row_values[0] if len(row_values) > 0 else ''
    header_display = unescape_value(header_val)
    print(f"{BOLD}{highlight_matches(header_display, grep_pattern)}{RESET}")

    # Rest of the columns are indented
    for i, col in enumerate(columns[1:], start=1):
        val = row_values[i] if i < len(row_values) else ''
        val_display = unescape_value(val).replace('\n', '\n    ')  # Indent multiline
        val_display = highlight_matches(val_display, grep_pattern)
        print(f"  {DIM}{col}:{RESET}")
        print(f"    {val_display}")


def cmd_inspect(args):
    """Inspect all string units from all .xcstrings files."""

    # Load data (for validation and help text)
    all_columns, locales, file_data = get_all_columns_and_locales()

    def print_help_and_exit(err):
        print(
            f"Invalid args passed to 'mfstrings inspect' command:"
            f"\n"
            f"\n{err}"
            f"\n"
            f"\nUsage: ./run mfstrings inspect --cols <columns> [--sortcol <column>] [--pretty] [--diff]"
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
            f"\n"
            f"\n--diff shows the diff between HEAD and the current worktree"
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

    # Validate --sortcol
    if args.sortcol:
        if args.sortcol not in columns:
            print_help_and_exit(f"Column '{args.sortcol}' which was passed to --sortcol, was not found in columns passed to --col: {columns}")

    # Validate --grep
    grep_pattern = None
    if args.grep:
        if not args.pretty:
            print(f"Warning: --grep is only supported with --pretty. For TSV output, pipe to grep instead:", file=sys.stderr)
            print(f"  ./run mfstrings inspect --cols ... | grep '{args.grep}'", file=sys.stderr)
            exit(1)
        try:
            grep_pattern = re.compile(args.grep, re.IGNORECASE)
        except re.error as e:
            print(f"Error: Invalid regex pattern '{args.grep}': {e}")
            exit(1)

    # Handle --diff mode
    if args.diff:
        # Generate output for HEAD and worktree
        output_head = generate_inspect_output(columns, args.sortcol, git_ref='HEAD')
        output_worktree = generate_inspect_output(columns, args.sortcol, git_ref=None)

        lines_head = output_head.splitlines()
        lines_worktree = output_worktree.splitlines()

        # Build a map of (fileid, key) -> line for each version
        def parse_line(line: str) -> tuple[str, str, str]:
            """Parse a line into (fileid, key, rest)."""
            parts = line.split('\t', 2)
            if len(parts) >= 2:
                return (parts[0], parts[1], line)
            return ('', '', line)

        head_map = {}
        for line in lines_head[1:]:  # Skip header
            fileid, key, _ = parse_line(line)
            head_map[(fileid, key)] = line

        worktree_map = {}
        for line in lines_worktree[1:]:  # Skip header
            fileid, key, _ = parse_line(line)
            worktree_map[(fileid, key)] = line

        # Find changes
        all_keys = set(head_map.keys()) | set(worktree_map.keys())
        has_changes = False

        for fk in sorted(all_keys):
            old_line = head_map.get(fk)
            new_line = worktree_map.get(fk)

            if old_line == new_line:
                continue  # No change

            # Filter by grep pattern if provided
            if grep_pattern:
                # Check if pattern matches either old or new line
                old_matches = old_line and grep_pattern.search(old_line)
                new_matches = new_line and grep_pattern.search(new_line)
                if not old_matches and not new_matches:
                    continue

            has_changes = True
            fileid, key = fk

            if args.pretty:
                # Human-readable output with colors
                # Apply grep highlighting to header elements
                fileid_display = highlight_matches(fileid, grep_pattern)
                key_display = highlight_matches(key, grep_pattern)

                if old_line is None:
                    # Added
                    print(f"{GREEN}+ [{fileid_display}] {key_display}{RESET}")
                    new_line_display = highlight_matches(new_line, grep_pattern)
                    print(f"  {GREEN}{new_line_display}{RESET}")
                elif new_line is None:
                    # Removed
                    print(f"{RED}- [{fileid_display}] {key_display}{RESET}")
                    old_line_display = highlight_matches(old_line, grep_pattern)
                    print(f"  {RED}{old_line_display}{RESET}")
                else:
                    # Changed - highlight the differences
                    print(f"{BOLD}~ [{fileid_display}] {key_display}{RESET}")

                    # Split into columns and show diff for each changed column
                    old_parts = old_line.split('\t')
                    new_parts = new_line.split('\t')

                    for i, col in enumerate(columns):
                        old_val = old_parts[i] if i < len(old_parts) else ''
                        new_val = new_parts[i] if i < len(new_parts) else ''

                        if old_val != new_val:
                            # Unescape for display
                            old_val_display = unescape_value(old_val)
                            new_val_display = unescape_value(new_val)

                            # Build highlight ranges: diff (red/green) first, then grep (yellow) to override
                            YELLOW = '\033[93m'
                            old_ranges: list[tuple[int, int, str]] = []
                            new_ranges: list[tuple[int, int, str]] = []

                            # Add diff highlights (red/green) first
                            matcher = SequenceMatcher(None, old_val_display, new_val_display)
                            for op, i1, i2, j1, j2 in matcher.get_opcodes():
                                if op == 'delete':
                                    old_ranges.append((i1, i2, RED))
                                elif op == 'insert':
                                    new_ranges.append((j1, j2, GREEN))
                                elif op == 'replace':
                                    old_ranges.append((i1, i2, RED))
                                    new_ranges.append((j1, j2, GREEN))

                            # Add grep highlights (yellow) - these override diff colors
                            if grep_pattern:
                                for m in grep_pattern.finditer(old_val_display):
                                    old_ranges.append((m.start(), m.end(), YELLOW))
                                for m in grep_pattern.finditer(new_val_display):
                                    new_ranges.append((m.start(), m.end(), YELLOW))

                            # Apply highlights
                            old_display = apply_highlights(old_val_display, old_ranges)
                            new_display = apply_highlights(new_val_display, new_ranges)

                            # Indent multiline content
                            old_display = old_display.replace('\n', '\n      ')
                            new_display = new_display.replace('\n', '\n      ')

                            print(f"  {DIM}{col}:{RESET}")
                            print(f"    {RED}-{RESET} {old_display}")
                            print(f"    {GREEN}+{RESET} {new_display}")

                print()  # Blank line between entries
            else:
                # Machine-readable TSV diff output
                # Format: +/-/~ <TAB> fileid <TAB> key <TAB> col1 <TAB> col2 ...
                if old_line is None:
                    print(f"+\t{new_line}")
                elif new_line is None:
                    print(f"-\t{old_line}")
                else:
                    print(f"-\t{old_line}")
                    print(f"+\t{new_line}")

        if not has_changes:
            if args.pretty:
                print("No changes.")
            exit(0)
        else:
            exit(1)
    else:
        # Normal output
        output = generate_inspect_output(columns, args.sortcol)
        if args.pretty:
            # Human-readable output
            lines = output.splitlines()
            for line in lines[1:]:  # Skip header
                # Filter by grep pattern if provided
                if grep_pattern and not grep_pattern.search(line):
                    continue

                parts = line.split('\t')
                print_row_pretty(columns, parts, grep_pattern)
                print()  # Blank line between entries
        else:
            # TSV output
            print(output)


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
        print(f"Error: Key '{base_key}' not found in {fileid}")
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

        # Apply edits (unescape \n, \t, \r to match inspect output format)
        if args.value is not None:
            string_unit['value'] = unescape_value(args.value)
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

        # Apply edits (unescape \n, \t, \r to match inspect output format)
        if args.value is not None:
            string_unit['value'] = unescape_value(args.value)
        if args.state:
            string_unit['state'] = args.state

        print(f"Updated {fileid}/{base_key} [{locale}]")

    # Write the file back (using mfutils to match Xcode's JSON formatting)
    mfutils.write_xcstrings_file(file_path, content)

    # Print what was changed (show escaped form for consistency with inspect)
    if args.value is not None:
        print(f"  value: {escape_cell(unescape_value(args.value))}")
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
            inspect_parser.add_argument('--diff', action='store_true', help='Show diff between HEAD and current worktree')
            inspect_parser.add_argument('--grep', type=str, help='Filter rows by regex pattern and highlight matches (requires --pretty)')
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
