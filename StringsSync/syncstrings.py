
"""
For [.swift, .c, .m, .nib, ...] source files, Xcode automatically updates the .xcstrings files to the source files when building the project. However we also want to use .xcstrings files for other file types (.md, .vue and .js files). That's what this script is for.

We plan to automatically execute this script when source files (.md, .vue, .js) are compiled.
"""


# Imports

import tempfile
import json
import os
import argparse
import glob

import mfutils
import mflocales

from dataclasses import dataclass, astuple

#
# Constants
#

main_repo = { # Maybe we should reuse construct_path() from buildmd.py instead of this stuff, (or maybe just combine those two scripts into one)
    'source_paths': [ # The .md file from which we want to extract strings.
        'Markdown/Templates/Acknowledgements.md',
        'Markdown/Templates/Readme.md',
    ],
    'xcstrings_dir': "Markdown/Strings/", # The folder where all the .xcstrings files are, which we want to update with the strings from the .md files.
}
website_repo = {
    # 'quotes_tool_path': "./utils/quotesTool.mjs",
    # 'quotes_xcstrings_path': "./locales/Quotes.xcstrings",
    # 'main_xcstrings_path': "./locales/Localizable.xcstrings",

    'quotes': {
        'tool_path': './utils/quotesTool.mjs',
        'xcstrings_path': './locales/strings/Quotes.xcstrings',
    },
    'dotvue': {
        'sourcefile_glob': './**/*.vue', # Find source files with this pattern
        'xcstrings_root': './locales/strings/repo-root/', # Find .xcstrings files for source files relative to this path.
    }
}

#
# Types
# 


@dataclass
class StringsDataItem: # We convert this to json and then directly insert it into a .stringsdata file
    comment: str
    key: str
    value: str
    key_with_index_prefix: str|None    # This is not found in normal .stringsdata files, we use it for other stuff inside this script. Maybe it shouldn't be part of this dataclass.

@dataclass
class StringsDataItem_NoValue: # Use this if the source language string is defined in the .xcstrings file instead of being extracted from the source file together with the key and comment.
    comment: str
    key: str
    key_with_index_prefix: str|None


