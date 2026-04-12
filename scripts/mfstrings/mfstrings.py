#!/usr/bin/env python3

"""
    mfstrings.py is a file created and primarily maintained (By Claude)
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import cmp_to_key
import fcntl

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


def find_xcstrings__ids_to_paths(git_refs: dict[str, str] | None = None) -> dict[str, str]:
    """
    Returns {fileid -> path} map

    Args:
        git_refs: If provided, find files as they existed at these git refs.
                  Dict mapping repo roots to commit refs (e.g., {'.': 'abc123'}).

    Note for Claudes: DO NOT SORT the return value unless there is a specific reason to. This returns the 'canonical' order of the the files which groups them into different categories based on their origin.
    """

    # Get all .xcstrings file paths from both mac-mouse-fix and mac-mouse-fix-website repos.
    paths = []
    if 1:
        main_files = mflocales.find_xcstrings_files('.', git_ref=(git_refs or {}).get('.'))
        website_files = mflocales.find_xcstrings_files(website_repo, git_ref=(git_refs or {}).get(website_repo))
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

all_repo_roots = ['.', '../mac-mouse-fix-website']

def parse_commit_spec(commit_spec: str | None) -> dict[str, str]:
    """
    Parse a commit spec like "abc123" or "abc123,def456" into a dict mapping repo roots to commits.

    Each commit is auto-detected to determine which repo it belongs to by checking if it exists
    in each repo. Returns {repo_root: commit} for commits that were found.

    Errors if:
    - A commit doesn't exist in any repo
    - Two commits belong to the same repo
    """

    def fail(msg):
        print(msg)
        exit(1)

    if not commit_spec: return {}

    commits = [c.strip() for c in commit_spec.split(',')]
    result: dict[str, str] = {}

    for commit in commits:
        # Find which repo(s) this commit exists in
        found_repos = []
        for repo_root in all_repo_roots:
            _, returncode, _ = mfutils.runclt(f'git rev-parse --verify {commit}^{{commit}}', cwd=repo_root, manually_handle_errors=True)
            if returncode == 0: found_repos.append(repo_root)

        if len(found_repos) == 0:       fail(f"Error: Commit '{commit}' not found in any repo ({', '.join(all_repo_roots)})")
        if found_repos[0] in result:    fail(f"Error: Multiple commits specified for the same repo '{found_repos[0]}': '{result[found_repos[0]]}' and '{commit}'")
        # If the same commit is found in multiple repos (e.g. HEAD, we just ignore that)

        result[found_repos[0]] = commit

    return result

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

def project_locales():
    development_locale, translation_locales = mflocales.find_xcode_project_locales(mflocales.path_to_xcodeproj['mac-mouse-fix'])
    return [development_locale] + translation_locales

def load_xcstrings__paths_to_objs(xcstrings_paths: list[str], git_refs: dict[str, str] | None = None, skip_missing: bool = False) -> dict[str, dict]:
    """
    Returns {xcstrings_path: xcstrings_obj}

    If git_refs is provided, loads file contents from git refs instead of the working directory.
    git_refs is a dict mapping repo roots to commit refs (e.g., {'.': 'abc123', '../mac-mouse-fix-website': 'def456'}).
    If skip_missing is True, silently skip files that don't exist at the given git_ref (useful when
    comparing across repos where a commit only exists in one repo).
    """

    result: dict[str, dict] = {}

    for path in xcstrings_paths:
        repo_root = repo_root_for_path(path)
        git_ref = git_refs.get(repo_root) if git_refs else None

        if git_ref: # Get file content at a specific git ref using `git show`.
            content_str, returncode, stderr = mfutils.runclt(f'git show {git_ref}:{os.path.relpath(path, repo_root)}', cwd=repo_root, manually_handle_errors=True)
            # Also skip empty content - git can return 0 with empty output for filenames with special chars like [...slug].xcstrings
            if returncode != 0 or not content_str:
                if skip_missing: continue
                raise RuntimeError(f"Failed to load {path} at git ref '{git_ref}': {stderr.strip() if stderr else 'empty content'}")
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
    return bool(mfkeypath(string_info, f"localizations/en/substitutions/pluralizable"))

def get_string_unit_data(string_unit: dict) -> tuple[str, str]:
    """
    Extract state and value from a stringUnit dict.
    Maps raw state to either 'translated' or 'needs_review'. (.xcstrings contain some more states which we all map to needs_review) (Binary state should help with grepping.)
    """

    state = 'translated' if (string_unit.get('state', '') == 'translated') else 'needs_review'
    value = string_unit.get('value', '')
    
    return state, value


def inspect_output_tsv(columns: list[str], sortcol: str, git_refs: dict[str, str] | None = None, row_filters: list[tuple[str, list[str]]] | None = None, skip_missing: bool = False) -> str:
    """
    Generate inspect output as TSV string.

    Args:
        git_refs: If provided, loads file contents from git refs instead of the working directory.
                  Dict mapping repo roots to commit refs (e.g., {'.': 'abc123', '../mac-mouse-fix-website': 'def456'}).
        row_filters: List of (column, values) tuples. Rows must match all filters (AND). Each filter matches if the row's column value is in the values list (OR).
        skip_missing: If True, skip files that don't exist at the given git_refs (useful for cross-repo diffs).
    """
    # Load data
    xcstrings__ids_to_paths = find_xcstrings__ids_to_paths(git_refs=git_refs)
    xcstrings__paths_to_objs = load_xcstrings__paths_to_objs(list(xcstrings__ids_to_paths.values()), git_refs=git_refs, skip_missing=skip_missing)
    locales = project_locales()

    # Determine which locales are being requested (for plural variant union)
    requested_locales = []
    if 1:
        for col in columns:
            if col in locales:
                requested_locales.append(col)
            elif col.startswith('state:'):
                locale = col[6:]  # Remove 'state:' prefix
                if locale in locales and locale not in requested_locales:
                    requested_locales.append(locale)

    # Build all rows first (so we can sort)
    rows: list[dict[str, str]] = []

    for fileid in xcstrings__ids_to_paths:

        # Skip files that weren't loaded (e.g., skipped due to skip_missing)
        if xcstrings__ids_to_paths[fileid] not in xcstrings__paths_to_objs:
            continue

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
                all_variants: set[str] = set()
                for locale in requested_locales:
                    variants_for_locale = mfkeypath(xcstrings_obj, f"strings/{key}/localizations/{locale}/substitutions/pluralizable/variations/plural").keys()
                    assert all(x in mflocales.locales_to_plural_variants[locale] for x in variants_for_locale), f"Unexpected plural variants for {locale}:{key}. Expected: {mflocales.locales_to_plural_variants[locale]}. Found: {variants_for_locale}."
                    all_variants.update(mflocales.locales_to_plural_variants[locale])

                # Create one row per variant
                for variant in all_variants:
                    row_data: dict[str, str] = {
                        'fileid': fileid,
                        'key': f'{key}|==|{variant}',
                        'comment': comment,
                    }

                    # Get values for each locale (including English)
                    for locale in locales:
                        
                        if variant not in mflocales.locales_to_plural_variants[locale]: # This locale doesn't have this variant
                            state, value = '(no pluralization)', '(no pluralization)'
                        else:
                            string_unit = mfkeypath(xcstrings_obj, f"strings/{key}/localizations/{locale}/substitutions/pluralizable/variations/plural/{variant}/stringUnit")
                            state, value = get_string_unit_data(string_unit)

                        if locale == 'en':
                            row_data['en'] = value
                        else:
                            row_data[f'state:{locale}'] = state
                            row_data[locale] = value

                    # Apply row filters (on full row_data, before column filtering)
                    if row_filters:
                        if not all(row_data.get(col, '') in vals for col, vals in row_filters):
                            continue

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

                # Apply row filters (on full row_data, before column filtering)
                if row_filters:
                    if not all(row_data.get(col, '') in vals for col, vals in row_filters):
                        continue

                # Store row data (filter to requested columns)
                filtered_row_data = {col: row_data.get(col, '') for col in columns}
                rows.append(filtered_row_data)

    # Sort
    def mfcmp(a, b):                # Note: Could use mflocales.ordered_plural_variants() to 'properly' sort the plural variants, but doesn't really matter. [Jan 2026]
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
    locales = project_locales()
    all_columns = available_columns_for_locales(locales)

    def print_help_and_exit(err): # TODO: Unify the way we print help / input errors [Jan 2026]
        print(
            f"Invalid args passed to 'mfstrings inspect' command:"
            f"\n"
            f"\n{err}"
            f"\n"
            f"\nUsage: ./run mfstrings inspect --cols <columns> --sortcol <column> [--filter ...] [--pretty] [--diff]"
            f"\n"
            f"\nAvailable columns:"
            f"\n  - {'\n  - '.join(all_columns)}"
            f"\n"
            f"\nExample:"
            f"\n  ./run mfstrings inspect --cols fileid,key,comment,en,state:tr,tr --sortcol key"
            f"\n  ./run mfstrings inspect --cols key,en,tr,state:tr --sortcol key --filter fileid=Localizable"
            f"\n  ./run mfstrings inspect --cols all --sortcol key"
            f"\n"
            f"\n--pretty tries to make the output more human-readable. Without --pretty, the output is a TSV (Tab separated values) table"
            f"\n"
            f"\n--diff shows the diff between HEAD and the current worktree (shorthand for --diff-filter HEAD --diff-highlight HEAD)"
            f"\n"
            f"\n--diff-filter COMMIT only shows strings that changed since COMMIT"
            f"\n--diff-highlight COMMIT compares worktree values against COMMIT for display"
            f"\n  Example: --diff-filter HEAD --diff-highlight abc123"
            f"\n    Shows only strings changed since HEAD, but compares them against the values from abc123"
            f"\n"
            f"\n state:LOCALE columns contain either 'translated' or 'needs_review'."
        )
        exit(1)

    if not xcstrings__paths_to_objs:
        print_help_and_exit("No .xcstrings files found.")

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
            print(f"  ./run mfstrings inspect --cols ... --sortcol ... | grep '{args.grep}'", file=sys.stderr)
            exit(1)
        try:
            grep_pattern = re.compile(args.grep, re.IGNORECASE)
        except re.error as e:
            print(f"Error: Invalid regex pattern '{args.grep}': {e}")
            exit(1)

    # Parse and validate --filter
    row_filters: list[tuple[str, list[str]]] = []
    if args.filters:
        for filter_str in args.filters:
            if '=' not in filter_str:
                print_help_and_exit(f"Invalid filter format: '{filter_str}'. Expected 'COLUMN=VALUE' or 'COLUMN=VAL1,VAL2'.")
            col, values_str = filter_str.split('=', 1)
            if col not in all_columns:
                print_help_and_exit(f"Unknown column in filter: '{col}'")
            values = values_str.split(',')
            row_filters.append((col, values))

    # Validate --at is mutually exclusive with --diff options
    if args.at and (args.diff or args.diff_filter or args.diff_highlight):
        print_help_and_exit("--at cannot be used with --diff, --diff-filter, or --diff-highlight")

    # Normalize diff options: --diff is shorthand for --diff-filter HEAD --diff-highlight HEAD
    if args.diff:
        if args.diff_filter is None:
            args.diff_filter = 'HEAD'
        if args.diff_highlight is None:
            args.diff_highlight = 'HEAD'

    # Parse commit specs into per-repo dicts
    at_refs = parse_commit_spec(args.at)
    diff_filter_refs = parse_commit_spec(args.diff_filter)
    diff_highlight_refs = parse_commit_spec(args.diff_highlight)

    # Print the output

    if not diff_filter_refs and not diff_highlight_refs: # Normal (non-diff) output

        output = inspect_output_tsv(columns, args.sortcol, row_filters=row_filters, git_refs=at_refs)

        if not args.pretty:
            print(output)
        else:
            lines = output.split('\n')
            row_counter = 1
            for line in lines[1:]:  # Skip header
                # Filter by grep pattern if provided
                if grep_pattern and not grep_pattern.search(line):
                    continue

                parts = line.split('\t')
                print_row_pretty(row_counter, columns, parts, grep_pattern)
                row_counter += 1
                print()  # Blank line between entries

    else: # Diff output (--diff, --diff-filter, and/or --diff-highlight)

        # Validate --cols
        if 'key' not in columns or 'fileid' not in columns:
            print(f"Error: Diff mode needs key and fileid columns to be present.") # Improvement idea: Could run the diffing logic with 'key' and 'fileid' present and then strip them later if the user doesn't want to see them.
            exit(1)

        # Generate output for filter ref, highlight ref, and worktree
        #   - filter_refs: Used to determine which rows changed (rows where filter_ref != worktree are shown). If empty, all rows are shown.
        #   - highlight_refs: Used for displaying the "old" values in diff output (optional, defaults to filter_refs)
        #   - skip_missing=True: Skip files that don't exist at the git ref (e.g., newly added .xcstrings files)
        # TODO: [Apr 2026] Currently file discovery happens separately for each call (worktree vs git_refs).
        #   This means deleted files won't show in diff output. To fix, we'd need to form a union of files
        #   from both worktree and old commits, then pass that unified file list to each inspect_output_tsv call.
        output_filter_ref    = inspect_output_tsv(columns, args.sortcol, git_refs=diff_filter_refs, row_filters=row_filters, skip_missing=True) if diff_filter_refs else None
        output_worktree      = inspect_output_tsv(columns, args.sortcol, row_filters=row_filters)
        output_highlight_ref = inspect_output_tsv(columns, args.sortcol, git_refs=diff_highlight_refs, skip_missing=True) if diff_highlight_refs and diff_highlight_refs != diff_filter_refs else None  # No row_filters: highlight ref is for display only, filters apply to worktree

        lines_filter_ref    = output_filter_ref.split('\n') if output_filter_ref else None
        lines_worktree      = output_worktree.split('\n')
        lines_highlight_ref = output_highlight_ref.split('\n') if output_highlight_ref else None

        def get_lineid(line: str) -> str: # lineid tells us which lines to compare for the diff.
            parts = line.split('\t')
            assert 'key' in columns and 'fileid' in columns, f"Programmer error. We should be checking this condition above."
            lineid = parts[columns.index('key')] + parts[columns.index('fileid')] # We need both the file and key to identify a line, since the keys can be duplicate across .xcstrings files.
            return lineid

        filter_ref_map = {}
        if lines_filter_ref:
            for line in lines_filter_ref[1:]:  # Skip header
                filter_ref_map[get_lineid(line)] = line

        worktree_map = {}
        for line in lines_worktree[1:]:  # Skip header
            worktree_map[get_lineid(line)] = line

        highlight_ref_map = {}
        if lines_highlight_ref:
            for line in lines_highlight_ref[1:]:  # Skip header
                highlight_ref_map[get_lineid(line)] = line

        worktree_has_changes = False

        row_counter = 1
        for fk in worktree_map.keys():
            filter_line = filter_ref_map.get(fk) if diff_filter_refs else None  # None means "no filter ref" (show all rows)
            new_line = worktree_map.get(fk)

            # Use filter_ref to determine if row changed - skip unchanged rows (only when filtering is enabled)
            if diff_filter_refs and filter_line == new_line:
                continue

            # Use highlight_ref for display (falls back to filter_ref if not specified)
            highlight_line = highlight_ref_map.get(fk) if highlight_ref_map else filter_line

            # Filter by grep pattern if provided
            if grep_pattern:
                highlight_matches = highlight_line and grep_pattern.search(highlight_line)
                new_matches = new_line and grep_pattern.search(new_line)
                if not highlight_matches and not new_matches:
                    continue

            worktree_has_changes = True

            if args.pretty:
                # Human-readable output with colors
                new_parts = new_line.split('\t') if new_line else []
                highlight_parts = highlight_line.split('\t') if highlight_line else []

                if   diff_filter_refs and filter_line is None:  print_row_pretty(row_counter, columns, new_parts, grep_pattern, diff_prefix=f"{GREEN}+") # Added (since filter_ref)
                elif diff_filter_refs and new_line is None:     print_row_pretty(row_counter, columns, highlight_parts, grep_pattern, diff_prefix=f"{RED}-")   # Removed (since filter_ref)
                else:                                           print_row_pretty(row_counter, columns, new_parts, grep_pattern, old_row_values=highlight_parts, diff_prefix="~" if diff_filter_refs else "") # Changed (or just highlighting without filter)

                row_counter += 1
                print()  # Blank line between entries
            else:
                # Machine-readable TSV diff output
                # Format: +/-/~ <TAB> fileid <TAB> key <TAB> col1 <TAB> col2 ...
                if   diff_filter_refs and filter_line is None:  print(f"+\t{new_line}")
                elif diff_filter_refs and new_line is None:     print(f"-\t{highlight_line}")
                else:
                    if diff_filter_refs:
                        print(f"-\t{highlight_line}")
                        print(f"+\t{new_line}")
                    else:
                        # Highlight-only mode: just show the new line (highlighting is only visible in --pretty)
                        print(new_line)

        if diff_filter_refs and not worktree_has_changes:
            if args.pretty:
                print("No changes.")
            exit(0)
        elif diff_filter_refs:
            exit(1)


def cmd_edit(args):
    """Edit a string's translation value and/or state in an .xcstrings file."""

    # Validate arguments
    if args.value is None and not args.state: # Caution: Don't use args.value as a boolean – that will silently ignore '' (emptystring) [Jan 2026]
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

    # Parse the key (handle |==|VARIANT suffix for pluralizable keys. Example: some.key|==|other)
    base_key, variant = '', ''
    if '|==|' in key: base_key, variant = key.rsplit('|==|', 1)
    else:          base_key, variant = key, None

    # Validate the plural variant
    if variant and variant not in mflocales.locales_to_plural_variants[locale]:
        print(f"Error: Invalid plural variant '{variant}'. Plural variants for locale '{locale}': {mflocales.locales_to_plural_variants[locale]}")
        exit(1)

    with open(file_path, 'r') as fd:

        # Lock the xcstrings file
        #   (Avoids file-corruption when multiple Claudes work on different languages.)
        fcntl.flock(fd, fcntl.LOCK_EX) # Automatically unlocked when the file is closed (I think) [Jan 2026]

        # Load the xcstrings file
        xcstrings_obj = json.loads(Path(file_path).read_text())

        # Find the string
        if base_key not in mfkeypath(xcstrings_obj, f"strings"):
            print(f"Error: Key '{base_key}' not found in {fileid}")
            exit(1)
        
        # Find/create stringUnit to edit
        stringUnit = {}
        if not variant: # Regular (non-pluralizable) string
            
            if is_pluralizable_string(mfkeypath(xcstrings_obj, f"strings/{base_key}")):
                print(f"Error: Key '{base_key}' is a pluralizable string. Please specify a variant using '{base_key}|==|one', '{base_key}|==|other', etc.")
                exit(1)

            stringUnit = mfkeypath(xcstrings_obj, f"strings/{base_key}/localizations/{locale}/stringUnit", default={}, create_intermediates=True)

        else: # Pluralizable string - edit a specific variant
            
            # Check if this string is actually pluralizable
            if not is_pluralizable_string(mfkeypath(xcstrings_obj, f"strings/{base_key}")):
                print(f"Error: Key '{base_key}' is not a pluralizable string, but variant '{variant}' was specified.")
                exit(1)

            # Ensure the structure exists for this locale
            mfkeypath(
                xcstrings_obj, 
                f"strings/{base_key}/localizations/{locale}/stringUnit", 
                default={'state': 'translated', 'value': '%#@pluralizable@'},       # Using %#@pluralizable@ everywhere and not having the pluralizable base-strings be editable is an MMF-specific convention. [Jan 2026] The mf-xcloc-editor Readme.md explains why I think this is a good choice. Maybe wrote about this in other places too [Jan 2026]
                create_intermediates=True
            )
            mfkeypath(
                xcstrings_obj, 
                f"strings/{base_key}/localizations/{locale}/substitutions/pluralizable",
                default={'formatSpecifier': 'd'},
                create_intermediates=True
            )

            # Get the stringUnit
            stringUnit = mfkeypath(
                xcstrings_obj,
                f"strings/{base_key}/localizations/{locale}/substitutions/pluralizable/variations/plural/{variant}/stringUnit",
                default={},
                create_intermediates=True
            )

        # Init/edit the stringUnit
        stringUnit['state'] = args.state if args.state else stringUnit.get('state', 'new')
        stringUnit['value'] = unescape_cell(args.value) if args.value is not None else stringUnit.get('value', '')

        # Write the file back
        mfutils.write_xcstrings_file(file_path, xcstrings_obj)

        # Print feedback
        if (0): # Disabling printing because: - Context pollution (?) - Claude can just use `mfstrings inspect` to check his work.
            print(f"Updated {key} [{locale}]")

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

    # Get ljust args
    max_id_len = max(len(fileid) for fileid in xcstrings__ids_to_paths.keys())

    # Print result
    print(f"Found {len(xcstrings__ids_to_paths)} .xcstrings file(s):\n")
    for fileid, path in xcstrings__ids_to_paths.items():
        print(f"  {fileid.ljust(max_id_len)}  ({os.path.normpath(path)})")


