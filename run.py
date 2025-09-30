#
# MARK: Imports
#
# (Only import stdlib stuff -> we want to run this without installing requirements)
# (Also don't import shared stuff I think (?) since we want this to be independent of other stuff (not sure this requirement makes sense))

import os
import sys
import glob
import subprocess
import re
import json
import shlex
import textwrap

#
# MARK: Documentation
#

"""

Convenience script for running other python scripts.

Behavior: [Mar 2025]
1. Recursively globs cwd for any .py files that have the same name as user-provided 'subcommand'
    (Certain files and folders are excluded from the search e.g. the /site-packages/ folder found inside python venv folders)
2. If an eligible .py file is found, its parent folder is searched for a requirements.txt file (with the glob pattern `*requirements*.txt`). If requirements are found, a venv is created, and the requirements are installed into it.
3. Additional environment variables are loaded from the ./.env file
4. The script is run (using the venv and the environment vars from the ./env file)

Intended usage: [Mar 2025]
    MMF project repos use mac-mouse-fix-scripts as a submodule, then they 
    - Add a ./env file which adds the library files like mfutil.py to the PYTHONPATH (making those files importable from other scripts) 
    - Add a ./run bash script which simply dispatches to this run.py script - as a convenience
    Then you can simply invoke scripts like this:
        ./run uploadstrings --some-arg
        (And environment vars are also passed to the script)
    -> SUPER CONVENIENT

Sidenotes:
     - How to run things without run.py? [Mar 2025]
        Create venv:            python3 -m venv env
        Install packages:       ./env/bin/python -m pip install -r <path to requirements.txt:
        Use run with .env:      dotenv run -- ./env/bin/python <path to script> <args for script>  
    - Why ./.env? [Mar 2025]
        - IIRC, ./.env was the only way to get VSCode to understand the imports for our own library files like mfutil.py
            (I think its built-in Terminal also imports .env automatically?)
    - How to debug this in VSCode?
        - I think you could: 1. Use run.py to install requirements into a venv. 2. In VSCode, choose the python interpreter from the venv -> Then everything should work.

dotenv file explanation:

    A dotenv file defines environment variables to be used with python.

    Why is mac-mouse-fix using it?
    We want to make the shared.py script importable to the other scripts.
    The only way I found to do this such that VSCode code completions work for the shared.py imports 
    is by creating an .env file and putting ```PYTHONPATH=mac-mouse-fix-scripts/shared/``` into it.
    To use the .env file without vscode, you normally import the `dotenv` library or use the `dotenv`
    command-line-tool, However, you have to install these manually.
    
    Since we want to keep run.py dependency-free, we instead do custom parsing of the .env file inside run.py.

    Custom parsing of the .env file:

        The .env file has a simple syntax that looks like this:
    
            # Application configuration
            APP_NAME=MyCoolApp
            DEBUG=True
            VERSION=1.0.0
            
            # Database configuration
            DATABASE_URL=postgres://user:password@localhost:5432/mydatabase
                            
            # Multiline value using \n
            GREETING=Hello, welcome to MyCoolApp!\nEnjoy your stay.
            
            # Garbage
            THISEQUALS=T=H=A=T
            LOTSOF  =  WHITESPACE
            # comment  =  that should not be parsed
        
        To parse it, we use the regex:

            ^(?!\s*#)(.*?)=(.*)$
        
        You can test it here:

            https://regex101.com/

"""

#
# MARK: Constants
#

venv_path = "env"
dotenv_path = ".env"

# Command map

subcommand_map = {
    # [Mar 2025] Now filled programmatically
}

compound_subcommands = {
    
    "build-markdown":  [
        lambda run_args, args: f"python3 {__file__} {run_args} -- syncstrings",           # We invoke this script again with different subcommands. 
        lambda run_args, args: f"python3 {__file__} {run_args} -- _buildmd {args}"        # Note: We tried calling ./run instead of `python3 __file__` which should do the same thing, but broke the VSCode debugger for some reason.
    ],       
    "mmf-website_build-strings": [
        lambda run_args, args: f"python3 {__file__} {run_args} -- syncstrings",
        lambda run_args, args: f"python3 {__file__} {run_args} -- _buildstrings-website {args}"
    ],
}

help_string = """
Use ./run like this:

    ./run [<run_args> --] <subcommand> <subcommand_args>

Known run_args

    --nopip         -> Don't try to install dependencies via pip – Speeds up iteration time

Known subcommands:

{}

Provided subcommand:

    {}

"""