#
# Main
#
def main():
    
    # Get repo name
    target_repo = os.getcwd()
    repo_name = os.path.basename(os.path.normpath(target_repo))
    
    # Extract source_files -> .stringsdata file
    if repo_name == 'mac-mouse-fix-website':
        
        # Log
        print(f"syncstrings.py: Syncing {website_repo['quotes']['xcstrings_path']} ...")
        print("")
        
        #
        # Quotes
        #

        # Extract strings from quotes.js
        # Note: 
        #   I ran into a problem where calling node failed, it was because /usr/local/bin (where node is located) was not in PATH. Restarting vscode fixed it.

        # TODO: 
        #   Also extract quotes.translation-disclaimer.[...] strings and quotes.source.[...] strings.

        quotes = json.loads(mfutils.runclt(['node', website_repo['quotes']['tool_path']], cwd=target_repo))
        extracted_strings: list[StringsDataItem] = []
        for quote in quotes:
            key = quote['quoteKey']
            value = quote['englishQuote']
            comment = ' ' # Setting it to ' ' deletes any comments that have been set in the Xcode .xcstrings GUI
            if quote['originalLanguage'] != 'en':
                original_language   = mflocales.locale_to_language_name(quote['originalLanguage'], 'en', False)
                original_quote      = quote['originalQuote']
                comment = f'The original language of this quote is {original_language} - {original_quote}'
            
            extracted_strings.append(StringsDataItem(comment, key, value, None)) # Set key-with-index to None to prevent adding index-prefixes in the .xcstrings file.
        
        # Call subfunc
        quotes_xcstrings_path = os.path.join(target_repo, website_repo['quotes']['xcstrings_path'])
        update_xcstrings(quotes_xcstrings_path, extracted_strings, did_extract_values=True)
        
        #
        # .vue files
        #

        # Glob for .vue files
        vuefile_paths = glob.glob(website_repo['dotvue']['sourcefile_glob']);

        # Log
        print(f"syncstrings.py: Syncing .vue files: {vuefile_paths}")
        print("")

        # Extract strings from .vue files
        for vue_path in vuefile_paths:
    
            # Construct path to xcstrings file
            xcstrings_path = os.path.splitext(vue_path)[0] + '.xcstrings'
            xcstrings_path = os.path.join(website_repo['dotvue']['xcstrings_root'], xcstrings_path)
            xcstrings_path = os.path.normpath(xcstrings_path) # Strips out redundant /./ segments from the path.

            # Log
            print(f"syncstrings.py: Syncing {vue_path} ◢")
            print(f"                                               {xcstrings_path}")

            # Load source file
            vue_content = None
            with open(vue_path, 'r') as file:
                vue_content = file.read()
            
            # Declare loop result
            extracted_strings: list[StringsDataItem_NoValue] = []
            
            for st in mflocales.get_localizable_strings_from_website_source_code(vue_content):
                
                # Print
                print(f"syncstrings.py:\nk:\n{st.key}\nc:\n{st.comment}\n-----------------------\n")

                # Remove all mdlink urls from extracted strings
                #       And replace with {url1}, {url2}, etc.
                #   TODO: Figure out if / how to do this for the website.
                # ui_string = mfutils.replace_markdown_urls_with_format_specifiers(ui_string).md_string

                # Store result
                #   In .stringsdata format
                # extracted_strings.append(StringsDataItem_NoValue(st.comment, st.key, st.key_with_index_prefix))
                extracted_strings.append(StringsDataItem(st.comment, st.key, st.value, st.key_with_index_prefix))

            # Call subfunc
            if len(extracted_strings) > 0:
                update_xcstrings(xcstrings_path, extracted_strings, did_extract_values=False)
            else:
                print(f"syncstrings.py: No localizable strings found in {xcstrings_path}. Skipping.")
        
    elif repo_name == 'mac-mouse-fix':
        
        # Log
        print(f"syncstrings.py: Syncing .xcstrings files inside {repo_name} ...")
        print("    (Most .xcstrings file are automatically synced by Xcode when building the project, but here we sync the ones not managed by Xcode)")
        print("")

        # Extract strings from source_files        
        for source_file in main_repo['source_paths']:

            # Construct path to xcstrings file
            stem = os.path.splitext(os.path.basename(source_file))[0]
            xcstrings_path = os.path.join(main_repo['xcstrings_dir'], (stem + '.xcstrings'))

            # Log
            print(f"syncstrings.py: Syncing {xcstrings_path}")

            # Load content
            content = None
            with open(source_file, 'r') as file:
                content = file.read()
            
            # Declare result
            extracted_strings: list[StringsDataItem] = []

            for st in mflocales.get_localizable_strings_from_markdown(content):
                
                ui_string = st.value

                # Print
                print(f"syncstrings.py:\nk:\n{st.key}\nv:\n{ui_string}\nc:\n{st.comment}\n-----------------------\n")
                  
                # Remove indentation from ui_string 
                #   (Otherwise translators have to manually add indentation to every indented line)
                #   (When we insert the translated strings back into the .md we have to add the indentation back in.)
                
                old_indent_level, old_indent_char = mfutils.get_indent(ui_string)
                ui_string = mfutils.set_indent(ui_string, 0, ' ')
                new_indent_level, new_indent_char = mfutils.get_indent(ui_string)
                
                if old_indent_level != new_indent_level:
                    print(f'syncstrings.py: [Changed {st.key} indentation from {old_indent_level}*"{old_indent_char or ''}" -> {new_indent_level}*"{new_indent_char or ''}"]\n')

                # Remove all mdlink urls from extracted strings
                #       And replace with {url1}, {url2}, etc.
                #   Discussion: We do this so there's less margin for error for localizers. 
                ui_string = mfutils.replace_markdown_urls_with_format_specifiers(ui_string).md_string

                # Store result
                #   In .stringsdata format
                extracted_strings.append(StringsDataItem(st.comment, st.key, ui_string, st.key_with_index_prefix))

            # Call subfunc
            update_xcstrings(xcstrings_path, extracted_strings, did_extract_values=False)

    else:
        assert False
#
# Helper
#