def cmd_list_cols(_args):

    locales         = project_locales()
    columns         = available_columns_for_locales(locales)

    for col in columns:
        print(f"{col}")


def cmd_progress(args):
    """Show translation progress as a table (files × locales)."""

    @dataclass
    class ProgressData:
        """Progress data computed for a set of files and locales."""
        per_file_locale: dict[str, dict[str, dict]]  # {fileid: {locale: {translated, to_translate, percentage}}}
        string_counts: dict[str, int]                 # {fileid: count}
        totals_per_locale: dict[str, dict]            # {locale: {translated, to_translate, percentage}}
        totals_per_file: dict[str, dict]              # {fileid: {translated, to_translate, percentage}}
        grand_translated: int
        grand_to_translate: int

        @property
        def grand_percentage(self) -> float:
            return self.grand_translated / self.grand_to_translate if self.grand_to_translate > 0 else 0.0
    
    def compute_progress_data(xcstrings__ids_to_paths: dict[str, str], translation_locales: list[str], git_refs: dict[str, str] | None = None) -> ProgressData:
        """Compute translation progress for given files and locales."""

        xcstrings__paths_to_objs = load_xcstrings__paths_to_objs(list(xcstrings__ids_to_paths.values()), git_refs=git_refs)

        per_file_locale: dict[str, dict[str, dict]] = {}
        string_counts: dict[str, int] = {}

        for fileid, path in xcstrings__ids_to_paths.items():
            xcstrings_obj = xcstrings__paths_to_objs[path]

            # Skip files with no translatable strings
            string_count = sum(1 for key in mfkeypath(xcstrings_obj, 'strings')
                            if mfkeypath(xcstrings_obj, f'strings/{key}/shouldTranslate') != False)
            if string_count == 0:
                continue

            string_counts[fileid] = string_count
            file_progress = mflocales.get_localization_progress([xcstrings_obj], translation_locales)
            per_file_locale[fileid] = file_progress

        # Compute totals per locale
        totals_per_locale: dict[str, dict] = {}
        for locale in translation_locales:
            total_translated = sum(per_file_locale[fid][locale]['translated'] for fid in per_file_locale)
            total_to_translate = sum(per_file_locale[fid][locale]['to_translate'] for fid in per_file_locale)
            totals_per_locale[locale] = {
                'translated': total_translated,
                'to_translate': total_to_translate,
                'percentage': total_translated / total_to_translate if total_to_translate > 0 else 0.0
            }

        # Compute totals per file
        totals_per_file: dict[str, dict] = {}
        for fileid in per_file_locale:
            total_translated = sum(per_file_locale[fileid][loc]['translated'] for loc in translation_locales)
            total_to_translate = sum(per_file_locale[fileid][loc]['to_translate'] for loc in translation_locales)
            totals_per_file[fileid] = {
                'translated': total_translated,
                'to_translate': total_to_translate,
                'percentage': total_translated / total_to_translate if total_to_translate > 0 else 0.0
            }

        # Compute grand totals
        grand_translated = sum(totals_per_locale[loc]['translated'] for loc in translation_locales)
        grand_to_translate = sum(totals_per_locale[loc]['to_translate'] for loc in translation_locales)

        return ProgressData(
            per_file_locale=per_file_locale,
            string_counts=string_counts,
            totals_per_locale=totals_per_locale,
            totals_per_file=totals_per_file,
            grand_translated=grand_translated,
            grand_to_translate=grand_to_translate
        )


    # Load file paths and locales
    xcstrings__ids_to_paths = find_xcstrings__ids_to_paths()
    development_locale, translation_locales = mflocales.find_xcode_project_locales(mflocales.path_to_xcodeproj['mac-mouse-fix'])

    # Filter locales
    if args.locales != 'all':
        requested_locales = args.locales.split(',')
        invalid_locales = [l for l in requested_locales if l not in translation_locales]
        if invalid_locales:
            print(f"Error: Unknown locale(s): {', '.join(invalid_locales)}")
            print(f"Available locales: {', '.join(translation_locales)}")  # Note for Claudes: DO NOT SORT the output of mflocales functions. Assume they return the 'canonical' order of things.
            exit(1)
        translation_locales = requested_locales

    # Filter files
    if args.files != 'all':
        requested_files = args.files.split(',')
        invalid_files = [f for f in requested_files if f not in xcstrings__ids_to_paths]
        if invalid_files:
            print(f"Error: Unknown file ID(s): {', '.join(invalid_files)}")
            print(f"Available file IDs: {', '.join(xcstrings__ids_to_paths.keys())}")
            exit(1)
        xcstrings__ids_to_paths = {f: xcstrings__ids_to_paths[f] for f in requested_files}

    # Compute progress
    data = compute_progress_data(xcstrings__ids_to_paths, translation_locales)

    # Format helpers
    def fmt_pct(pct: float) -> str:
        if pct == 1.0:
            return '100%'
        elif pct == 0.0:
            return '0%'
        else:
            return f'{pct * 100:.0f}%'

    def fmt_diff(diff: int) -> str:
        if diff > 0:
            return f'+{diff}'
        else:
            return str(diff)

    sorted_fileids = data.per_file_locale.keys()
    total_strings = sum(data.string_counts.values())
    columns = ['fileid', 'strings'] + translation_locales + ['total']

    if args.diff:
        # Diff mode: compare HEAD vs worktree
        head = compute_progress_data(xcstrings__ids_to_paths, translation_locales, git_refs=parse_commit_spec('HEAD'))

        # Format before→after (with optional color for pretty mode)
        def fmt_change(old: int, new: int, color: bool = False) -> str:
            if old == new:
                return str(new)
            if color:
                if new > old:
                    return f'{GREEN}{old}→{new}{RESET}'
                else:
                    return f'{RED}{old}→{new}{RESET}'
            return f'{old}→{new}'

        if not args.pretty:
            print('\t'.join(columns))
            for fileid in sorted_fileids:
                row = [fileid, str(data.string_counts[fileid])]
                for locale in translation_locales:
                    old = head.per_file_locale.get(fileid, {}).get(locale, {}).get('translated', 0)
                    new = data.per_file_locale[fileid][locale]['translated']
                    row.append(fmt_change(old, new))
                old_total = head.totals_per_file.get(fileid, {}).get('translated', 0)
                new_total = data.totals_per_file[fileid]['translated']
                row.append(fmt_change(old_total, new_total))
                print('\t'.join(row))
            totals_row = ['TOTAL', str(total_strings)]
            for locale in translation_locales:
                old = head.totals_per_locale.get(locale, {}).get('translated', 0)
                new = data.totals_per_locale[locale]['translated']
                totals_row.append(fmt_change(old, new))
            totals_row.append(fmt_change(head.grand_translated, data.grand_translated))
            print('\t'.join(totals_row))
        else:
            # Compute max width needed for before→after values (without color codes)
            max_change_len = max(5, max(len(loc) for loc in translation_locales))
            for fileid in sorted_fileids:
                for locale in translation_locales:
                    old = head.per_file_locale.get(fileid, {}).get(locale, {}).get('translated', 0)
                    new = data.per_file_locale[fileid][locale]['translated']
                    max_change_len = max(max_change_len, len(fmt_change(old, new)))
                old_total = head.totals_per_file.get(fileid, {}).get('translated', 0)
                new_total = data.totals_per_file[fileid]['translated']
                max_change_len = max(max_change_len, len(fmt_change(old_total, new_total)))

            file_col_width = max(len('fileid'), max(len(fid) for fid in sorted_fileids), len('TOTAL'))
            strings_col_width = max(len('strings'), len(str(total_strings)))
            locale_col_width = max_change_len

            header = f"{'fileid'.ljust(file_col_width)}  {'strings'.rjust(strings_col_width)}"
            for locale in translation_locales:
                header += f"  {locale.rjust(locale_col_width)}"
            header += f"  {'total'.rjust(locale_col_width)}"
            print(header)
            print('-' * len(header))

            for fileid in sorted_fileids:
                row = f"{fileid.ljust(file_col_width)}  {str(data.string_counts[fileid]).rjust(strings_col_width)}"
                for locale in translation_locales:
                    old = head.per_file_locale.get(fileid, {}).get(locale, {}).get('translated', 0)
                    new = data.per_file_locale[fileid][locale]['translated']
                    # Pad without color, then add color
                    padded = fmt_change(old, new).rjust(locale_col_width)
                    colored = fmt_change(old, new, color=True)
                    # Replace plain text with colored version in padded string
                    row += f"  {padded.replace(fmt_change(old, new), colored)}"
                old_total = head.totals_per_file.get(fileid, {}).get('translated', 0)
                new_total = data.totals_per_file[fileid]['translated']
                padded = fmt_change(old_total, new_total).rjust(locale_col_width)
                colored = fmt_change(old_total, new_total, color=True)
                row += f"  {padded.replace(fmt_change(old_total, new_total), colored)}"
                print(row)

            print('-' * len(header))
            totals_row = f"{'TOTAL'.ljust(file_col_width)}  {str(total_strings).rjust(strings_col_width)}"
            for locale in translation_locales:
                old = head.totals_per_locale.get(locale, {}).get('translated', 0)
                new = data.totals_per_locale[locale]['translated']
                padded = fmt_change(old, new).rjust(locale_col_width)
                colored = fmt_change(old, new, color=True)
                totals_row += f"  {padded.replace(fmt_change(old, new), colored)}"
            old_grand = head.grand_translated
            new_grand = data.grand_translated
            padded = fmt_change(old_grand, new_grand).rjust(locale_col_width)
            colored = fmt_change(old_grand, new_grand, color=True)
            totals_row += f"  {padded.replace(fmt_change(old_grand, new_grand), colored)}"
            print(totals_row)

            print()
            grand_diff = data.grand_translated - head.grand_translated
            diff_colored = f'{GREEN}+{grand_diff}{RESET}' if grand_diff > 0 else f'{RED}{grand_diff}{RESET}' if grand_diff < 0 else '0'
            print(f"Change: {diff_colored} strings ({data.grand_translated}/{data.grand_to_translate} total)")

    elif not args.pretty:
        print('\t'.join(columns))
        for fileid in sorted_fileids:
            row = [fileid, str(data.string_counts[fileid])]
            for locale in translation_locales:
                row.append(str(data.per_file_locale[fileid][locale]['translated']))
            row.append(str(data.totals_per_file[fileid]['translated']))
            print('\t'.join(row))
        totals_row = ['TOTAL', str(total_strings)]
        for locale in translation_locales:
            totals_row.append(str(data.totals_per_locale[locale]['translated']))
        totals_row.append(str(data.grand_translated))
        print('\t'.join(totals_row))

    else:
        file_col_width = max(len('fileid'), max(len(fid) for fid in sorted_fileids), len('TOTAL'))
        strings_col_width = max(len('strings'), len(str(total_strings)))
        locale_col_width = max(5, max(len(loc) for loc in translation_locales))

        header = f"{'fileid'.ljust(file_col_width)}  {'strings'.rjust(strings_col_width)}"
        for locale in translation_locales:
            header += f"  {locale.rjust(locale_col_width)}"
        header += f"  {'total'.rjust(locale_col_width)}"
        print(header)
        print('-' * len(header))

        for fileid in sorted_fileids:
            row = f"{fileid.ljust(file_col_width)}  {str(data.string_counts[fileid]).rjust(strings_col_width)}"
            for locale in translation_locales:
                row += f"  {str(data.per_file_locale[fileid][locale]['translated']).rjust(locale_col_width)}"
            row += f"  {str(data.totals_per_file[fileid]['translated']).rjust(locale_col_width)}"
            print(row)

        print('-' * len(header))
        totals_row = f"{'TOTAL'.ljust(file_col_width)}  {str(total_strings).rjust(strings_col_width)}"
        for locale in translation_locales:
            totals_row += f"  {str(data.totals_per_locale[locale]['translated']).rjust(locale_col_width)}"
        totals_row += f"  {str(data.grand_translated).rjust(locale_col_width)}"
        print(totals_row)

        print()
        print(f"Overall: {data.grand_translated}/{data.grand_to_translate} strings translated ({fmt_pct(data.grand_percentage)})")


