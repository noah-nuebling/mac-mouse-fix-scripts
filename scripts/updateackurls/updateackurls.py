
""" 
    Problem this solves: Whenever I add new language with importstrings.py, 
        I have to update every single `Acknowledgements.xcstrings > 2: translations` url for every language! 
        This automates part of that. 
        Specifically, this edits the [markdown]({urls}) inside `Acknowledgements.xcstrings > 2: translations` so that they count up sequentially: {url_1}, {url_2}, {url_3}, ...
        [Dec 2025]
    Alternative solutions:
        - Change the way the `url_xx` replacement stuff works so I don't have to change them all when adding a new url at the start / middle [Dec 2025]
            See: `def replace_markdown_urls_with_format_specifiers`
"""

import glob

import mfutils

xcstrings_path = glob.glob('**/Acknowledgements.xcstrings', recursive=True)[0]

# Read xcstrings file
xcstrings_obj = mfutils.read_xcstrings_file(xcstrings_path)
assert xcstrings_obj != None

# Update urls inside "2: translations"
key = "2: translations"
for locale in xcstrings_obj["strings"][key]["localizations"]:
    if locale == 'en': continue
    
    translation = xcstrings_obj["strings"][key]["localizations"][locale]["stringUnit"]["value"]
    updated_translation = mfutils.replace_markdown_urls_with_format_specifiers(translation).md_string # Misuse replace_markdown_urls_with_format_specifiers() to make the url numbers in the translation sequential. ('Misuse' because the translations will already contain format specifiers) [Dec 2025]
    
    xcstrings_obj["strings"][key]["localizations"][locale]["stringUnit"]["value"] = updated_translation

# Write xcstrings file
mfutils.write_xcstrings_file(xcstrings_path, xcstrings_obj)