def update_xcstrings(xcstrings_path: str, extracted_strings: list[StringsDataItem|StringsDataItem_NoValue], did_extract_values: bool):

    # Validate extracted strings exist
    assert extracted_strings != None and len(extracted_strings) > 0, f"syncstrings.py: extracted_strings are unexpectedly 'None'. Don't call update_xcstrings if there's nothing to extract. Called for xcstring_path: {xcstrings_path}"

    # Validate: xcstrings file exists
    assert os.path.exists(xcstrings_path), f"syncstrings.py: Tried to update {xcstrings_path}, but the file doesn't exist. If you create the file, make sure to add it to some dummy target in Xcode, so that the strings are included in Xcode's .xcloc exports. (But don't add the .xcstrings file to a real target, otherwise it'll be included in the built bundle, where it will be unused and take up some space.)"

    # Create .stringsdata file
    #   Notes on stringsTable name: 
    #       Each .xcstrings file represents one stringsTable (and should be (has to be?) named after it). 
    #       See apple docs for more info on strings tables.
    
    xcstrings_name = os.path.basename(xcstrings_path)
    strings_table_name = os.path.splitext(xcstrings_name)[0]
    stringsdata_content = {
        "source": "garbage/path.txt",
        "tables": {
            strings_table_name: extracted_strings
        },
        "version": 1
    }
    stringsdata_path = None
    with tempfile.NamedTemporaryFile(delete=False, suffix=".stringsdata", mode='w') as file: # Not sure what the 'delete' option does
        # write data
        json.dump(stringsdata_content, file, indent=2, cls=mfutils.JSONEncoder)
        # Store file path
        stringsdata_path = file.name
    
    print(f"syncstrings.py: Created .stringsdata file at: {stringsdata_path}")
    
    # 
    # Modfiy .xcstrings file: 
    # 

    xcstrings_obj = mfutils.read_xcstrings_file(xcstrings_path)
    source_language = xcstrings_obj['sourceLanguage']
    assert source_language == 'en'
    
    # 1. Modification: Set the 'extractedState' for all strings
    
    extraction_state = 'extracted_with_value' if did_extract_values else 'extracted'
    for key, info in xcstrings_obj['strings'].items():
        info['extractionState'] = extraction_state

    print(f"syncstrings.py: Set the extractionState of all strings to '{extraction_state}'")

    # 2. Modification: Set the 'state' of all 'source_language' ui strings to 'new'
    #   -> If we have accidentally changed them, their state will be 'translated' 
    #       instead which will prevent xcstringstool from updating them to the new value from the source file.

    #   -> All these modifications are necessary so that xcstringstool updates everything (I think)

    if did_extract_values:
        for key, info in xcstrings_obj['strings'].items():
            if 'localizations' in info.keys() and source_language in info['localizations'].keys():
                info['localizations'][source_language]['stringUnit']['state'] = 'new'
            else:
                pass
                # assert False

    # 3. Modification: Remove indexes from keys (e.g. 003:some.key -> some.key)
    #   Explanation: We have to first remove all the prefixes from the .xcstrings file before calling xcstringstool to synchronize.
    #       Otherwise I think the syncing would break if we ever change the order that the keys appear in the template.
    for key in list(xcstrings_obj['strings'].keys()):
        key: str = key

        # Get new, index-less key
        key_without_index = mflocales.remove_index_prefix_from_key(key)

        # Guard
        if key == key_without_index:
            continue

        # Move content from key -> new_key
        xcstrings_obj['strings'][key_without_index] = xcstrings_obj['strings'][key]
        del xcstrings_obj['strings'][key]

    # Write modified .xcstrings file
    mfutils.write_xcstrings_file(xcstrings_path, xcstrings_obj)   

    # Use xcstringstool to sync the .xcstrings file with the .stringsdata
    #   This is the core of what we're trying to do here.
    developer_dir = mfutils.runclt("xcode-select --print-path")
    stringstool_path = os.path.join(developer_dir, 'usr/bin/xcstringstool')
    result = mfutils.runclt(f"{stringstool_path} sync {xcstrings_path} --stringsdata {stringsdata_path}")
    print(f"syncstrings.py: ran xcstringstool to update {xcstrings_path}. Result: '{result}'")
    
    #
    # Modify .xcstrings file
    # 

    xcstrings_obj = mfutils.read_xcstrings_file(xcstrings_path)

    # 1. Modification: Set the 'extractedState' for all strings to 'manual'
    #   Otherwise Xcode won't export them and also delete all of them or give them the 'Stale' state
    #   (We leave strings 'stale' which this analysis determined to be stale)
    
    for key, info in xcstrings_obj['strings'].items():
        if info.get('extractionState', None) == 'stale': # I think if there is no extractionState, that basically means 'extracted_without_value'. In that case we also want to set the state to 'manual'.
            pass
        else:
            info['extractionState'] = 'manual'

    # 2. Modification: Add indexes back to keys (e.g. some.key -> 003:some.key)
    xcstrings_obj_keys = set(xcstrings_obj['strings'].keys())
    extracted_from_template_keys = set(map(lambda item: item.key, extracted_strings))
    assert xcstrings_obj_keys == extracted_from_template_keys, f"Something went wrong.\nxcstrings_obj_keys:\n{xcstrings_obj_keys}\n\nextracted_from_template_keys:\n{extracted_from_template_keys}\n\nsymmetric difference:\n{xcstrings_obj_keys.symmetric_difference(extracted_from_template_keys)}"
    for item in extracted_strings:
        # Skip none
        #   Callers can set key_with_index_prefix to None to avoid adding an index prefix.
        if item.key_with_index_prefix == None:
            continue
        # Move content from key -> key_with_index_prefix
        xcstrings_obj['strings'][item.key_with_index_prefix] = xcstrings_obj['strings'][item.key]
        del xcstrings_obj['strings'][item.key]

    # Write modified .xcstrings file
    mfutils.write_xcstrings_file(xcstrings_path, xcstrings_obj)
    print(f"syncstrings.py: Set the extractionState of all strings to 'manual'")

#
# Call main
#
if __name__ == "__main__":
    main()