def print_help_and_exit(subcommand, exit_code=1):

    longest_name = max([len(k) for k in subcommand_map.keys()])
    command_desc = ''
    for i, (name, value) in enumerate(subcommand_map.items()):
        if i != 0: command_desc += '\n'
        name = name + ' '*(longest_name-len(name))
        command_desc += f"- {name}"
        if isinstance(value, str):
            command_desc += f" ({value})"
    command_desc = textwrap.indent(command_desc, 4*' ')

    print(help_string.format(command_desc, subcommand))
    exit(exit_code)

#
# MARK: Dotenv
#

def load_dotenv():
    
    # Get file content
    content = None
    with open(dotenv_path, 'r') as file:
        content = file.read()
    
    # Apply regex
    regex = r'^(?!\s*#)(.*?)=(.*)$'
    matches = re.finditer(pattern=regex, string=content, flags=re.MULTILINE) # MULTILINE activates ^ and $
    
    # Compile result
    #   Note: We're also stripping out whitespace here
    result = {}
    for match in matches:
        key = match.group(1).strip()
        value = match.group(2).strip()
        result[key] = value
    
    # Return
    return result

#
# MARK: Main
#

def main():
    
    # Make sure we're running in the mac-mouse-fix project folder (We don't really need to be asserting this)
    cwd_name = os.path.basename(os.getcwd())
    assert cwd_name == 'mac-mouse-fix' or cwd_name == 'mac-mouse-fix-website' or cwd_name == 'mac-mouse-fix-update-feed'
    
    # Log
    print(f"Invoking run.py with cwd: {os.getcwd()}")
    
    # Find 'subcommands'
    def fill_subcommand_map():
        
        # Add compound_subcommands to subcommand_map
        subcommand_map.update(compound_subcommands)

        # Find all python scripts in the cwd
        python_script_paths = glob.glob('./**/*.py', recursive=True)

        # Filter weird stuff
        def passes_filter(script_path: str) -> bool:
            
            if 'site-packages'                 in script_path: return False # Ignore downloaded packages inside venvs
            if '__init__.py'                   in script_path: return False # Ignore python package directory markers
            if 'uvenv/bin/activate_this.py'    in script_path: return False # Not sure what this is [Sep 2025]
            if 'mac-mouse-fix-scripts/z_old'   in script_path: return False # Ignore 'old' scripts
            if 'mac-mouse-fix-scripts/shared'  in script_path: return False # Ignore library files
            if 'mac-mouse-fix-scripts/run.py'  in script_path: return False # Ignore this script
            # Passed all filters
            return True
        python_script_paths = list(filter(passes_filter, python_script_paths))

        # Create name -> path map for python scripts
        script_name_to_path = {}
        for p in python_script_paths:
            name = os.path.splitext(os.path.basename(p))[0]
            assert name not in script_name_to_path, f"Duplicate script name at 1. '{p}' 2. '{script_name_to_path[name]}'"
            script_name_to_path[name] = p

        # Add found scripts to 'subcommand map'
        subcommand_map.update(script_name_to_path)
    fill_subcommand_map()

    # Extract run.py args
    run_args   = []
    argv_other = []
    try:    spliti = sys.argv.index('--')
    except: spliti = None
    if spliti: # The args before `--` are for run.py
        run_args   = sys.argv[1:spliti]
        argv_other = [sys.argv[0]] + sys.argv[spliti+1:] # [Jul 2025] argv[0] isn't needed but it makes argv_other exactly match the "else" case.
        print(f"run.py: Split args into run.py args: {run_args}, and other args: {argv_other}")
    else:
        argv_other = sys.argv

    # Parse run.py args
    #   [Jul 2025] Maybe we could print_help_and_exit() if the user passes unknown args?
    arg_nopip = "--nopip" in run_args

    # Handle missing subcommand
    #   (Note: [Mar 2025] We do this after building subcommand_map so we can show the user the available subcommands.)
    if len(argv_other) < 2:
        print_help_and_exit('<no subcommand provided>')
        exit(1)

    # Process subcommand
    subcommand      = argv_other[1]
    subcommand_args = argv_other[2:]
    
    # Help
    if subcommand == '-h' or subcommand == 'help':
        print_help_and_exit(subcommand)

    # Check if provided command is known
    if not (subcommand in subcommand_map.keys()):
        print_help_and_exit(subcommand)

    # Implement compound subcommands
    if isinstance(subcommand_map[subcommand], list):
        for commandline_string_maker in subcommand_map[subcommand]:
            commandline_string = commandline_string_maker(shlex.join(run_args), shlex.join(subcommand_args))
            print(f'\nrun.py: Running clt {commandline_string} ...\n')
            commandline_list = shlex.split(commandline_string) # shlex allows you to escape whitespace inside a single arg with \ or "with quotes". Just like the shell!
            result = subprocess.run(commandline_list)
            print(f'\nrun.py: clt returned with code {result.returncode} ({commandline_string})\n')
            if result.returncode != 0:
                sys.exit(result.returncode)
        
        exit(0)        

    # Find paths
    script_path             = subcommand_map[subcommand]
    script_folder           = os.path.dirname(script_path)
    requiremements_paths    = glob.glob(f'{script_folder}/*requirements*.txt')
    assert len(requiremements_paths) <= 1, f"Multiple requirements.txt files found for script {subcommand}: {requiremements_paths}"
    requiremements_path     = requiremements_paths[0] if len(requiremements_paths) > 0 else None
    
    script_folder           = os.path.normpath(script_folder)                 # Normalize the path so it looks nicer when printing
    
    # Handle requirements
    
    python_interpreter = None
    if requiremements_path == None:
        python_interpreter = 'python3'
    else:
        
        # Get python path for the venv
        venv_python_path = os.path.join(venv_path, 'bin/python')

        # Define helper
        def create_venv(reuse_existing = True):

            # Check if the virtual environment exists
            #   Not recreating the venv every time speeds things up a lot.
            venv_exists = os.path.exists(venv_path)
            venv_seems_valid = os.path.exists(os.path.join(venv_path, 'pyvenv.cfg')) and os.path.exists(venv_python_path)
            
            if (not venv_seems_valid) or (not reuse_existing):
                
                if venv_exists:
                    # Log
                    print(f"\nrun.py: Deleting existing venv at ./{venv_path} ...")    
                    # Delete existing venv
                    subprocess.check_call(f"rm -r ./{venv_path}", text=True, shell=True)

                # Log
                print(f"\nrun.py: Creating venv at ./{venv_path} ...")
                
                # Create venv
                # Notes: 
                # - subprocess.check_call throws an error if the command returns non-zero. Otherwise returns 0
                subprocess.check_call(f"python3 -m venv {venv_path}", text=True, shell=True)
            else:
                # Log
                print(f"\nrun.py: Reusing existing venv at ./{venv_path}. (If there are problems try deleting the venv.)")
        
        # Define helper
        def install_requirements():
            print(f"\nrun.py: Installing requirements from ./{requiremements_path} ...")
            subprocess.check_call(f'./{venv_python_path} -m pip install -r "{requiremements_path}"', text=True, shell=True)

        # Do stuff
        if not arg_nopip: # --nopip turns off the superrr slow `pip install -r`, which does nothing if all the requirements are already installed. (Which is most of the time if you're iterating on something.)
                          # An alternative way to speed things up would be using `uv`. Test result: [Aug 2025] uv: 20ms, pip: 400ms
            create_venv()
            try:
                install_requirements()
            except Exception as e:
                print(f"\nrun.py: Installing requirements failed with exception:\n{e}\nTrying again without reusing existing venv...")
                create_venv(reuse_existing=False)
                install_requirements()

        # Tell the WORLD
        python_interpreter = f'./{venv_python_path}'
    
    # Log
    print(f"\nrun.py: Loading environ variables from ./{dotenv_path} ...")
    
    # Load environment variables defined in the .env file
    dotenv_vars = load_dotenv()
    
    # Analyze dotenv overlap
    overlapping_env_var_keys = [k for k in dotenv_vars.keys() if k in os.environ.keys()]
    dotenv_overlap = {k: dotenv_vars[k] for k in overlapping_env_var_keys}
    os_overlap = {k: os.environ[k] for k in overlapping_env_var_keys}
    
    # Validate
    if len(overlapping_env_var_keys) > 0:
        print(f"\nrun.py: WARN: .env defines vars that are already in the environment -.env will override - \nenv: {json.dumps(dotenv_overlap, ensure_ascii=False, indent=2)}\nos: {json.dumps(dict(os_overlap), ensure_ascii=False, indent=2)}")
    
    # Combine env_vars
    env_vars = os.environ | dotenv_vars
    
    # Log
    print(f"run.py: Running script at ./{script_path} with arguments: {subcommand_args} using interpreter {python_interpreter} ...\n")
    
    # Run script
    #   Notes:
    #   - We're passing env= here. If we don't do that, os.environ is automatically passed to the subprocess.
    script_result = subprocess.run([python_interpreter, script_path, *subcommand_args], env=env_vars)
    
    # Log 
    #   Log the script output verbatim 
    #   Update: This doesn't seem to work as I thought it would. stdout and stderr were always None, but the called-scripts' prints were printed to the command line anyways.
    # print(f'\nrun.py: script stderr: {script_result.stderr}', end='\n', file=sys.stderr)
    # print(f'run.py: script stdout: {script_result.stdout}', end='\n', file=sys.stdout)

    # Exit
    exit(script_result.returncode)    

#
# MARK: Call main
#
if __name__ == "__main__":
    main()