def cmd_bulk_edit(args):
    """Bulk edit translations for a specific locale across all .xcstrings files."""

    locale = args.locale
    action = args.action

    # Get all files first (needed for both safety check and processing)
    xcstrings__ids_to_paths = find_xcstrings__ids_to_paths()

    # Safety check: abort if any .xcstrings files have uncommitted changes
    dirty_files = []
    for fileid, path in xcstrings__ids_to_paths.items():
        repo_root = repo_root_for_path(path)
        is_dirty = mfutils.runclt(f'git diff HEAD --name-only -- "{os.path.relpath(path, repo_root)}"', cwd=repo_root)
        if is_dirty:
            dirty_files.append(path)

    if dirty_files and not args.force:
        print(f"Error: Cannot run bulk-edit while .xcstrings files have uncommitted changes.")
        print(f"Dirty files: [\n    {'\n    '.join([os.path.normpath(p) for p in dirty_files])}\n]")
        print("\nCommit or stash your changes first, or use --force to skip this check.")
        exit(1)

    # Load file contents
    xcstrings__paths_to_objs = load_xcstrings__paths_to_objs(list(xcstrings__ids_to_paths.values()))
    xcstrings__paths_to_head_objs = load_xcstrings__paths_to_objs(list(xcstrings__ids_to_paths.values()), git_refs=parse_commit_spec('HEAD')) if action == 'sync-state-with-diff' else None

    # Validate locale exists
    locales = project_locales()

    if locale not in locales:
        print(f"Error: Locale '{locale}' not found in project.")
        print(f"Available locales: {', '.join(locales)}")
        exit(1)

    if locale == 'en':
        print("Error: Cannot bulk-edit the source locale 'en'.")
        exit(1)

    total_modified = 0

    for fileid, path in xcstrings__ids_to_paths.items():
        content = xcstrings__paths_to_objs[path]
        file_modified = 0

        for key in mfkeypath(content, 'strings'):
            localizations = mfkeypath(content, f'strings/{key}/localizations')

            if locale not in localizations:
                continue

            if action == 'delete':
                del localizations[locale]
                file_modified += 1

            elif action == 'sync-state-with-diff':
                head_content = xcstrings__paths_to_head_objs[path]

                # Regular strings
                head_value = mfkeypath(head_content, f'strings/{key}/localizations/{locale}/stringUnit/value')
                worktree_value = mfkeypath(content, f'strings/{key}/localizations/{locale}/stringUnit/value')
                if worktree_value:
                    new_state = 'needs_review' if worktree_value != head_value else 'translated'
                    mfkeypath(content, f'strings/{key}/localizations/{locale}/stringUnit')['state'] = new_state
                    file_modified += 1

                # Pluralizable strings
                for variant in mfkeypath(content, f'strings/{key}/localizations/{locale}/substitutions/pluralizable/variations/plural'):
                    head_variant_value     = mfkeypath(head_content, f'strings/{key}/localizations/{locale}/substitutions/pluralizable/variations/plural/{variant}/stringUnit/value')
                    worktree_variant_value = mfkeypath(content,      f'strings/{key}/localizations/{locale}/substitutions/pluralizable/variations/plural/{variant}/stringUnit/value')
                    if worktree_variant_value:
                        new_state = 'needs_review' if worktree_variant_value != head_variant_value else 'translated'
                        mfkeypath(content, f'strings/{key}/localizations/{locale}/substitutions/pluralizable/variations/plural/{variant}/stringUnit')['state'] = new_state
                        file_modified += 1

        if file_modified > 0:
            mfutils.write_xcstrings_file(path, content)
            print(f"  {fileid}: modified {file_modified} entries")
            total_modified += file_modified

    action_verb = {'delete': 'deleted', 'sync-state-with-diff': 'synced state for'}[action]
    if total_modified > 0:
        print(f"\n{action_verb.capitalize()} {total_modified} '{locale}' entries across {len(xcstrings__ids_to_paths)} files.")
    else:
        print(f"No '{locale}' entries found.")


