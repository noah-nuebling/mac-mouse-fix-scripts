#!/usr/bin/env python3

# Credits to Claude 4.5

import os
import sys
import hashlib
import ctypes
from ctypes import *
from pathlib import Path
from typing import Any
import subprocess
import shlex
from glob import glob
from textwrap import dedent

#
# Define helper functions
#

def loadfn(restype, fn, argtypes): # Reduce boilerplate when calling c-functions. [Oct 2025]
    fn.restype = restype
    fn.argtypes = argtypes
    return fn

def runclt(command_args): # Minimal drop-in replacement for mfutils.runclt (Can't use that since this has to run on localizer's computers.) [Oct 2025] || When we add explicit types here like `str|list[str]` then the script does nothing when called by double-clicking in Finder. Not sure what's going on.
    
    command = []
    if isinstance(command_args, str):
        command = shlex.split(command_args)
    elif isinstance(command_args, list):
        command = command_args
    
    subprocess.call(command)

def show_alert(msg):
    # Using show_alert() since print() is not visible when launching the script by double-clicking the enclosing app-bundle [Oct 2025]
    #       Caution: If msg contains double-quote (") or escaped single-quote (\') here it breaks the osascript. Not sure why. [Oct 2025]
    #                shlex.quote() doesn't help. Not sure if it's worth switching to CFUserNotificationDisplayAlert() or CFUserNotificationDisplayAlert()
    
    runclt(['osascript', '-e', f'display dialog "{msg}" with title "" buttons {{"OK"}} default button 1'])

    print(f"Showing alert: {msg}") # Print the msg as a backup for debugging in case the osascript fails for some reason.

# Do stuff
if 1:

    # Undo App Translocation, so we can access the .xcloc files next to the .app bundle
    #   (Also see AppTranslocationManager.m from Mac Mouse Fix)
    if 1:
        script_path = Path(__file__).resolve()
        app_path = script_path.parent.parent.parent # Get the app bundle path (we're in Contents/MacOS)
        
        # Load C-functions from System frameworks
        
        CFURLCreateFromFileSystemRepresentation: Any = None
        CFURLGetFileSystemRepresentation: Any = None
        SecTranslocateCreateOriginalPathForURL: Any = None

        if 1:
            cf = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
            security = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/Security.framework/Security')

            # CFURLRef CFURLCreateFromFileSystemRepresentation(CFAllocatorRef allocator, const UInt8 *buffer, CFIndex bufLen, Boolean isDirectory);
            CFURLCreateFromFileSystemRepresentation = loadfn(c_void_p, cf.CFURLCreateFromFileSystemRepresentation, [c_void_p, c_char_p, c_long, c_bool]) 

            # Boolean CFURLGetFileSystemRepresentation(CFURLRef url, Boolean resolveAgainstBase, UInt8 *buffer, CFIndex maxBufLen);
            CFURLGetFileSystemRepresentation = loadfn(c_bool, cf.CFURLGetFileSystemRepresentation, [c_void_p, c_bool, c_char_p, c_long])

            # CFURLRef SecTranslocateCreateOriginalPathForURL(CFURLRef translocatedPath, CFErrorRef *error)
            SecTranslocateCreateOriginalPathForURL = loadfn(c_void_p, security.SecTranslocateCreateOriginalPathForURL, [c_void_p, c_void_p])

        # Convert path -> CFURL
        app_path_bytes = str(app_path).encode('utf-8')
        cfurl = CFURLCreateFromFileSystemRepresentation(None, app_path_bytes, len(app_path_bytes), True)

        # Get original (untranslocated) path using Security.framework
        original_cfurl = SecTranslocateCreateOriginalPathForURL(cfurl, None)

        # Convert CFURL -> path
        original_path = ""
        if original_cfurl:
            PATH_MAX = 4096 # Not sure what to use here. `getconf PATH_MAX /` returns 1024 on my 2018 Mac Mini [Oct 2025]
            buffer = ctypes.create_string_buffer(PATH_MAX)
            if CFURLGetFileSystemRepresentation(original_cfurl, True, buffer, PATH_MAX):
                original_path = Path(buffer.value.decode('utf-8'))

        # Check translocation
        if not original_path or app_path == original_path: # Not sure when `not original_path` happens
            if 0: show_alert(f"- App doesn't seem to be translocated at path '{app_path}'. Proceeding...")
        else:
            if 0: show_alert(f"- App seems to be translocated ('{app_path}' -> '{original_path}'). Removing quarantine and relaunching....")
            
            runclt(f'xattr -cr "{original_path}"')
            runclt(f'open -n "{original_path}"')
            sys.exit(0)

    # Navigate to working directory (This script in .app/Contents/MacOS/ -> go up to parent folder of the .app bundle)
    work_dir = Path(__file__).resolve().parent.parent.parent.parent
    os.chdir(work_dir)

    # Deduplicate .jpeg files using hardlinks
    if 1:
        seen = {}
        for file in work_dir.rglob('*.jpeg'):
            if not file.is_file():
                continue

            checksum = hashlib.md5(file.read_bytes()).hexdigest()

            if checksum not in seen:
                seen[checksum] = str(file)
            else:
                original = seen[checksum]
                file.unlink()
                os.link(original, str(file))

    # Find xcloc files
    xcloc_files = glob("*.xcloc")
    if not xcloc_files:
        show_alert(f"Error: Found no .xcloc files in folder:\n{os.getcwd()}")
        exit(1)    

    # Compress .xcloc files using tar (zip doesn't preserve the hardlink deduplication)
    runclt(['tar', '-czf', 'Compressed Localizations (Upload This).tar.gz', *xcloc_files])

    # Log success message 
    show_alert(dedent(f"""\
        Created archive:
        'Compressed Localizations (Upload This).tar.gz'

        Containing localization files:
        {xcloc_files}

        You can upload the compressed localizations via:

        GitHub: 
        https://redirect.macmousefix.com/?target=mmf-localization-contribution

        Email:  
        https://redirect.macmousefix.com/?target=mailto-noah\
    """))