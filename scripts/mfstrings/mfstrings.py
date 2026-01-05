#!/usr/bin/env python3

"""
    mfstrings.py is a file created and primarily maintained (By Claude)
"""

import argparse
import json
import os
import re
import sys
from difflib import SequenceMatcher
from functools import cmp_to_key

from pathlib import Path

import mfobjc
import mflocales
import mfutils

from mfutils import mfkeypath

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


def find_xcstrings__ids_to_paths() -> dict[str, str]:
    """
    Returns {fileid -> path} map
    """

    # Get all .xcstrings file paths from both mac-mouse-fix and mac-mouse-fix-website repos.
    paths = []
    if 1:
        main_files = mflocales.find_xcstrings_files('.')
        website_files = mflocales.find_xcstrings_files(website_repo)
        paths = main_files + website_files

    # Count occurrences of each base name
    name_counts: dict[str, int] = {}
    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]
        name_counts[name] = name_counts.get(name, 0) + 1

    # Assign unique ids
    name_seen: dict[str, int] = {}
    result: dict[str, str] = {}

    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]

        if name_counts[name] > 1:
            # Duplicate name - add suffix
            idx = name_seen.get(name, 0) + 1
            name_seen[name] = idx
            fileid = f"{name}_{idx}"
        else:
            fileid = name

        result[fileid] = path

    return result

def repo_root_for_path(filepath: str) -> str: # Determine which repo this file belongs to
    if os.path.normpath(filepath).startswith('../mac-mouse-fix-website'):
        return '../mac-mouse-fix-website'
    else:
        return '.'

def available_columns_for_locales(locales: list[str]):
    
    # Build all available columns [Jan 2026]
    #   Pass in a union of locales from all xcstrings files [Jan 2026]
    #   Order: key first (for --pretty readability), then metadata, then translations, then states at the end
    
    all_columns = ['key', 'fileid', 'comment', 'en']

    # Add translation columns (without state)
    for locale in locales:
        if locale == 'en':
            continue
        all_columns.append(locale)

    # Add state columns at the end
    for locale in locales:
        if locale == 'en':
            continue
        all_columns.append(f'state:{locale}')

    return all_columns

def xcstrings_locales(xcstrings_objs: list[dict]):

    # Collect locales from xcstrings files.
    all_locales: set[str] = set()
    for xcstrings_obj in xcstrings_objs:
        for key in mfkeypath(xcstrings_obj, 'strings'):
            all_locales.update(list(mfkeypath(xcstrings_obj, f"strings/{key}/localizations").keys()))

    # Sort locales (en first, then alphabetically)
    return sorted(all_locales, key=lambda l: (l != 'en', l))

def load_xcstrings__paths_to_objs(xcstrings_paths: list[str], git_ref: str | None = None) -> dict[str, dict]:
    """
    Returns {xcstrings_path: xcstrings_obj}

    If git_ref is provided, loads file contents from that git ref instead of the working directory.
    """
    
    result: dict[str, dict] = {}
    
    for path in xcstrings_paths:
        if git_ref: # Get file content at a specific git ref using `git show`.
            repo_root = repo_root_for_path(path)
            content_str = mfutils.runclt(f'git show {git_ref}:{os.path.relpath(path, repo_root)}', cwd=repo_root)
        else:       content_str = Path(path).read_text()
        result[path] = json.loads(content_str)

    return result


def escape_cell(value: str) -> str:
    """
    Escape tabs and newlines in cell values for TSV output.
    
    NOTE: [Jan 2026] Some cell values contain U+2028 (Shift+Return) instead of `\n`. 
        This will not escape U+2028, but .splitlines() will split on it!
        -> split('\n') instead splitlines(), to split the TSV table into rows!

    """
    if value is None:
        return ""
    return value.replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def unescape_cell(value: str) -> str:
    """Unescape \\n, \\t, \\r in input values (inverse of escape_cell)."""
    if value is None:
        return ""
    return value.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")


def is_pluralizable_string(string_info: dict) -> bool:
    """Check if a string is pluralizable by looking at the English version."""
    return bool(mfkeypath(string_info, f"localizations/en/substitutions/pluralizable/"))

