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

from dataclasses import dataclass

#
# Command line tools
#

def clt_result_description(returncode, stdout, stderr) -> str:
    
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
    
def runclt(command_arg: str | list, cwd: str = None, print_live_output: bool = False, prefer_arm64: bool = True) -> str | None:
    
    """
    
    Notes on args that we're passing to subprocess.run():
        - `shell=False`: Invoking the clt directly instead of calling it through a shell.
            -> When using `shell=True`, it allows you to pass the clt and args in a single string and also to use several commands using ; or use shell features like | pipes.
            -> However, using `shell=True` is a SECURITY PROBLEM if we pass in any user-generated strings. -> Never use that without considering security.
            -> We're using shlex to process the input string so that we can pass in the command and args as a single string as you would use it on the command line but without having to enable `shell=True`
        - `text=True`: Return stdout and stderr as string instead of bits
        - `cwd=cwd`: Sets the working directory for the subprocess. 
        - `executable=exec`: Replaces the program to execute.
            -> We used to have this set for some reason, I think to replace the shell, but I don't think we should set this.
    
    """
    
    # Preprocess `command`
    #   -> So that it works similar to as if shell=True (we can pass in the args as a single string, like on the command-line) but yet we can keep shell=False (because that's a security problem)
    #   -> If one of your args contains spaces, you can escape with "with quotes" or with\ backslashes - just like a normal shell (Implemented by shlex)
    
    commands = None
    if type(command_arg) is list:
        commands = command_arg
    elif type(command_arg) is str:
        commands = shlex.split(command_arg)
    
    command_name = commands[0]
    
    # Handle non-standard return codes
    success_codes=[0]
    if commands[0] == 'git' and commands[1] == 'diff': 
        success_codes.append(1) # Git diff returns 1 if there's a difference
    
    # Launch the arm64 version of the clt
    #   Background: On my M1 mac all the clts are normally launched as x86_64 for some reason. This causes xcodebuild to fail with weird errors about provisioning profiles. 
    #   Explanation: `arch -arm64 -x86_64 <clt> <args>` will launch the -arm64 version of clt, if available, otherwise it should fall back to available archs.
    if prefer_arm64:
        commands = ['arch', '-arm64', '-x86_64'] + commands
    
    # Run process and collect output
    
    stdout = ""
    stderr = ""
    returncode = None
    with subprocess.Popen(commands, cwd=cwd, shell=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
        
        while True:
            
            # Print
            if print_live_output:
                print(f"{command_name}: stdout {{", end='\n')
            
            # Read stdout
            while True:
                
                stdout_line = proc.stdout.readline()
                if stdout_line == None or len(stdout_line) == 0:
                    break                
                else:
                    stdout += f"\n{stdout_line}"
                    if print_live_output:
                        print(f"  > {stdout_line}", end='')
            
            # Print
            if print_live_output:
                print(f"}} endstdout: {command_name}", end='\n')
                print(f"{command_name}: stderr {{", end='\n')

            # Read stderr
            while True:
                
                stderr_line = proc.stderr.readline()
                if stderr_line == None or len(stderr_line) == 0:
                    break                
                else:
                    stderr += f"\n{stderr_line}"
                    if print_live_output:
                        print(f"  > {stderr_line}", end='')
                
            # Print    
            if print_live_output:
                print(f"}} endstderr: {command_name}", end='\n')
            
            # Check if subproc has finished
            returncode = proc.poll()
            if returncode != None:
                break

    if not print_live_output:
        assert stderr == '' and returncode in success_codes, f"Command \n\"{shlex.join(commands)}\"\n was run in cwd \"{cwd}\" and failed with result:\n{ clt_result_description(returncode, stdout, stderr) }"
        stdout = stdout.strip() # The stdout sometimes has trailing newline character which we remove here.
        return stdout
    else:
        print('')
        assert returncode in success_codes, f"Command \n\"{shlex.join(commands)}\"\n was run in cwd \"{cwd}\" and failed with result: { returncode }"  # Note that we allow stderr to be non-empty with print_live_output. It's ok since it's printed to the console, so we consider it 'handled' I guess.
        return None

def runclt_insecure(command, cwd=None, exec=None): 
    
    """
    Notes:
    
    This is a SECURITY PROBLEM.
    -> What makes this insecure is if we set shell=True on subprocess.run and then pass in user-generated strings. 
        (If you don't pass in user generated strings, this is ok to use)
    -> We replaced this with runclt(), renamed this func to runclt_insecure() and added these notes about security in the commit after b052473ad4a5efd9128f2934daf15bdbd0daf8a7
    

        
    """
    
    assert False
    
    success_codes=[0]
    if command.startswith('git diff'): 
        success_codes.append(1) # Git diff returns 1 if there's a difference
    
    clt_result = subprocess.run(command, cwd=cwd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, executable=exec)
    
    assert clt_result.stderr == '' and clt_result.returncode in success_codes, f"Command \"{command}\", run in cwd \"{cwd}\"\nreturned: {clt_result_description(clt_result)}"
    
    clt_result.stdout = clt_result.stdout.strip() # The stdout sometimes has trailing newline character which we remove here.
    
    return clt_result.stdout

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
# Strings
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
# JSON
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
# Markdown
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
    
    assert all_conditions_in_string == list(condition_dict.keys())

    return result

            

# Define mdlink regex
#   Matches markdown links. [The](url) is captured in the first group.
#   Created and documented here: https://regex101.com/r/mntroB
mdlink_regex = r'\[[^\]]+?\]\(([^\)]+?)\)'

def int_to_letter(n: int):
    # Maps 1 -> a, 2 -> b, 3 -> c, ...
    return chr(96 + n)

def int_to_LETTER(n: int):
    # Maps 1 -> A, 2 -> B, 3 -> C, ...
    return chr(64 + n)

def replace_markdown_urls_with_format_specifiers(md_string: str):

    # Replace the urls of the [markdown](links) inside `md_string` with url<X> format specifiers (Such as '{url1}', '{url2}', etc)
    #       Also returns a list of the removed urls.
    #   Note: We thought about using c-style/IEEE-style format specifiers (e.g. '%2$s') since those are highlighed by Xcode when editing .xcstrings files, and localizers should be used to them from localizing the main app, but python-style specifiers are easier to implement for now. If localizers struggle with this, we could change it.
    #   
    #   Example:
    #       Input: 
    #           "Some [cool](https://google.com) stuff"
    #       Output: 
    #           md_string = "Some [cool]({url1}) stuff"
    #           removed_urls = ["https://google.com"]

    # Declare result type
    @dataclass
    class Result:
        md_string: str
        removed_urls: list[str]

    # Declare vars
    result_md_string = None
    removed_urls = []
    url_ctr = 0
    url_count = -1

    # Declare helper function
    #   For re.sub()
    def get_replacement(match: re.Match) -> str:

        removed_urls.append(match.group(1))

        nonlocal url_ctr
        url_ctr += 1
        
        placeholder = r'{url}'
        if url_count != 1:
            placeholder = f'{{url_{url_ctr}}}'

        replacement = match.group(0).replace(match.group(1), placeholder)

        return replacement

    # Get url_count
    url_count = len(re.findall(mdlink_regex, md_string, 0))

    # Call re.sub()
    result_md_string = re.sub(mdlink_regex, get_replacement, md_string, 0, 0)

    # Return
    return Result(result_md_string, removed_urls)

def replace_format_specifiers_with_markdown_urls(md_string: str, urls: list[str]) -> str:

    # Replace url<X> format specifiers (such as '{url1}', '{url2}', etc) inside `md_string` with the urls from `urls`
    #
    # Example:
    #       Input: 
    #           md_string = "Some [cool]({url1}) stuff"
    #           urls = ["https://google.com/"]
    #       Output: 
    #           "Some [cool](https://google.com) stuff"

    # Get info
    url_count = len(urls)

    # Format
    result = md_string
    for url_ctr, url in enumerate(urls, 1):

        placeholder = r'{url}'
        if url_count != 1:
            placeholder = f'{{url_{url_ctr}}}'

        assert placeholder in result, f'mfutils: URL placeholder "{placeholder}" not found while trying to insert urls into markdown string:\n{md_string}'

        result = result.replace(placeholder, url)

    # Return result
    return result

#
# Files
#

def create_temp_file(suffix=''):
    
    # Returns temp_file_path
    #   Use os.remove(temp_file_path) after you're done with it
    
    temp_file_path = ''
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file_path = temp_file.name
    return temp_file_path

def read_file(file_path, encoding='utf-8'):
    
    result = ''
    with open(file_path, 'r', encoding=encoding) as temp_file:
        result = temp_file.read()
    
    return result


def read_tempfile(temp_file_path, remove=True):
    
    result = read_file(temp_file_path)
    
    if remove:
        os.remove(temp_file_path)
    
    return result

def write_file(file_path, content, encoding='utf-8'):
    with open(file_path, 'w', encoding=encoding) as file:
        file.write(content)

def read_xcstrings_file(xcstrings_path: str) -> dict:
    return json.loads(read_file(xcstrings_path))

def write_xcstrings_file(xcstrings_path: str, xcstrings_obj: dict):
    
    # TODO: Make sure we adopt this everywhere.
    
    #   We set all these args so that the output will exactly follow the Xcode format. If we don't do this, 
    #   Xcode will convert the file formatting once we edit it in Xcode, which leads to changes in the git history.
    #
    #   1. ensure_ascii=False --> Makes the output utf-8 instead of ascii. (Otherwise emojis will be ascii encoded and stuff)
    #   2. separators=(',', ' : ') --> Changes the separators used in the resulting json file to look exactly like Xcode formats them.
    
    write_file(xcstrings_path, json.dumps(xcstrings_obj, indent=2, ensure_ascii=False, separators=(',', ' : ')))

def convert_utf16_file_to_utf8(file_path):
    
    content = read_file(file_path, 'utf-16')
    write_file(file_path, content, encoding='utf-8')

def is_file_empty(file_path):
    """Check if file is empty by confirming if its size is 0 bytes.
        Also returns true if the file doesn't exist."""
    return not os.path.exists(file_path) or os.path.getsize(file_path) == 0

#
# Other
#

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
