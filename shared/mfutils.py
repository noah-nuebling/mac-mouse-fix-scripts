"""

utlis.py holds various utility functions 
    of categories that are too small to put into a separate file
    
"""

#
# Imports
#

# pip imports

# stdlib imports  
import tempfile
import subprocess
import os
import textwrap
import json
import random
import shlex
import platform
import re
import hashlib
from pathlib import Path
from typing import Callable

from dataclasses import dataclass
from typing import List, Union, Any

#
# MARK: Other 
# General utility functions that don't belong together
#-

MFKEYPATH_NONE = object()
def mfkeypath(dict, kp, set_to=MFKEYPATH_NONE, default=MFKEYPATH_NONE, create_intermediates=False) -> Any:
    """
    Access nested dicts using slash-separated keypaths like 'a/b/c'.

    Modes:
        mfkeypath(d, 'a/b')              -> Returns d['a']['b'], or {} if path doesn't exist
        mfkeypath(d, 'a/b', set_to=X)    -> Sets d['a']['b'] = X (crashes if 'a' doesn't exist)
        mfkeypath(d, 'a/b', default=X)   -> Returns d['a']['b'] if exists, else sets d['a']['b'] = X and returns X

    Args:
        create_intermediates: When True, creates missing intermediate dicts for set_to/default modes
    """

    # Parse args
    mode = ('set' if set_to is not MFKEYPATH_NONE else 'default' if default is not MFKEYPATH_NONE else 'get')
    keys = kp.split('/') 

    # Footgun protection
    assert not ((set_to is not MFKEYPATH_NONE) and (default is not MFKEYPATH_NONE)), f"Either set_to= or default= can be used, not both."
    if mode == 'get': assert create_intermediates == False, f"create_intermediates only works when set_to= or default= is present."
    assert not kp.startswith('/'), f"Keypaths shouldn't start with /"
    assert not kp.endswith('/'), f"Keypaths shouldn't end with with /"
    keys = [key for key in keys if len(key)] # Filter out empty keys that could appear due to: double slash //, slash at the start/end of the path, empty path. (Maybe more I can't think of)

    # Walk/modify the dict
    current = dict
    if mode == 'get':
        for key in keys:
            current = current.get(key, {})             # Simply return {} if the keypath doesn't exist. || Note that we can't differentiate between a missing path and an actual {} value stored in the dict. || Note: We also tried returning None but that's more annoying since it crashes when you try to do anything with it so you always need to check for it. This is more like objc. Not sure if wise. [Jan 2026]
        return current
    else:

        for key in keys[:-1]:                                                   # Walk up to the second-to-last key
            if create_intermediates: current = current.setdefault(key, {})      # Create dicts on the path.
            else:                    current = current[key]                     # Crashes if the keypath doesn't exist, except when create_intermediates= is used. 
        
        if mode == 'set':       current[keys[-1]] = set_to                  # Modify at the last key
        elif mode == 'default': return current.setdefault(keys[-1], default)

def exc_desc(e: Exception) -> str:
    return f"{type(e).__name__}({e})"

def mfdedent(s: str) -> str:

    # Better alternative to textwrap.dedent() 
    # 
    # Advantage:
    #   Doesn't require use of `\` at  the start and end of the string to remove unwanted newlines.
    # 
    # Behavior:
    #   - Dedents the string like textwrap.dedent()
    #   - Removes exactly one newline at the beginning if present
    #   - Removes exactly one newline at the end if present
    #   - Preserves all other newlines and whitespace
    # 
    # Implementation:
    #   We can simply check whether the firstchar/lastchar is a newline, because textwrap.dedent() removes all whitespace from empty lines – That makes things much simpler for us!
    #
    # Example:
    #       
    #       This textwrap.dedent code:
    #           ```
    #           textwrap.dedent("""\
    #   
    #               **CoolHeader**
    #               CoolText\
    #           """)
    #           ```
    #
    #       ... is equivalent to this mfdedent code:
    #           ```
    #           mfdedent("""
    #   
    #               **CoolHeader**
    #               CoolText
    #           """)
    #           ```

    s = textwrap.dedent(s)
    if s.startswith('\n'):  s = s[1:]
    if s.endswith('\n'):    s = s[:-1]
    return s