def get_string_unit_data(string_unit: dict) -> tuple[str, str]:
    """
    Extract state and value from a stringUnit dict.
    Maps raw state to either 'translated' or 'needs_review'. (.xcstrings contain some more states which we all map to needs_review) (Binary state should help with grepping.)
    """

    state = 'translated' if (string_unit.get('state', '') == 'translated') else 'needs_review'
    value = string_unit.get('value', '')
    
    return state, value


def inspect_output_tsv(columns: list[str], sortcol: str, fileid_filter: str, git_ref: str | None = None) -> str:
    """
    Generate inspect output as TSV string.

    Args:
        fileid_filter: File ID to inspect. Use "all" to inspect all files.
        git_ref: If provided, loads file contents from that git ref instead of the working directory.
    """
    # Load data
    xcstrings__ids_to_paths = find_xcstrings__ids_to_paths()

    # Filter by fileid if not "all"
    if fileid_filter != 'all':
        if fileid_filter not in xcstrings__ids_to_paths:
            raise ValueError(f"Unknown fileid: '{fileid_filter}'. Run './run mfstrings list-files' to see available file IDs.")
        xcstrings__ids_to_paths = {fileid_filter: xcstrings__ids_to_paths[fileid_filter]}

    xcstrings__paths_to_objs = load_xcstrings__paths_to_objs(list(xcstrings__ids_to_paths.values()), git_ref=git_ref)
    locales = xcstrings_locales(list(xcstrings__paths_to_objs.values()))

    # Determine which locales are being requested (for plural variant union)
    requested_locales = ['en']  # Always include 'en'
    if 1:
        for col in columns:
            if col in locales and col != 'en':
                requested_locales.append(col)
            elif col.startswith('state:'):
                locale = col[6:]  # Remove 'state:' prefix
                if locale in locales and locale not in requested_locales:
                    requested_locales.append(locale)

    # Build all rows first (so we can sort)
    rows: list[dict[str, str]] = []

    for fileid in xcstrings__ids_to_paths:
        
        xcstrings_obj = xcstrings__paths_to_objs[xcstrings__ids_to_paths[fileid]]

        for key in mfkeypath(xcstrings_obj, f"strings"):
            

            # Skip strings marked as "don't translate"
            if mfkeypath(xcstrings_obj, f"strings/{key}/shouldTranslate") == False:
                continue
            
            # Extract comment
            comment = str(mfkeypath(xcstrings_obj, f"strings/{key}/comment") or '')

            # Process comment
            if 1:
                """
                When an old-style plist is detected, removes everything, except for the value for the 'Note', which is the actual comment left by the developer.
                
                Example input:  Class = "NSMenuItem"; title = "Regular"; ObjectID = "17P-PJ-tV1"; Note = "Scrolling > Smoothness > Regular Option";
                Example output: Scrolling > Smoothness > Regular Option

                We implemented the same thing in mf-xcloc-editor [Jan 3 2026]                
                """

                dict = mfobjc.NSPropertyListSerialization_loads(comment)
                if mfobjc.isclass(dict, 'NSDictionary'):
                    comment = mfobjc.NSDictionary_stringForKey(dict, 'Note') or ""

            # Check if this is a pluralizable string
            if is_pluralizable_string(mfkeypath(xcstrings_obj, f"strings/{key}")):
                
                # Get union of all plural variants across requested locales
                all_variants: set[str]
                if 1:
                    all_variants = set()
                    for locale in requested_locales:
                        all_variants.update(mfkeypath(xcstrings_obj, f"strings/{key}/localizations/{locale}/substitutions/pluralizable/variations/plural").keys())

                    # Sort variants by 'canonical' order
                    canonical_order = ['zero', 'one', 'two', 'few', 'many', 'other']
                    assert all(v in canonical_order for v in all_variants), f"Unexpected plural variants found for key '{key}'. Expected: {canonical_order}, Found: {all_variants}"
                    all_variants = [v for v in canonical_order if v in all_variants]

                # Create one row per variant
                for variant in all_variants:
                    row_data: dict[str, str] = {
                        'fileid': fileid,
                        'key': f'{key}>{variant}',
                        'comment': comment,
                    }

                    # Get values for each locale (including English)
                    for locale in locales:
                        loc_variants = mfkeypath(xcstrings_obj, f"strings/{key}/localizations/{locale}/substitutions/pluralizable/variations/plural")

                        if loc_variants and variant in loc_variants:
                            
                            string_unit = mfkeypath(xcstrings_obj, f"strings/{key}/localizations/{locale}/substitutions/pluralizable/variations/plural/{variant}/stringUnit")
                            state, value = get_string_unit_data(string_unit)
                        else:
                            state, value = '-', '-'  # This locale doesn't have this variant

                        if locale == 'en':
                            row_data['en'] = value
                        else:
                            row_data[f'state:{locale}'] = state
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
                    string_unit = mfkeypath(xcstrings_obj, f"strings/{key}/localizations/{locale}/stringUnit")
                    state, value = get_string_unit_data(string_unit)

                    if locale == 'en':
                        row_data['en'] = value
                    else:
                        row_data[f'state:{locale}'] = state
                        row_data[locale] = value

                # Store row data (filter to requested columns)
                filtered_row_data = {col: row_data.get(col, '') for col in columns}
                rows.append(filtered_row_data)

    # Sort
    def mfcmp(a, b):
        # Primary sort by --sortcol
        if (x := mfobjc.NSString_localizedStandardCompare(a[sortcol], b[sortcol])): return x
        # Secondary sort by remaining columns in order
        for col in columns:
            if col == sortcol: continue
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