def main():

    r"""
    Discussions:
        - On |==|: [Jan 2026] It's is ugly but greppable (--grep "\|==\|"). It is also used in .xcloc files – Chose it out of familiarity – See mf-xcloc-editor.
    """

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
            inspect_parser.add_argument('--cols', type=str, required=True, help='Comma-separated list of columns to show, in order (e.g., "state:tr,fileid,key,en,tr"). Use "all" to include all available columns. Cells in the state:LOCALE columns are either "translated" or "needs_review".')
            inspect_parser.add_argument('--sortcol', type=str, required=True, help='Column to sort the table by. This column must also be passed to --cols.')
            inspect_parser.add_argument('--diff', action='store_true', help='Show diff between HEAD and current worktree. Shorthand for --diff-filter HEAD --diff-highlight HEAD.')
            inspect_parser.add_argument('--diff-filter', type=str, metavar='COMMIT[,COMMIT]', help='Only show strings that changed since COMMIT (compares COMMIT vs worktree to decide which rows to show). Use comma-separated commits for different repos (auto-detected).')
            inspect_parser.add_argument('--diff-highlight', type=str, metavar='COMMIT[,COMMIT]', help='Compare worktree values against COMMIT (shows character-level diffs in --pretty mode). Use comma-separated commits for different repos (auto-detected).')
            inspect_parser.add_argument('--at', type=str, metavar='COMMIT[,COMMIT]', help='Show strings as they existed at COMMIT (time travel). Mutually exclusive with --diff options. Use comma-separated commits for different repos (auto-detected).') # Usecase for which we created this: Compare zh-HK and zh-Hant at an older commit (human translations) to see if there are any differences.
            inspect_parser.add_argument('--pretty', action='store_true', help='Human-readable output (default is TSV)')
            inspect_parser.add_argument('--grep', type=str, help='Filter rows by regex pattern and highlight matches (requires --pretty)')
            inspect_parser.add_argument('--filter', type=str, action='append', dest='filters', metavar='COLUMN=VALUE', help='Filter rows by exact column value. Use COLUMN=VAL1,VAL2 for OR matching. Multiple --filter args use AND logic. With --diff, filters apply to worktree values only.') # Mostly introduced for 'context debugging' workflow (--filter state:de=translated) but now `--diff-filter HEAD` does the same job but better [Jan 2026] || Update: --filter is now also useful for Claude so he can do `--filter fileid=Localizable` [Jan 2026]
            inspect_parser.set_defaults(func=cmd_inspect)

            # edit command
            edit_parser = subparsers.add_parser('edit', help='Edit a translation value and/or state')
            edit_parser.add_argument('--path', type=str, required=True, help='Path to the string: "fileid/key/locale". For pluralizable strings, use "fileid/key|==|variant/locale" (e.g., "Localizable/some.key|==|one/tr")')
            edit_parser.add_argument('--value', type=str, help='The new translation value')
            edit_parser.add_argument('--state', type=str, help='The new state: "translated" or "needs_review"')
            edit_parser.set_defaults(func=cmd_edit)

            # progress command
            progress_parser = subparsers.add_parser('progress', help='Show translation progress as a table (files × locales)')
            progress_parser.add_argument('--locales', type=str, required=True, help='Comma-separated list of locales to show, or "all" for all locales')
            progress_parser.add_argument('--files', type=str, required=True, help='Comma-separated list of file IDs to show, or "all" for all files')
            progress_parser.add_argument('--diff', action='store_true', help='Show diff between HEAD and current worktree')
            progress_parser.add_argument('--pretty', action='store_true', help='Human-readable output (default is TSV)')
            progress_parser.set_defaults(func=cmd_progress)

            # bulk-edit command
            bulk_edit_parser = subparsers.add_parser('bulk-edit', help='Bulk edit translations for a specific locale across all .xcstrings files. To be used by human in "translation context debugging" workflow.')
            bulk_edit_parser.add_argument('action', type=str, choices=['delete', 'sync-state-with-diff'], help='Action to perform: "delete" removes all translations for the locale, "sync-state-with-diff" sets state to needs_review for changed values')
            bulk_edit_parser.add_argument('--locale', type=str, required=True, help='The locale to edit (e.g., "tr", "de")')
            bulk_edit_parser.add_argument('--force', action='store_true', help='Skip the check for uncommitted changes in .xcstrings files')
            bulk_edit_parser.set_defaults(func=cmd_bulk_edit)

        # Parse and execute
        args = parser.parse_args()

        if args.command is None:
            parser.print_help()
            return

        args.func(args)


if __name__ == '__main__':
    main()