def xcode_project_uuid():
    
    """
    The project.pbxproj file from Xcode uses 12 digit hexadecimal numbers (which have 24 characters) as keys/identifiers for it's 'objects'. So here we generate such an identifier. (In a really naive way)
    """
    
    result = ""
    for _ in range(24):
        num = random.randint(0, 15)
        hexa = hex(num)[2:].capitalize()
        result += hexa
    
    assert(len(result) == 24)
    
    return result
    

def find_xcode_project_build_schemes(repo_path, project_path):

    # Credit: ChatGPT
    
    # Define extra options
    #   Hopefull these prevent xcodebuild from resolving packages and doing weird stuff.
    #   ...If I do this, CocoaLumberJack will be deleted and added by Xcode in an infinite loop or sth ->  "-dry-run -skipPackageSignatureValidation -skipMacroValidation -skipPackagePluginValidation -skipPackageUpdates -onlyUsePackageVersionsFromResolvedFile -disableAutomaticPackageResolution"
    #   Update:  The cocoalumberjack issues were bc I drag-and-dropped a copy of the framework into a project folder inside Xcode, so maybe we could try this again.
    extra_options = "" 
    
    # Run xcodebuild -list to get the list of schemes
    result = runclt(f'xcodebuild -list -project "{project_path}" {extra_options}', cwd=repo_path)
    
    # Extract schemes using regex
    schemes_string = result.split('Schemes:')[1]
    result = re.findall(r'^\s+(\S+)\s*$', schemes_string, flags=re.MULTILINE)
    
    # Return
    return result


#
# MARK: Maths
#

def scale(x: float, from_range: tuple[float, float], to_range: tuple[float, float]) -> float: # Linear transform or something. We use the same thing in mac-mouse-fix and mac-mouse-fix-website [Oct 2025]
    x = (x - from_range[0]) / (from_range[1] - from_range[0])
    x = (x * (to_range[1] - to_range[0])) + to_range[0]
    return x

