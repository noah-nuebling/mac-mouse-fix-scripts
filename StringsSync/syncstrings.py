
"""
For [.swift, .c, .m, .nib, ...] source files, Xcode automatically updates the .xcstrings files to the source files when building the project. However we also want to use .xcstrings files for other file types (.md, .vue and .js files). That's what this script is for.

We plan to automatically execute this script when source files (.md, .vue, .js) are compiled.
"""


# Imports

import tempfile
import json
import os
import argparse

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
    'quotes_tool_path': "./utils/quotesTool.mjs",
    'quotes_xcstrings_path': "./locales/Quotes.xcstrings",
    'main_xcstrings_path': "./locales/Localizable.xcstrings",
}

#
# Types
# 


@dataclass
class ExtractedString:
    comment: str
    key: str
    value: str

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
        print(f"syncstrings.py: Syncing {website_repo['quotes_xcstrings_path']} ...")
        print("")
        
        # Extract strings from quotes.js
        # Note: 
        #   I ran into a problem where calling node failed, it was because /usr/local/bin (where node is located) was not in PATH. Restarting vscode fixed it.
        quotes = json.loads(mfutils.runclt(['node', website_repo['quotes_tool_path']], cwd=target_repo))
        extracted_strings: list[ExtractedString] = []
        for quote in quotes:
            key = quote['quoteKey']
            value = quote['englishQuote']
            comment = ' ' # Setting it to ' ' deletes any comments that have been set in the Xcode .xcstrings GUI
            if quote['originalLanguage'] != 'en':
                original_language   = mflocales.locale_to_language_name(quote['originalLanguage'], 'en', False)
                original_quote      = quote['originalQuote']
                comment = f'The original language of this quote is {original_language} - {original_quote}'
            
            extracted_strings.append(ExtractedString(comment, key, value))
        
        # Call subfunc
        quotes_xcstrings_path = os.path.join(target_repo, website_repo['quotes_xcstrings_path'])
        update_xcstrings(quotes_xcstrings_path, extracted_strings)
        
        # Log
        print(f"syncstrings.py: Not syncing {website_repo['main_xcstrings_path']}, since that's not implemented, yet.")
        print("")
        
        # Notes:
        # - Syncing Localizable.strings would require us use a NSLocalizedString-like macro throughout our .vue files.
        #   (So we can extract the strings from the source code with a regex)
        #   This would require big refactor and is not worth it right now, I think.
        
        # Extract strings from .vue files
        # ...
        
        # Call subfunc
        # ...
        
    elif repo_name == 'mac-mouse-fix':
        
        # Log
        print(f"syncstrings.py: Syncing .xcstrings files inside {repo_name} ...")
        print("    (Most .xcstrings file are automatically synced by Xcode when building the project, but here we sync the ones not managed by Xcode)")
        print("")

        # Extract strings from source_files        
        for source_file in main_repo['source_paths']:
            
            # Declare result
            extracted_strings: list[ExtractedString] = []

            # Construct path to xcstrings file
            stem = os.path.splitext(os.path.basename(source_file))[0]
            xcstrings_path = os.path.join(main_repo['xcstrings_dir'], (stem + '.xcstrings'))

            # Log
            print(f"syncstrings.py: Syncing {xcstrings_path}")

            # Load content
            content = None
            with open(source_file, 'r') as file:
                content = file.read()
            
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
                extracted_strings.append(ExtractedString(st.comment, st.key, ui_string))

            # Call subfuncs
            update_xcstrings(xcstrings_path, extracted_strings)
    
    else:
        assert False
#
# Helper
#

def update_xcstrings(xcstrings_path: str, extracted_strings: list[ExtractedString]):

    # Validate: xcstringsf file exists
    assert os.path.exists(xcstrings_path), f"Tried to update {xcstrings_path}, but the file doesn't exist. If you create the file, make sure to add it to some dummy target in Xcode, so that the strings are included in Xcode's .xcloc exports. (But don't add the .xcstrings file to a real target, otherwise it'll be included in the built bundle, where it will be unused.)"

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
    
    # Set the 'extractedState' for all strings to 'extracted_with_value'
    #   Also set the 'state' of all 'sourceLanguage' ui strings to 'new'
    #   -> If we have accidentally changed them, their state will be 'translated' 
    #       instead which will prevent xcstringstool from updating them to the new value from the source file.
    #   -> All this is necessary so that xcstringstool updates everything (I think)
    
    xcstrings_obj = mfutils.read_xcstrings_file(xcstrings_path)
    source_language = xcstrings_obj['sourceLanguage']
    assert source_language == 'en'
    for key, info in xcstrings_obj['strings'].items():
        info['extractionState'] = 'extracted_with_value'
        if 'localizations' in info.keys() and source_language in info['localizations'].keys():
            info['localizations'][source_language]['stringUnit']['state'] = 'new'
        else:
            pass
            # assert False
     
    mfutils.write_xcstrings_file(xcstrings_path, xcstrings_obj)   
    print(f"syncstrings.py: Set the extractionState of all strings to 'extracted_with_value'")
        
    # Use xcstringstool to sync the .xcstrings file with the .stringsdata
    developer_dir = mfutils.runclt("xcode-select --print-path")
    stringstool_path = os.path.join(developer_dir, 'usr/bin/xcstringstool')
    result = mfutils.runclt(f"{stringstool_path} sync {xcstrings_path} --stringsdata {stringsdata_path}")
    print(f"syncstrings.py: ran xcstringstool to update {xcstrings_path} Result: {result}")
    
    # Set the 'extractedState' for all strings to 'manual'
    #   Otherwise Xcode won't export them and also delete all of them or give them the 'Stale' state
    #   (We leave strings 'stale' which this analysis determined to be stale)
    xcstrings_obj = mfutils.read_xcstrings_file(xcstrings_path)
    for key, info in xcstrings_obj['strings'].items():
        if info['extractionState'] == 'stale':
            pass
        else:
            info['extractionState'] = 'manual'

    # Write modified .xcstrings file
    mfutils.write_xcstrings_file(xcstrings_path, xcstrings_obj)
    print(f"syncstrings.py: Set the extractionState of all strings to 'manual'")

#
# Call main
#
if __name__ == "__main__":
    main()