def print_row_pretty(
    row_index: int,
    columns: list[str],
    row_values: list[str],
    grep_pattern: re.Pattern | None = None,
    old_row_values: list[str] | None = None,
    diff_prefix: str = ''
):
    """
    Print a single row in human-readable format.

    Args:
        columns: Column names
        row_values: Current/new row values (escaped TSV)
        grep_pattern: Optional regex pattern for highlighting matches
        old_row_values: If provided, shows diff between old and new values
        diff_prefix: Prefix for the header line (e.g., '+', '-', '~')
    """
    # First column value is the header
    header_val = f"({row_index})"
    header_val += ' ' + (unescape_cell(row_values[0]) if len(row_values) > 0 else '')
    header_display = highlight_matches(header_val, grep_pattern)

    # Print header
    if diff_prefix:
        print(f"{BOLD}{diff_prefix} {header_display}{RESET}")
    else:
        print(f"{BOLD}{header_display}{RESET}")

    # Print remaining columns (skip first which is the header)
    for i, col in enumerate(columns):
        if i == 0:
            continue

        new_val = row_values[i] if i < len(row_values) else ''
        new_val_display = unescape_cell(new_val)

        if old_row_values is not None:
            # Diff mode
            old_val = old_row_values[i] if i < len(old_row_values) else ''
            old_val_display = unescape_cell(old_val)

            if old_val != new_val:
                # Changed column - show diff with highlights
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
            else:
                # Unchanged column
                val_display = highlight_matches(new_val_display, grep_pattern)
                val_display = val_display.replace('\n', '\n    ')
                print(f"  {DIM}{col}:{RESET}")
                print(f"    {val_display}")
        else:
            # Non-diff mode
            val_display = highlight_matches(new_val_display, grep_pattern)
            val_display = val_display.replace('\n', '\n    ')
            print(f"  {DIM}{col}:{RESET}")
            print(f"    {val_display}")