# 
# MARK: Byte -> Human
#   Convert number of bytes to human-readable representation
#   I don't think this needs to be localized.
# 
class HumanBytes: # Source: 
    METRIC_LABELS: List[str] = ["B", "kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
    BINARY_LABELS: List[str] = ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB"]
    PRECISION_OFFSETS: List[float] = [0.5, 0.05, 0.005, 0.0005] # PREDEFINED FOR SPEED.
    PRECISION_FORMATS: List[str] = ["{}{:.0f} {}", "{}{:.1f} {}", "{}{:.2f} {}", "{}{:.3f} {}"] # PREDEFINED FOR SPEED.
    @staticmethod
    def format(num: Union[int, float], metric: bool=False, precision: int=1) -> str:
        """
        Human-readable formatting of bytes, using binary (powers of 1024)
        or metric (powers of 1000) representation.
        """
        assert isinstance(num, (int, float)), "num must be an int or float"
        assert isinstance(metric, bool), "metric must be a bool"
        assert isinstance(precision, int) and precision >= 0 and precision <= 3, "precision must be an int (range 0-3)"
        unit_labels = HumanBytes.METRIC_LABELS if metric else HumanBytes.BINARY_LABELS
        last_label = unit_labels[-1]
        unit_step = 1000 if metric else 1024
        unit_step_thresh = unit_step - HumanBytes.PRECISION_OFFSETS[precision]
        is_negative = num < 0
        if is_negative: # Faster than ternary assignment or always running abs().
            num = abs(num)
        for unit in unit_labels:
            if num < unit_step_thresh:
                # VERY IMPORTANT:
                # Only accepts the CURRENT unit if we're BELOW the threshold where
                # float rounding behavior would place us into the NEXT unit: F.ex.
                # when rounding a float to 1 decimal, any number ">= 1023.95" will
                # be rounded to "1024.0". Obviously we don't want ugly output such
                # as "1024.0 KiB", since the proper term for that is "1.0 MiB".
                break
            if unit != last_label:
                # We only shrink the number if we HAVEN'T reached the last unit.
                # NOTE: These looped divisions accumulate floating point rounding
                # errors, but each new division pushes the rounding errors further
                # and further down in the decimals, so it doesn't matter at all.
                num /= unit_step
        return HumanBytes.PRECISION_FORMATS[precision].format("-" if is_negative else "", num, unit)

#
# MARK: Dependency Tracking
#

def _deptracker_get_deps(deptracker_archive_path: str) -> dict:
    deps = None
    try:                    deps = json.loads(Path(deptracker_archive_path).read_text())
    except Exception as e:  deps = {}
    assert deps is not None, f"Buggy code"
    return deps

def _deptracker_set_deps(deptracker_path: str, newdeps: dict) -> None:
    result = json.dumps(newdeps, ensure_ascii=False, indent=4)
    Path(deptracker_path).write_text(result)

def _deptracker_hash(s: bytes) -> str:
    #   Note: [Mar 2025] haven't looked into what the best hashing algorithm or library or params or anything.
    return hashlib.md5(s).hexdigest()

def _deptracker_check(deptracker_archive_path:str, source_hashes_or_paths:list[str], target_path:str, sources_are_files:bool) -> bool:

    # If this returns true, the target file is still up-to-date
    # If this returns false, the target file should be recomputed from its sources

    # Declare result
    result = None
    reason = None

    try:

        # Check if target exists
        if not os.path.exists(target_path):
            raise Exception(f"Target file doesn't exist at '{target_path}'")

        # Load deps
        deps = _deptracker_get_deps(deptracker_archive_path)

        # Check target hashes
        #   Note: [Mar 2025] Checking the target file hash for modifications isn't super necessary I think. Might even slow things down for big files.
        target_hash = _deptracker_hash(Path(target_path).read_bytes())
        stored_target_hash = deps[target_path]['target_hash']
        if target_hash != stored_target_hash:
            raise Exception(f"Target file has been modified at '{target_path}'. Stored hash: {stored_target_hash}, fresh hash: {target_hash}")

        if not sources_are_files:
            # Compare source hashes
            cached_source_hashes = deps[target_path]['source_hashes']
            if cached_source_hashes != source_hashes_or_paths:
                raise Exception(f"Source hashes differ - fresh: {source_hashes_or_paths}, cached: {cached_source_hashes}")
        else:
            # Compare source files
            cached_source_paths = []
            for source in deps[target_path]['sources']:
                
                # Store path
                cached_source_path = source['source_path']
                cached_source_paths.append(cached_source_path)
                
                # Check hash
                cached_source_hash = source['source_hash']
                source_hash = _deptracker_hash(Path(cached_source_path).read_bytes())
                if source_hash != cached_source_hash:
                    raise Exception(f"Source file has been modified at '{cached_source_path}'")

            # Check paths
            diff = set(cached_source_paths).symmetric_difference(set(source_hashes_or_paths))
            if len(diff) > 0:
                raise Exception(f"Source files differ. diff: {diff}")

        # Success
        result = True

    except Exception as e:
        # Handle failure
        reason = exc_desc(e)
        result = False
    
    # Log
    if result == False:
        print(f"Dependency tracker: Check failed for file '{target_path}' with reason: {reason}")
    elif result == True:
        print(f"Dependency tracker: Check succeeded for file '{target_path}'.")
    else:
        assert False, f"Buggy code"

    # Return
    return result

def _deptracker_stamp(deptracker_archive_path:str, source_hashes_or_paths:list[str], target_path:str, sources_are_files:bool) -> None:

    # Call this after recomputing the target file from the source files

    # Load deps
    deps = _deptracker_get_deps(deptracker_archive_path)
    
    # Update deps
    new_entry = {
        'target_hash': _deptracker_hash(Path(target_path).read_bytes()),
    }
    if not sources_are_files:
        new_entry['source_hashes'] = source_hashes_or_paths
    else:
        new_entry['sources'] = [
            { 
                'source_path': source_path, 
                'source_hash': _deptracker_hash(Path(source_path).read_bytes()) 
            }
            for source_path in source_hashes_or_paths
        ]

    deps[target_path] = new_entry

    # Store deps
    _deptracker_set_deps(deptracker_archive_path, deps)

    # Log
    entry_desc = f"{{'{target_path}': {new_entry}}}"
    print(f"Dependency tracker: Recorded stamp-of-approval for target-sources relationship: {entry_desc}")

def deptracked(deptracker_archive_path:str, source_hashes_or_paths:list[str], target_path:str, sources_are_files:bool=False, allow_missing_source_files:bool=True):

    # Decorator for automatically adding to-file-caching to a function
    #
    # Note: [Mar 2025] On source hashes/files
    #   The deptracker accepts either hashes or file paths as sources. If the sources are file paths, it generates the hashes itself based on file content.
    #
    # Notes for _deptracker_stamped() invocation below
    #   Caution: [Mar 2025]
    #       User needs to make sure to update the source files before this is called! (Otherwise, the deptracker will reference an outdated source file)
    #   Optimization: [Mar 2025]
    #       - This reloads and recomputes the hash for the source_paths every time. (Inefficient since for translations there's one source file for many translations – and the source file always has the same hash.)
    #       - This reloads the new_target_string from file – the derivation func probably already knows this string and could pass it in.
    #       - We could reuse file-handles from _deptracker_check() for the _deptracker_stamp() instead of opening/closing the files twice.
    #       > Conclusion: We'll use the deptracker on slow operations, so this stuff is unlikely to matter.

    def decorator(target_file_updater: Callable[[None],None]):

        # Validate source hashes
        if not sources_are_files:
            assert all([len(hash) > 0 for hash in source_hashes_or_paths]), f'Some source hash is empty. Source hashes: {source_hashes_or_paths}'

        # Validate source files
        if sources_are_files:
            for p in source_hashes_or_paths:
                if not os.path.exists(p):
                    msg = "Dependency tracker: {action} derivation of '{target_path}' because source file '{p}' doesn't exist."
                    if allow_missing_source_files:
                        print(msg.format(action="Skipping", target_path=target_path, p=p)) # [Mar 2025] We wanna allow missing source files during development for flexibility.
                        return lambda: None
                    else:
                        assert False, msg.format(action="Aborting on", target_path=target_path, p=p)

        def wrapper() -> None:            
            # Main logic
            if not _deptracker_check(deptracker_archive_path, source_hashes_or_paths, target_path, sources_are_files):
                derivation_succeeded = target_file_updater() # This is expected to update the target file, or return False
                assert isinstance(derivation_succeeded, bool), f"Wrapped function unexpectedly returned non-boolean value: {derivation_succeeded}"
                if derivation_succeeded:
                    _deptracker_stamp(deptracker_archive_path, source_hashes_or_paths, target_path, sources_are_files)
        
        return wrapper
    return decorator

#
# MARK: Command line tools
#

def clt_result_description(returncode, stdout=None, stderr=None) -> str:
    
    result = f"""\
        
code: {returncode}

stdout:
{add_indent(stdout, 2)}
[[endstdout]]

stderr:
{add_indent(stderr, 2)}
[[endstderr]]

"""
    
    return result
    

def runclt(*command_arg, cwd: str|None = None, print_live_output: bool = False, manually_handle_errors: bool = False, strip_stdout: bool = True) -> str | tuple[str, int, str]:
    

    """
    (Run) a (c)ommand-(l)ine-(t)ool
    Use this instead of subprocess

    Examples: [Jan 2026]
        
        stdout = runclt('git status --short')                                           # returns stdout, raises on error (if returncode != 0 or stderr != '')

        stdout, code, stderr = runclt('git status', manually_handle_errors=True)        # Custom handling of returncode and stderr

        runclt('npm install', print_live_output=True)                                   # Stream output as it runs (for long-running subtasks)

        runclt(['git', 'commit', '-m', 'my message'], print_live_output=True)           # You can also pass a list of strings instead of a string

        runclt('cat myfile.txt > output.txt')                                           # DOESNT WORK -> You can't do shell stuff. We just mimic shell syntax using shlex.split. We decided to do that because shell=True is a "security problem" (although I don't know if that matters here) [Jan 2026]

    """

    # Preprocess `command`
    
    if len(command_arg) > 1: assert False, f"Passed multiple positional args ({command_arg}). Instead, pass a single string or list."
    
    commands: list[str] = []
    if   type(command_arg[0]) is list:  commands = command_arg[0]
    elif type(command_arg[0]) is str:   commands = shlex.split(command_arg[0])

    command_name = commands[0]
    
    # Warn against footguns
    assert command_name != 'cd', f"cd will only affect the subprocess, not the Python process. Use os.chdir() instead."
    
    # Run process and collect output
    stdout = ""
    stderr = ""
    returncode = None
    with subprocess.Popen(commands, cwd=cwd, shell=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
        
        while 1:
            
            # Handle stdout
            if print_live_output: print(f"{command_name}: stdout {{", end='\n') # Print stdout header
            while 1:
                stdout_line = proc.stdout.readline() # Read stdout line
                if not stdout_line: break # Break
                stdout += f"\n{stdout_line}" # Store stdout line
                if print_live_output: print(f"  > {stdout_line}", end='') # Print stdout line
            if print_live_output: print(f"}} endstdout: {command_name}", end='\n') # Print stdout footer
            
            # Handle stderr
            if print_live_output: print(f"{command_name}: stderr {{", end='\n') # Print stderr header
            while 1:    
                stderr_line = proc.stderr.readline() # Read stderr line
                if not stderr_line: break # Break
                stderr += f"\n{stderr_line}" # Store stderr line
                if print_live_output: print(f"  > {stderr_line}", end='') # Print stderr line
            if print_live_output: print(f"}} endstderr: {command_name}", end='\n') # Print stderr footer
            
            # Check if subproc has finished
            returncode = proc.poll()
            if returncode != None:
                break
    
    # Process stdout
    if strip_stdout:
        stdout = stdout.strip() # The stdout sometimes has trailing newline character which we remove here.

    # Return
    if not manually_handle_errors:
        assert returncode == 0 and stderr == '', f"Command \n\"{shlex.join(commands)}\"\n was run in cwd {f'"cwd"' if cwd else f'"{os.getcwd()}" (implicit)'} and failed with result:\n{ clt_result_description(returncode, stdout, stderr)}.\n\nPass manually_handle_errors=True to avoid this error. [Jan 2026]"
        return stdout
    else:
        return stdout, returncode, stderr

def run_git_command(repo_path, command):
    
    """
    Helper function to run a git command using subprocess. 
    (Credits: ChatGPT)
    
    Should probably unify this into runCLT, along with other uses of `subprocess`
    """
    proc = subprocess.Popen(['git', '-C', repo_path] + command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"Git command error: {stderr.decode('utf-8')}")

    return stdout.decode('utf-8')


#
# MARK: Strings
#

def add_indent(s, indent_spaces=2):
    return textwrap.indent(s, ' ' * indent_spaces)

def get_indent(string: str) -> tuple[int, chr]:
    
    # NOTE: We could possibly use textwrap.dedent() etc instead of this
    
    # Edge case
    if string == '':
        return 0, ''

    # Split into lines
    lines = string.split('\n')
    
    # Remove lines empty lines (ones that have no chars or only whitespace)
    def is_empty(string: str):
        return len(string) == 0 or all(character.isspace() for character in string)
    lines = list(filter(lambda line: not is_empty(line), lines))
    
    # Special case
    if len(lines) == 0:
        return 0, ''

    # Loop

    indent_level = 0
    break_outer_loop = False
    
    while True:
        
        # Idea: If all lines have a an identical whitespace at the current indent_level, then we can increase the indent_level by 1. 
        #   Note: GitHub Flavoured Markdown apparently considers 1 tab equal to 4 spaces. Don't know how we could handle that here. We'll just crash on tab.
        
        last_line = None
        for line in lines:
            
            assert line[indent_level] != '\t' # Tabs are weird, we're not sure how to handle them.
            
            is_space = line[indent_level].isspace()
            is_differnt = line[indent_level] != last_line[indent_level] if last_line != None else False
            if not is_space or is_differnt: 
                break_outer_loop = True; break
            last_line = line
        
        if break_outer_loop:
            break    
        
        indent_level += 1
    
    indent_char = None if indent_level == 0 else lines[0][0]

    return indent_level, indent_char

def set_indent(string: str, indent_level: int, indent_character: chr) -> str:
    
    # Get existing indent
    old_level, old_characer = get_indent(string)
    
    # Remove existing indent
    if old_level > 0:
        unindented_lines = []
        for line in string.split('\n'):
            unindented_lines.append(line[old_level:])
        string = '\n'.join(unindented_lines)
    
    # Add new indent
    if indent_level > 0:
        indented_lines = []
        for line in string.split('\n'):
            indented_lines.append(indent_character*indent_level + line)
        string = '\n'.join(indented_lines)
    
    # Return
    return string

def trim_empty_lines(string: str) -> str:

    """
    Removes leading and trailling empty lines
    """

    # Split
    lines = string.splitlines()

    # Filter out leading empty lines
    lines_2 = None
    for i in range(0, len(lines)):
        
        line_is_empty = (lines[i].strip() == '')
        
        if not line_is_empty:
            lines_2 = lines[i:]
            break
    
    # Early return
    if lines_2 == None:
        return ''

    # Filter out trailling empty lines
    lines_3 = None
    for i in reversed(range(0, len(lines_2))):

        line_is_empty = (lines_2[i].strip() == '')

        if not line_is_empty:
            lines_3 = lines_2[:i+1]
            break
    
    # Early return
    if lines_3 == None:
        assert False, f'Not sure this can happen, since the lines_2 early return case should\'ve already been hit if the string only contains empty lines.'
        return ''

    # Assemble result
    result = '\n'.join(lines_3)

    # Return
    return result

#
# MARK: JSON
#

import dataclasses, json

class JSONEncoder(json.JSONEncoder):
        
    # JSON encoder that can encode `@dataclass`es
    #   Usage example:
    #       json.dumps(foo, cls=mfutils.JSONEncoder)

    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)

#
# MARK: Markdown
#  

def conditional_render_with_jinja_if_blocks(string: str, condition_dict: dict[str, bool]) -> str:

    """
    
    Arguments: 
        `string` that contains jinja-style if-blocks. 
        `condition_dict` that specifies which jinja-style-if-blocks's content should be included in the output and which should be omitted

    Example 1:
        Input: 
            condition_dict: 
                { 'some_conddd': False }
            string:
                blabla
                {% if some_conddd %}
                Cool Content
                {% endif %}
                blub
        Output:
                blabla
                blub
    Example 2:
        Input:
            condition_dict: 
                { 'some_conddd': True }
            string:
                blabla
                {% if some_conddd %}
                Cool Content
                {% endif %}
                blub
        Output:
            blabla
            Cool Content
            blub
    
    Notes:
    - Regex was created and tested here: https://regex101.com/r/9iFynq
    - Example of using real jinja if-blocks for conditional rendering: https://stackoverflow.com/questions/27786948/conditional-rendering-of-html-segment-using-render-template
    - If we need more powerful stuff for our md templates, we should probably actually use jinja instead of reimplementing its functionality. 
    """

    assert False    # [Aug 2025] Unused now. This was only used for conditionally showing the 'localization progress' banner. But we've moved the generation of the 'localization progress' and 'locale picker' text completely into code now, instead of trying to do as much of it as possible in the templates. 
                    #   (We made this change to avoid having to duplicate the 'localization header' stuff across all the localizable templates. 
                    #       For that, we could've gone 2 routes: Make the templates more powerful with 'component' system, or move the duplicated strings into code entirely. We went with moving things into code, which also made this here obsolete. Before we make the templates more powerful, we should consider using a 'real' templating language like jinja instead.)

    result = string

    regex = r'{%\s*?if\s*(.*?)\s*?%}\n(.*?)\n{%\s*?endif\s*?%}'

    all_conditions_in_string: list[str] = []

    for match in re.finditer(regex, string, re.MULTILINE | re.DOTALL):

        full_match = match.group(0)
        condition, content = match.groups()

        assert len(full_match) > 0
        assert len(condition) > 0
        assert ' ' not in condition
        assert '\n' not in condition
        assert condition in condition_dict

        do_render = condition_dict[condition]

        if do_render:
            result = result.replace(full_match, content)
        else:
            result = result.replace(full_match, '')
        
        all_conditions_in_string.append(condition)
    
    if (0): # Turn off assert because we're not using the same set of conditions for every document
        assert all_conditions_in_string == list(condition_dict.keys())

    return result

def int_to_letter(n: int):
    # Maps 1 -> a, 2 -> b, 3 -> c, ...
    return chr(96 + n)

def int_to_LETTER(n: int):
    # Maps 1 -> A, 2 -> B, 3 -> C, ...
    return chr(64 + n)

def replace_html_images_with_format_specifiers(md_string: str):

    # HTML <img> version of `replace_markdown_urls_with_format_specifiers()`

    # Create regex for <img> HTML tags
    img_regex = r'''(?x)
    (               # Capture the whole thing in a group.
        <img
            [^>]*?  # All the image params
        (?:       # 3 Different ways of closing an <img> tag
            >\s*?<\/img>    # This must be first to take precedence over the other options, so it's ever matched [Sep 2025]
            |
            >
            |
            \>
        )
    )
    '''

    # Call helper
    _result = _replace_captured_strings_with_format_specifiers(md_string, img_regex, "img") # Use `img` instead of `image` in the format specifier to communicate that localizers shouldn't translate that word. [Sep 2025]

    # Convert to expected result format
    @dataclass
    class Result:
        md_string: str
        removed_imgs: list[str]
    return Result(_result.result_string, _result.removed_strings)

def replace_format_specifiers_with_html_images(md_string: str, imgs: list[str]) -> str:
    result = _replace_format_specifiers_with_captured_strings(md_string, imgs, "img")
    return result

def replace_markdown_urls_with_format_specifiers(md_string: str):

    # Replace the urls of the [markdown](links) inside `md_string` with url<X> format specifiers (Such as '{url1}', '{url2}', etc)
    #       Also returns a list of the removed urls.
    #   Note: We thought about using c-style/IEEE-style format specifiers (e.g. '%2$s') since those are highlighed by Xcode when editing .xcstrings files, and localizers should be used to them from localizing the main app, but python-style specifiers are easier to implement for now. If localizers struggle with this, we could change it.
    #   
    #   Example: 
    #       (See the helper function: _replace_captured_strings_with_format_specifiers())

    # Define mdlink regex
    #   Matches markdown links. [The](url) is captured in group url1 or url2.
    #   Created and documented here: https://regex101.com/r/FcEKlP/3
    #   Meta: [Jul 2025] Not sure we're overcomplicating things with the (<escaped>) urls. Those urls are useful if the url contains spaces or `)` – but couldn't we just avoid creating such URLs?
    mdlink_regex = r'''(?x)
    \[
        [^\]]+? # Link Name
    \] 
    \((?:
        <(?P<url1>.*?)> # (<escaped>) urls. These can contain `)`
        |
        (?P<url2>[^\)]*?) # (regular) urls.
    )\)
    '''

    # Call helper
    _result = _replace_captured_strings_with_format_specifiers(md_string, mdlink_regex, "url") # Replace with {url_xx}
    
    # Convert to expected result format.
    @dataclass
    class Result:
        md_string: str
        removed_urls: list[str]
    return Result(_result.result_string, _result.removed_strings)

def replace_format_specifiers_with_markdown_urls(md_string: str, urls: list[str]) -> str:

    # Replace url_<X> format specifiers (such as '{url_1}', '{url_2}', etc) inside `md_string` with the urls from `urls`

    result = _replace_format_specifiers_with_captured_strings(md_string, urls, "url")
    return result

def _replace_captured_strings_with_format_specifiers(input_string: str, regex_pattern: str, format_specifier_stem: str):

    #   Overview: [Sep 2025]
    #   Finds matches for `regex_pattern` in `input_string`. 
    #   Every match is expected to have **exactly 1 non-empty capturing group**.
    #   This capturing group will be replaced by a format specifier containing `format_specifier_stem`, 
    #       or containing `format_specifier_stem + "_1"`, `format_specifier_stem + "_2"`, etc. (in case there are multiple matches in the string)
    #   
    #   Purpose [Sep 2025]
    #   This is used as a helper function for our url-replacement and <img>-tag replacement functions which 
    #       we use to preprocess localized strings to make things easier for localizers. [Sep 2025]
    #
    #   Example: [Sep 2025]
    #       Input: 
    #           input_string             = "Some [cool](https://google.com) stuff, and a [fruity](https://apple.com) website."
    #           regex_pattern            = <pattern that matches [markdown](links) and captures the url in its only non-empty capturing group.
    #           format_specifier_stem    = "url"
    #       Output: 
    #           result_string = "Some [cool]({url_1}) stuff, and a [fruity]({url_2}) website."
    #           removed_strings = ["https://google.com", "https://apple.com"]

    # Declare result type
    @dataclass
    class Result:
        result_string: str
        removed_strings: list[str]

    # Declare vars
    result_string = None
    removed_strings = []
    found_str_ctr = 0
    n_occurences_of_pattern = -1

    # Declare helper function
    #   For re.sub()
    def get_replacement(match: re.Match) -> str:
        
        captured_strings = list(match.groups())
        captured_strings = [x for x in captured_strings if x] # Filter empty matches
        assert len(captured_strings) == 1, f"Number of non-empty capturing groups in '{match.group(0)}' for pattern '{regex_pattern}' is not 1."
        captured_string = captured_strings[0]

        removed_strings.append(captured_string)

        nonlocal found_str_ctr
        found_str_ctr += 1
        
        placeholder = f'{{{format_specifier_stem}}}'
        if n_occurences_of_pattern != 1:
            placeholder = f'{{{format_specifier_stem}_{found_str_ctr}}}'

        replacement = match.group(0).replace(captured_string, placeholder)

        return replacement

    # Get occurences_of_pattern
    n_occurences_of_pattern = len(re.findall(regex_pattern, input_string, 0))

    # Call re.sub()
    result_string = re.sub(regex_pattern, get_replacement, input_string, 0, 0)

    # Return
    return Result(result_string, removed_strings)

def _replace_format_specifiers_with_captured_strings(input_string: str, captured_strings: list[str], format_specifier_stem: str) -> str:

    # Inverse of _replace_captured_strings_with_format_specifiers()
    #   
    #   Example: [Sep 2025]
    #       Input: 
    #           input_string          = "Some [cool]({url_1}) stuff, and a [fruity]({url_2}) website."
    #           captured_strings      = ["https://google.com", "https://apple.com"]
    #           format_specifier_stem = "url"
    #       Output: 
    #           "Some [cool](https://google.com) stuff, and a [fruity](https://apple.com) website."

    # Format
    result = input_string
    for i, captured_string in enumerate(captured_strings, 1):

        placeholder = f'{{{format_specifier_stem}}}'
        if len(captured_strings) != 1:
            placeholder = f'{{{format_specifier_stem}_{i}}}'

        assert placeholder in result, f'mfutils: Placeholder "{placeholder}" not found while trying to insert captured strings into string:\n{input_string}'

        result = result.replace(placeholder, captured_string)

    # Return result
    return result

#
# MARK: Files
#

#   Update: [Dec 2025] These file abstractions are pretty ridiculous. Just use pathlib.

def create_temp_file(suffix=''):
    
    # Returns temp_file_path
    #   Use os.remove(temp_file_path) after you're done with it
    
    temp_file_path = ''
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file_path = temp_file.name
    return temp_file_path

def read_tempfile(temp_file_path, remove=True):
    
    result = read_file(temp_file_path)
    
    if remove:
        os.remove(temp_file_path)
    
    return result

def read_file(file_path, encoding='utf-8'):
    # Note: [Mar 2025] It's probably better to just use pathlib instead
    result = ''
    with open(file_path, 'r', encoding=encoding) as temp_file:
        result = temp_file.read()
    
    return result

def write_file(file_path, content, encoding='utf-8'):
    with open(file_path, 'w', encoding=encoding) as file:
        file.write(content)

def read_xcstrings_file(xcstrings_path: str, allow_empty=False) -> dict|None:
    s = read_file(xcstrings_path)
    if len(s.strip()) == 0:
        if not allow_empty: assert False
        else: return None
    return json.loads(s)

def write_xcstrings_file(xcstrings_path: str, xcstrings_obj: dict):
    
    # TODO: Make sure we adopt this everywhere.
    
    #   We set all these args so that the output will exactly follow the Xcode format. If we don't do this, 
    #   Xcode will convert the file formatting once we edit it in Xcode, which leads to changes in the git history.
    #
    #   1. ensure_ascii=False --> Makes the output utf-8 instead of ascii. (Otherwise emojis will be ascii encoded and stuff)
    #   2. separators=(',', ' : ') --> Changes the separators used in the resulting json file to look exactly like Xcode formats them.
    #   3. + '\n' --> Trailing newline to match how Xcode formats .xcstrings files after you edit them. (Prevents git churn) [Dec 2025]
    #       Update: [Dec 27 2025] Now Xcode doesn't add '\n' anymore? – I removed that code.
    
    write_file(
        xcstrings_path, 
        json.dumps(xcstrings_obj, indent=2, ensure_ascii=False, separators=(',', ' : '))
    )

def convert_utf16_file_to_utf8(file_path):
    
    content = read_file(file_path, 'utf-16')
    write_file(file_path, content, encoding='utf-8')

def is_file_empty(file_path):
    """Check if file is empty by confirming if its size is 0 bytes.
        Also returns true if the file doesn't exist."""
    return not os.path.exists(file_path) or os.path.getsize(file_path) == 0
