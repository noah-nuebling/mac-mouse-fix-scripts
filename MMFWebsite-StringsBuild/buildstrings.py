"""
This script is part of the build process for the Mac Mouse Fix Website. 
It compiles .xcstrings files, which hold the localizable strings for the website, to a nuxt-i18n-compatible .js file.
"""

#
# Imports
#

import argparse
import os
import glob
from collections import defaultdict
import json

import mflocales
import mfutils


#
# Constants
#

quotes_xcstrings_path   = "./locales/strings/Quotes.xcstrings"
xcstrings_root          = "./locales/strings/repo-root/"
# main_xcstrings_path     = "./locales/Localizable.xcstrings"

output_path             = "./locales/Localizable.js"

#
# Main
#
def main():
    
    # Get repo name
    target_repo = os.getcwd()
    repo_name = os.path.basename(os.path.normpath(target_repo))
    
    # Validate
    assert repo_name == 'mac-mouse-fix-website', f'This script is made for the mac-mouse-fix-website repo. The MarkdownBuild script does string-building for the main repo'
    
    # Log
    print(f'compile_website_strings: Begin')
    
    # Find mmf-project locales
    xcodeproj_path = mflocales.path_to_xcodeproj[repo_name]
    source_locale, translation_locales = mflocales.find_xcode_project_locales(xcodeproj_path)
    locales = [source_locale] + translation_locales
    
    # Log
    print(f'compile_website_strings: Found source_locale: {source_locale}, translation_locales: {translation_locales}')
    
    # Sort 
    #   We sort the locales - this way vue will display the languages in a nice order
    locales = mflocales.sorted_locales(locales, source_locale)
    
    # Load xcstrings files
    vue_xcstrings_list = []
    for xcstrings_path in glob.glob(xcstrings_root + '**/*.xcstrings'):
        vue_xcstrings_list.append(json.loads(mfutils.read_file(xcstrings_path)))
    quotes_xcstrings = json.loads(mfutils.read_file(quotes_xcstrings_path))
    all_xcstrings_list = vue_xcstrings_list + [quotes_xcstrings]
    
    # Get progress
    progress = mflocales.get_localization_progress(all_xcstrings_list, translation_locales)
    
    # Log
    print(f'compile_website_strings: Loaded vue .xcstrings files at {vue_xcstrings_list}, loaded Quotes.xcstrings from: {quotes_xcstrings_path}')
    
    # Compile
    
    # Compile xcstrings 
    vuestrings = {}
    vuelangs = []
    
    for locale in locales:

        # Get progress string 
        #   For this locale
        progress_display = str(int(100*progress[locale]["percentage"])) + '%' if locale != source_locale else ''

        # Compile list-of-languages dict
        #   (These are parsed as nuxt i18n `LocaleObject`s, (`code` and `name` fields) but we add other fields for our custom logic.)
        vuelangs.append({
            'code': locale,
            'name': mflocales.locale_to_language_name(locale, locale, include_flag=True),
            'progressDisplay': progress_display,
        })
        
        # Compile new vuestrings dict
        #   that @nuxtjs/i18n can understand
        #   Notes:
        #       - Note that we enabled fallbacks. This means the resulting Localizable.js file will aleady contain best-effort fallbacks for each string for each language. 
        #           So we don't need extra fallback logic inside the mmf-website code.
        vuestrings[locale] = {}
        for xcstrings in all_xcstrings_list:
            for key in xcstrings['strings']:
                value, locale_of_value = mflocales.get_translation(xcstrings, key, locale, fall_back_to_next_best_language=True)
                assert value != None # Since we enabled fallbacks, there should be a value for every string
                key = mflocales.remove_index_prefix_from_key(key)
                vuestrings[locale][key] = value
            
    # Render the compiled data to a .js file
    #   We could also render it to json, but json doesn't allow comments, which we want to add.
    vuestrings_json = json.dumps(vuestrings, ensure_ascii=False, indent=4)
    vuelangs_json = json.dumps(vuelangs, ensure_ascii=False, indent=4)
    js_string = f"""\
//
// AUTOGENERATED - DO NOT EDIT
// This file is automatically generated and should not be edited manually. 
// It was converted from an .xcstrings file, by the StringsBuild script (which is from the mac-mouse-fix-scripts repo).
//
export default {{
    "sourceLocale": "{source_locale}",
    "locales": {vuelangs_json},
    "strings":
{mfutils.add_indent(vuestrings_json, 4)}
    
}};
"""
    
    # Log
    print(f'compile_website_strings: Compiled strings dict for nuxtjs i18n')

    # Write to output_path
    with open(output_path, 'w') as file:
        file.write(js_string)
    
    # Log
    print(f'compile_website_strings: Wrote strings dict to {output_path}')
    
#
# Call main
#
if __name__ == '__main__':
    main()