def cmd_inspect(args):
    """Inspect string units from .xcstrings files."""

    # Load data (for validation and help text)
    xcstrings__ids_to_paths = find_xcstrings__ids_to_paths()
    xcstrings__paths_to_objs = load_xcstrings__paths_to_objs(list(xcstrings__ids_to_paths.values()))
    locales = xcstrings_locales(list(xcstrings__paths_to_objs.values()))
    all_columns = available_columns_for_locales(locales)

    def print_help_and_exit(err): # TODO: Unify the way we print help / input errors [Jan 2026]
        print(
            f"Invalid args passed to 'mfstrings inspect' command:"
            f"\n"
            f"\n{err}"
            f"\n"
            f"\nUsage: ./run mfstrings inspect --fileid <fileid> --cols <columns> --sortcol <column> [--pretty] [--diff]"
            f"\n"
            f"\nAvailable file IDs: {', '.join(xcstrings__ids_to_paths.keys())}"
            f"\n"
            f"\nAvailable columns:"
            f"\n  - {'\n  - '.join(all_columns)}"
            f"\n"
            f"\nExample:"
            f"\n  ./run mfstrings inspect --fileid all --cols fileid,key,comment,en,state:tr,tr --sortcol key"
            f"\n  ./run mfstrings inspect --fileid Localizable --cols key,en,tr,state:tr --sortcol key"
            f"\n  ./run mfstrings inspect --fileid all --cols all --sortcol key"
            f"\n"
            f"\n--pretty tries to make the output more human-readable. Without --pretty, the output is a TSV (Tab separated values) table"
            f"\n"
            f"\n--diff shows the diff between HEAD and the current worktree"
            f"\n"
            f"\n state:LOCALE columns contain either 'translated' or 'needs_review'."
        )
        exit(1)

    if not xcstrings__paths_to_objs:
        print_help_and_exit("No .xcstrings files found.")

    # Validate --fileid
    if args.fileid != 'all' and args.fileid not in xcstrings__ids_to_paths:
        print_help_and_exit(f"Unknown fileid: '{args.fileid}'")

    # Handle 'all' keyword to include all columns [Jan 2026]
    if args.cols == 'all':
        columns = all_columns
    else:
        columns = args.cols.split(',')

        # Validate columns
        for col in columns:
            if col not in all_columns:
                print_help_and_exit(f"Unknown column: {col}")

    # Validate --sortcol
    if args.sortcol not in columns:
        print_help_and_exit(f"Column '{args.sortcol}' which was passed to --sortcol, was not found in columns passed to --cols: {columns}")

    # Validate --grep
    grep_pattern = None
    if args.grep:
        if not args.pretty:
            print(f"Warning: --grep is only supported with --pretty. For TSV output, pipe to grep instead:", file=sys.stderr) # TODO: Stupid Claude didn't use print_help_and_exit(). (It's right above) There are so many different error reporting / help-printing mechanisms now. Claude 4.5 Opus still kinda stupid sometimes. Still decends into chaos if you let it do its thing for too long I think.
            print(f"  ./run mfstrings inspect --fileid ... --cols ... | grep '{args.grep}'", file=sys.stderr)
            exit(1)
        try:
            grep_pattern = re.compile(args.grep, re.IGNORECASE)
        except re.error as e:
            print(f"Error: Invalid regex pattern '{args.grep}': {e}") 
            exit(1)

    # Print the output

    if not args.diff: # Normal (non-diff) output

        output = inspect_output_tsv(columns, args.sortcol, args.fileid)
        
        if not args.pretty: 
            print(output)
        else:               # Human-readable output
            lines = output.split('\n')
            row_counter = 0
            for line in lines[1:]:  # Skip header
                # Filter by grep pattern if provided
                if grep_pattern and not grep_pattern.search(line):
                    continue

                parts = line.split('\t')
                print_row_pretty(row_counter, columns, parts, grep_pattern)
                row_counter += 1
                print()  # Blank line between entries

    else: # --diff output
        
        # Validate --diff
        if args.diff:
            if 'key' not in columns or 'fileid' not in columns:
                print(f"Error: --diff needs key and fileid columns to be present.") # Improvement idea: Could run the diffing logic with 'key' and 'fileid' present and then strip them later if the user doesn't want to see them.
                exit(1)

        # Generate output for HEAD and worktree
        output_head     = inspect_output_tsv(columns, args.sortcol, args.fileid, git_ref='HEAD')
        output_worktree = inspect_output_tsv(columns, args.sortcol, args.fileid, git_ref=None)

        lines_head     = output_head.split('\n')
        lines_worktree = output_worktree.split('\n')

        def get_lineid(line: str) -> str: # Return tuple of (lineid, line) || lineid tells us which lines to compare.
            
            parts = line.split('\t')

            assert 'key' in columns and 'fileid' in columns, f"Programmer error. We should be checking this condition above."
            lineid = parts[columns.index('key')] + parts[columns.index('fileid')] # We need both the file and key to identify a line, sine the keys can be duplicate across .xcstrings files.
            
            return lineid

        head_map = {}
        for line in lines_head[1:]:  # Skip header
            head_map[get_lineid(line)] = line

        worktree_map = {}
        for line in lines_worktree[1:]:  # Skip header
            worktree_map[get_lineid(line)] = line

        # Find changes
        all_lineids = set(head_map.keys()) | set(worktree_map.keys())
        worktree_has_changes = False

        row_counter = 0
        for fk in sorted(all_lineids):
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

            worktree_has_changes = True

            if args.pretty:
                # Human-readable output with colors
                new_parts = new_line.split('\t') if new_line else []
                old_parts = old_line.split('\t') if old_line else []

                if old_line is None:    print_row_pretty(row_counter, columns, new_parts, grep_pattern, diff_prefix=f"{GREEN}+") # Added - show all green
                elif new_line is None:  print_row_pretty(row_counter, columns, old_parts, grep_pattern, diff_prefix=f"{RED}-")   # Removed - show all red
                else:                   print_row_pretty(row_counter, columns, new_parts, grep_pattern, old_row_values=old_parts, diff_prefix="~") # Changed - show diff
                
                row_counter += 1

                print()  # Blank line between entries
            else:
                # Machine-readable TSV diff output
                # Format: +/-/~ <TAB> fileid <TAB> key <TAB> col1 <TAB> col2 ...
                if old_line is None:    print(f"+\t{new_line}")
                elif new_line is None:  print(f"-\t{old_line}")
                else:
                    print(f"-\t{old_line}")
                    print(f"+\t{new_line}")

        if not worktree_has_changes:
            if args.pretty:
                print("No changes.")
            exit(0)
        else:
            exit(1)


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
    parts = args.path.split('/')
    if len(parts) != 3:
        print(f"Error: Invalid path format: '{args.path}'. Expected 'fileid/key/locale'.")
        exit(1)
    fileid, key, locale = parts

    # Find the xcstrings file
    file_path = find_xcstrings__ids_to_paths().get(fileid, None)
    if not file_path:
        print(f"Error: No .xcstrings file found with fileid '{fileid}'")
        print("Use './run mfstrings list-files' to see available fileids.")
        exit(1)

    # Parse the key (handle >variant suffix for pluralizable keys. Example: some.key>other)
    base_key, variant = '', ''
    if '>' in key: base_key, variant = key.rsplit('>', 1)
    else:          base_key, variant = key, None

    # Load the xcstrings file
    xcstrings_obj = json.loads(Path(file_path).read_text())

    # Find the string
    if base_key not in mfkeypath(xcstrings_obj, f"strings"):
        print(f"Error: Key '{base_key}' not found in {fileid}")
        exit(1)
    # Handle pluralizable vs regular strings
    if not variant: # Regular (non-pluralizable) string
        
        if is_pluralizable_string(mfkeypath(xcstrings_obj, f"strings")):
            print(f"Error: Key '{base_key}' is a pluralizable string. Please specify a variant using '{base_key}>one', '{base_key}>other', etc.")
            exit(1)

        # Apply edits 
        if args.value is not None:
            mfkeypath(
                xcstrings_obj, 
                f"strings/{base_key}/localizations/{locale}/stringUnit/value", 
                set_to=unescape_cell(args.value),  # (unescape \n, \t, \r to match inspect output format)
                create_intermediates=True
            )
            
        if args.state:
            mfkeypath(
                xcstrings_obj, 
                f"strings/{base_key}/localizations/{locale}/stringUnit/state",
                set_to=args.state,
                create_intermediates=True
            )

        print(f"Updated {fileid}/{base_key} [{locale}]")

    else: # Pluralizable string - edit a specific variant
        
        # Check if this string is actually pluralizable
        if not is_pluralizable_string(mfkeypath(xcstrings_obj, f"strings/{base_key}")):
            print(f"Error: Key '{base_key}' is not a pluralizable string, but variant '{variant}' was specified.")
            exit(1)

        # Ensure the structure exists for this locale
        # Structure: localizations/<locale>/substitutions/pluralizable/variations/plural/<variant>/stringUnit
        
        mfkeypath(
            xcstrings_obj, 
            f"strings/{base_key}/localizations/{locale}/stringUnit", 
            set_to={'state': 'translated', 'value': '%#@pluralizable@'}, 
            create_intermediates=True
        )
        mfkeypath(
            xcstrings_obj, 
            f"strings/{base_key}/localizations/{locale}/substitutions/pluralizable",
            set_to={'formatSpecifier': 'd', 'variations': {'plural': {}}},
            create_intermediates=True
        )

        if args.value is not None:
            mfkeypath(
                xcstrings_obj, 
                f"strings/{base_key}/localizations/{locale}/substitutions/pluralizable/variations/plural/{variant}/stringUnit/value",
                set_to=unescape_cell(args.value), # (unescape \n, \t, \r to match inspect output format)
                create_intermediates=True
            )
        if args.state:
            mfkeypath(
                xcstrings_obj, 
                f"strings/{base_key}/localizations/{locale}/substitutions/pluralizable/variations/plural/{variant}/stringUnit/state",
                set_to=args.state,
                create_intermediates=True
            )

        print(f"Updated {fileid}/{base_key}>{variant} [{locale}]")


    # Write the file back (using mfutils to match Xcode's JSON formatting)
    mfutils.write_xcstrings_file(file_path, xcstrings_obj)

    # Print what was changed (show escaped form for consistency with inspect)
    if args.value is not None:
        print(f"  value: {escape_cell(unescape_cell(args.value))}")
    if args.state:
        print(f"  state: {args.state}")

def cmd_list_files(_args):
    
    # Find files
    xcstrings__ids_to_paths = find_xcstrings__ids_to_paths()
    if not xcstrings__ids_to_paths:
        print("No .xcstrings files found.")
        return

    # Find number of strings in each file
    xcstrings__ids_to_countstrs = {}
    if 1:
        xcstrings__ids_to_counts = {}
        xcstrings__paths_to_objs = load_xcstrings__paths_to_objs(list(xcstrings__ids_to_paths.values()))
        for fileid in xcstrings__ids_to_paths:
            xcstrings_obj = xcstrings__paths_to_objs[xcstrings__ids_to_paths[fileid]]
            for key in mfkeypath(xcstrings_obj, 'strings'):
                if mfkeypath(xcstrings_obj, f"strings/{key}/shouldTranslate") == False: continue
                xcstrings__ids_to_counts[fileid] = xcstrings__ids_to_counts.get(fileid, 0) + 1
        
        xcstrings__ids_to_countstrs = {fileid: f"{mfkeypath(xcstrings__ids_to_counts, fileid)} strings" for fileid in xcstrings__ids_to_counts.keys()}


    # Get ljust args
    max_id_len          = max(len(fileid) for fileid in xcstrings__ids_to_paths.keys())
    max_countstr_len    = max(len(x) for x in xcstrings__ids_to_countstrs.values())

    # Print result
    print(f"Found {len(xcstrings__ids_to_paths)} .xcstrings file(s):\n")
    for fileid in xcstrings__ids_to_countstrs: # Using xcstrings__ids_to_countstrs filters the files with count 0
        path = xcstrings__ids_to_paths[fileid]
        countstr = xcstrings__ids_to_countstrs[fileid]
        print(f"  {fileid.ljust(max_id_len)} {countstr.rjust(max_countstr_len)}  {os.path.normpath(path)}")


def cmd_list_cols(_args):

    xcstrings_paths = list(find_xcstrings__ids_to_paths().values())
    xcstrings_objs  = list(load_xcstrings__paths_to_objs(xcstrings_paths).values())
    locales         = xcstrings_locales(xcstrings_objs)
    columns         = available_columns_for_locales(locales)

    for col in columns:
        print(f"{col}")
    

def cmd_delete_locale(args):
    """Delete all translations for a specific locale from all .xcstrings files."""

    locale = args.locale

    # Get all files first (needed for both safety check and processing)
    xcstrings__ids_to_paths = find_xcstrings__ids_to_paths()

    # Safety check: abort if any .xcstrings files have uncommitted changes
    
    repo_root = repo_root_for_path(path)
    
    dirty_files = []
    for id in xcstrings__ids_to_paths:
        is_dirty = mfutils.runclt(f'git diff HEAD --name-only -- "{os.path.relpath(path, repo_root)}"', cwd=repo_root) # Check if file has changes (staged or unstaged)
        if is_dirty: dirty_files.append(xcstrings__ids_to_paths[id])
    
    if dirty_files:
        print("Error: Cannot delete locale while .xcstrings files have uncommitted changes.")
        print(f"Dirty files: [\n    {'\n    '.join([os.path.normpath(p) for p in dirty_files])}\n]")
        print("\nCommit or stash your changes first.")
        exit(1)

    # Validate locale exists
    xcstrings__ids_to_paths     = find_xcstrings__ids_to_paths()
    xcstrings__paths_to_objs    = load_xcstrings__paths_to_objs(list(xcstrings__ids_to_paths.values()))
    locales                     = xcstrings_locales(list(xcstrings__paths_to_objs.values()))
    
    if locale not in locales:
        print(f"Error: Locale '{locale}' not found in any .xcstrings file.")
        print(f"Available locales: {', '.join(sorted(locales))}")
        exit(1)

    if locale == 'en':
        print("Error: Cannot delete the source locale 'en'.")
        exit(1)
    total_deleted = 0

    for fileid, path in xcstrings__ids_to_paths.items():
        content = xcstrings__paths_to_objs[path]

        strings = content.get('strings', {})
        file_deleted = 0

        for key, string_info in strings.items():
            localizations = string_info.get('localizations', {})
            if locale in localizations:
                del localizations[locale]
                file_deleted += 1

        if file_deleted > 0:
            mfutils.write_xcstrings_file(path, content)
            print(f"  {fileid}: deleted {file_deleted} entries")
            total_deleted += file_deleted

    if total_deleted > 0:
        print(f"\nDeleted {total_deleted} '{locale}' entries across {len(xcstrings__ids_to_paths)} files.")
    else:
        print(f"No '{locale}' entries found.")


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
            inspect_parser = subparsers.add_parser('inspect', help='Inspect string units from .xcstrings files (TSV output)')
            inspect_parser.add_argument('--fileid', type=str, required=True, help='File ID to inspect (e.g., "Localizable", "Main"). Use "all" to inspect all files. Run "./run mfstrings list-files" to see available file IDs.')
            inspect_parser.add_argument('--cols', type=str, required=True, help='Comma-separated list of columns to show, in order (e.g., "state:tr,fileid,key,en,tr"). Use "all" to include all available columns. Cells in the state:LOCALE columns are either "translated" or "needs_review".')
            inspect_parser.add_argument('--sortcol', type=str, required=True, help='Column to sort the table by. This column must also be passed to --cols.')
            inspect_parser.add_argument('--diff', action='store_true', help='Show diff between HEAD and current worktree')
            inspect_parser.add_argument('--pretty', action='store_true', help='Human-readable output')
            inspect_parser.add_argument('--grep', type=str, help='Filter rows by regex pattern and highlight matches (requires --pretty)')
            inspect_parser.set_defaults(func=cmd_inspect)

            # edit command
            edit_parser = subparsers.add_parser('edit', help='Edit a translation value and/or state')
            edit_parser.add_argument('--path', type=str, required=True, help='Path to the string: "fileid/key/locale". For pluralizable strings, use "fileid/key>variant/locale" (e.g., "Localizable/some.key>one/tr")')
            edit_parser.add_argument('--value', type=str, help='The new translation value')
            edit_parser.add_argument('--state', type=str, help='The new state: "translated" or "needs_review"')
            edit_parser.set_defaults(func=cmd_edit)

            # delete-locale command
            delete_locale_parser = subparsers.add_parser('delete-locale', help='Delete all translations for a locale. Won\'t run if any .xcstrings files have uncomitted changes.[Jan 2026]. Created for \'context debugging\' workflow [Jan 2026]')
            delete_locale_parser.add_argument('locale', type=str, help='The locale code to delete (e.g., "de", "fr", "zh-Hans")')
            delete_locale_parser.set_defaults(func=cmd_delete_locale)

        # Parse and execute
        args = parser.parse_args()

        if args.command is None:
            parser.print_help()
            return

        args.func(args)


if __name__ == '__main__':
    main()
