
"""

This script compiles markdown documents which are translatable or which have dynamic content.

"""

#
# Imports
#
import sys
import argparse
import requests
# import json
import pycountry
import datetime
import babel.dates
import re
import pathlib
import urllib.parse
import string
import os
import math
from pprint import pprint # For debugging
import json

import mfutils
import mflocales

#
# Document paths
#
# Explanation:
#   This script takes a `template .md` file plus an `.xcstrings` file and then compiles them into a series of proper, localized `compiled .md` - one for each locale in the .xcstrings file.
#   
#   The `template .md`, `.xcstrings`, and `compiled .md` files all have the same filename stem, but with different extensions. 
#   They are also found in different directories. 
#   Example where the 'filename stem' is 'Readme':
#       Template: 
#           ./Markdown/Templates/Readme.md
#       XCStrings: 
#           ./Markdown/Strings/Readme.xcstrings
#       Compiled: 
#           ./Readme.md                                     (English aka 'development language' document)
#           ./Markdown/LocalizedDocuments/de/Readme.md      (German Document)
#           ./Markdown/LocalizedDocuments/vi/Readme.md      (Vietnamese Document)
#           ...                                             (And so on)
#  
#   To compile one of these documents, run this script and pass in the `filename stem` ('Readme' in this example) as the `--document`
#   
# Notes:
#   - All the hardcoded paths in this script are relative to the root directory of the repo - we expect this script to be run from the repo root.

template_root = "Markdown/Templates"                                        # The script will look for document templates in this directory (It's relative to the repo root)
xcstrings_root = "Markdown/Strings"                                         # The script will look for xcstrings files in this dir
compiled_doc_root__development_locale = ""                                  # Compiled documents in the 'development language' (English) will be put into this dir
compiled_doc_root__translated_locales = "Markdown/LocalizedDocuments"       # Compiled documents in translated languages will be put into this dir

from enum import Enum
class DocType(Enum):
    TEMPLATE = 2
    XCSTRINGS = 1
    COMPILED_DOC = 3

def get_document_keys():
    
    # Returns the filename stems of all files in the 'template_root' folder
    # These filename stems can be used as 'document keys' - they identify a certain document that we might want to compile.


    result_lowercase = []
    result = []

    for item in os.listdir(template_root):

        # Get stem
        filename_stem, ext = os.path.splitext(item)

        # Guard
        if not os.path.isfile(item): continue
        if not ext == '.md': continue

        # Store result
        result.append(filename_stem)

        # Validate
        assert filename_stem.lower() not in result_lowercase, f"Found duplicate template name: {item}. (Checked case-insensitively.) (This is a problem because the template names determine the document keys, which we might want to use case-insensitively. So the template names need to be case-insensitively unique.)"
        result_lowercase.append(filename_stem.lower())
    
    return result

def path_to_repo_root(path):
    parent_count = len(pathlib.Path(path).parents)
    root_path = '../' * (parent_count-1)
    return root_path

def path_to_compiled_doc_root(thisdoc_path: str, locale: str, development_locale: str):
    
    # Construct docroot for locale
    docroot = None
    if locale == development_locale:
        docroot = compiled_doc_root__development_locale
    else:
        docroot = os.path.join(compiled_doc_root__translated_locales, locale)
    
    # Validate
    assert(thisdoc_path.startswith(docroot))

    # Get thisdoc path relative to docroot.
    thisdoc_path_relative = thisdoc_path.removeprefix(docroot)

    # Construct path from thisdoc to docroot
    parent_count = len(pathlib.Path(thisdoc_path_relative).parents)
    root_path = '../' * (parent_count-1)

    # Return
    return root_path

def construct_path(filename_stem: str, doc_type: DocType, locale: str|None = None, development_locale: str = 'en'):

    match doc_type:
        case DocType.TEMPLATE:
            return os.path.join(template_root, filename_stem + '.md')
        
        case DocType.XCSTRINGS:
            return os.path.join(xcstrings_root, filename_stem + '.xcstrings')
        
        case DocType.COMPILED_DOC:

            assert locale != None and len(locale) > 0

            if (locale == development_locale):
                return os.path.join(compiled_doc_root__development_locale, filename_stem + '.md')
            else:
                return os.path.join(compiled_doc_root__translated_locales, locale, filename_stem + '.md')
        
        case _:
            assert False
            return None

#
# Constants
#

# !! Amend custom_field_labels if you change the UI strings on Gumroad !!

show_locale_threshold = 0.5 # If the translation progress of a locale is greater than this, we show it in the locale picker. (E.g. 0.6 means: Only show locales that are more than 60% complete) || Note: Keep this in sync with `showLocaleThreshold` on the MMF Website.

sales_count_rounder = 100 # Round sales counts to multiple of this number. This is to prevent the acknowledgements file from changing on every sale, which clogs up commit history a bit.

gumroad_sales_cache_file = "Markdown/gumroad_sales_cache.json"  # DONT leak this. If you move/rename this, make sure it's covered by .gitignore. It's inside the Markdown folder to be a bit more hidden.
gumroad_sales_cache_shelf_life = 24                             # In hours

gumroad_custom_field_labels_name = ["Your Name – Will be displayed in the Acknowledgements if you purchase the 2. or 3. Option"]
gumroad_custom_field_labels_message = ["Your message (Will be displayed next to your name in the Acknowledgements if you purchase the 3. Option)", "Your message – Will be displayed next to your name in the Acknowledgements if you purchase the 3. Option"]
gumroad_custom_field_labels_dont_display = ["Don't publicly display me as a 'Generous Contributor' under 'Acknowledgements'"]

gumroad_product_id_euro = "FP8NisFw09uY8HWTvVMzvg=="
gumroad_product_id_dollar = "OBIdo8o1YTJm3lNvgpQJMQ=="
gumroad_product_ids = [gumroad_product_id_euro, gumroad_product_id_dollar] # 1st is is the € based product (Which we used in the earlier MMF 3 Betas, but which isn't used anymore), 2nd id is $ based product (mmfinappusd)

gumroad_api_base = "https://api.gumroad.com"
gumroad_sales_api = "/v2/sales"
gumroad_date_format = '%Y-%m-%dT%H:%M:%SZ' # T means nothing, Z means UTC+0 | The date strings that the gumroad sales api returns have this format

name_blacklist = ['mail', 'paypal', 'banking', 'beratung', 'macmousefix'] # TODO: Add Iam | When gumroad doesn't provide a name we use part of the email as the display name. We use the part of the email before @, unless it contains one of these substrings, in which case we use the part of the email after @ but with the `.com`, `.de` etc. removed
nbsp = '&nbsp;'  # Non-breaking space. &nbsp; doesn't seem to work on GitHub. (Edit: &nbsp; seems to work on GH now.) Tried '\xa0', too. See https://github.com/github/cmark-gfm/issues/346

#
# Main
#
def main():
    
    # Get document keys
    document_keys = get_document_keys()
    
    # Parse args
    parser = argparse.ArgumentParser()
    parser.add_argument("--api_key", default=os.getenv("GUMROAD_API_KEY"), help="Provide a Gumroad API key using the `--api_key` command line argument or by setting the GUMROAD_API_KEY environment variable. You can retrieve your Access Token in the GitHub Secrets or in the Gumroad Settings under Advanced.")
    parser.add_argument("--document"), # We used to get the document through .getenv, too but that can be confusing I think
    parser.add_argument("--no_api", action='store_true') # no_api option is not necessary anymore now since we have caching to make things fast when testing.
    args = parser.parse_args()

    document_key = args.document
    gumroad_api_key = args.api_key
    no_api = args.no_api
    
    # Validate --api_key
    if gumroad_api_key == None or len(gumroad_api_key) == 0:
        print("No gumroad api key provided.")
    else:
        print(f"Working with gumroad api key: {gumroad_api_key}")
    
    # Guard --document exists
    document_key_was_provided = isinstance(document_key, str) and document_key != ''
    if not document_key_was_provided:
        print("No document key provided. Provide one using the '--document' command line argument")
        sys.exit(1)
    
    # Adjust capitalization of --document
    #   So that the clt arg becomes effectively case-insensitive
    if False:
        for k in document_keys:
            if k.lower() == document_key.lower():
                document_key = k
                break
    
    # Validate --document
    document_key_is_valid = document_key in document_keys
    if not document_key_is_valid:
        print(f"Unknown document key '{document_key}'. Valid document keys: {list(document_keys)}")
        sys.exit(1)
    
    # Log
    print(f"Generating document: {document_key}")
    
    # Construct paths to .xcstrings file
    xcstrings_path = construct_path(document_key, DocType.XCSTRINGS)

    # Load xcstrings file as python object
    xcstrings = []
    with open(xcstrings_path, 'r') as file:
        xcstrings = json.load(file)
    
    # Remove index-prefixes from keys inside xcstrings obj (e.g. 003:some.key -> some.key)
    for key in list(xcstrings['strings'].keys()):

        key_without_index = mflocales.remove_index_prefix_from_key(key)

        xcstrings['strings'][key_without_index] = xcstrings['strings'][key]
        del xcstrings['strings'][key]

    # Find locales
    development_locale, translation_locales = mflocales.find_xcode_project_locales(mflocales.path_to_xcodeproj['mac-mouse-fix'])
    
    # Get translation progress
    translation_progress = mflocales.get_localization_progress([xcstrings], translation_locales)
    
    # Compile locales
    iterated_locales = translation_locales.copy() 
    iterated_locales.append(development_locale)
    
    # Sort locales
    #   Don't sort these while iterating - will lead to bugs
    iterated_locales = mflocales.sorted_locales(iterated_locales, development_locale)
    
    # Iterate locales
    for locale in iterated_locales:
        
        # Get document root
        #   The folder that the output files for this locale go into
        # document_root = get_destination_root(locale, development_locale)
        
        # Get document subpath
        # document_subpath = document_key_to_filename_map[document_key]
        
        # Get src and dst paths

        template_path = construct_path(document_key, DocType.TEMPLATE)
        destination_path = construct_path(document_key, DocType.COMPILED_DOC, locale, development_locale)
        
        # Load template
        template = ""
        with open(template_path, ) as f:
            template = f.read()

        # Do conditional rendering
        #   Explanation: 
        #   - In the template md files we can wrap sections in `{% if <some condition> %}` and `{% endif %}` (we also call these 'jinja-style if-blocks') to render the section only in case <some condition> is set to `True` in the render_condition_dict.
        #   - Using show_localization_progress, we hide the note about the localization progress in case the locale is 100% translated. This follows the logic we use for showing the localization progress on the MMF Website.
        render_condition_dict = {
            'show_localization_progress': (locale != development_locale) and (translation_progress[locale]['percentage'] < 1.0),
        }
        template = mfutils.conditional_render_with_jinja_if_blocks(template, render_condition_dict)

        # Log
        print('buildmd.py: Inserting translations into template at path {}...'.format(template_path))

        # Decare loop state
        missing_translations = []

        # Translate the template
        for st in mflocales.get_localizable_strings_from_markdown(template):
            
            # Get the translated value
            translation, best_locale = mflocales.get_translation(xcstrings, st.key, locale)

            # Log
            if best_locale != locale:
                missing_translations.append({ "key": st.key, "best_locale": best_locale })
            
            # Insert urls from the template into the translation
            urls_from_template = mfutils.replace_markdown_urls_with_format_specifiers(st.value).removed_urls # We could cache the urls between languages but it doesn't seem to produce noticable slowdown
            translation = mfutils.replace_format_specifiers_with_markdown_urls(translation, urls_from_template)

            # Apply the original indentation to the translation
            indent_level, indent_char = mfutils.get_indent(st.value)
            assert indent_char == ' ' or indent_char == None
            translation = mfutils.set_indent(translation, indent_level, ' ')
            
            # Insert translation into template
            template = template.replace(st.full_match, translation)
        
        # Log missing translations
        if len(missing_translations) > 0:
            s = ',\n'.join(list(map(lambda t: f"{t['key']} -> {t['best_locale']}", missing_translations)))
            print(f"buildmd.py: Used fallbacks for some strings since they weren't available in {locale}:\n{s}\n")

        # Log
        print(f'buildmd.py: Inserting generated strings into template at {template_path}...')
        
        # Insert into template
        if document_key == "Readme":
            template = insert_root_paths(template, destination_path, locale, development_locale)
            template = insert_locale_stuff(template, document_key, locale, development_locale, iterated_locales, translation_progress)
        elif document_key == "Acknowledgements":
            template = insert_root_paths(template, destination_path, locale, development_locale) # This is not currently necessary here since we don't use the {root_path} placeholder in the acknowledgements templates
            template = insert_locale_stuff(template, document_key, locale, development_locale, iterated_locales, translation_progress)
            template = insert_acknowledgements(template, locale, gumroad_api_key, gumroad_sales_cache_file, gumroad_sales_cache_shelf_life, no_api)
        else:
            assert False # Should never happen because we check document_key for validity above.
        
        # Validate that template is completely filled out
        #   Note: Having this crash might be annoying for writing documents. If there's an issue we have to understand these weird errors instead of just seeing the problems in the resulting document.
        template_parse_result = list(string.Formatter().parse(template))
        template_fields = [tup[1] for tup in template_parse_result if tup[1] is not None]
        is_fully_formatted = len(template_fields) == 0
        if not is_fully_formatted:
            print(f"Something went wrong. Template at '{template_path}' still has format field(s) after inserting: {template_fields}")
            sys.exit(1)
        
        # Add comment to the top of the document which says that it is autogenerated
        template = "<!-- THIS FILE IS AUTOMATICALLY GENERATED - EDITS WILL BE OVERRIDDEN -->\n" + template
        
        # Create path
        destination_dir = os.path.dirname(destination_path)
        if len(destination_dir) > 0:
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        
        # Write template
        with open(destination_path, mode="w") as f:
            f.write(template)
        
        # Log
        print('Wrote result to {}'.format(destination_path))

# 
# Template inserters 
#

sales_data_cache = None # This cache is used for different language version of the acknowledgements document. Now that we massively sped up getting all the sales through the gumroad_sales_cache.json file, this isn't really necessary anymore. But it doesn't hurt.

def insert_acknowledgements(template, locale_str, gumroad_api_key, cache_file, cache_shelf_life, no_api):
    
    global sales_data_cache
    
    all_sales_count = None
    generous_sales = None
    very_generous_sales = None
    
    if sales_data_cache != None:
        
        #
        # Load from cache
        #
        
        all_sales_count = sales_data_cache['all_sales_count']
        generous_sales = sales_data_cache['generous_sales']
        very_generous_sales = sales_data_cache['very_generous_sales']
        
    else: 
        
        #
        # Load from scratch and store in cache
        #
    
        sales = get_latest_sales(cache_file, cache_shelf_life, gumroad_api_key, gumroad_api_base, gumroad_sales_api, gumroad_product_ids, no_api)
        
        # Experiment: Analyze license keys and how many times they have been activated
        #   
        #   (This code doesn't really belong here at all. TODO: Move the code somewhere else. We might want to extract the loading-of-gumroad-sales into a separate python module or whatever it's called so we can reuse it outside of markdown_generator.py)
        # 
        #   Results: (09.05.2024) (This is not 100% accurate, I think we missed a few licenses and we only used the USD listing, not the older EUR listing. But these numbers describe the activations of the vast majority of bought licenses I think)
        #   - Number of licenses that have been activated 0 times: 90
        #   - Number of licenses that have been activated 1 time: 5910
        #   - Number of licenses that have been activated 2 times: 307
        #   - Number of licenses that have been activated 3 times: 39
        #   - Number of licenses that have been activated 4 times: 7
        #   - Number of licenses that have been activated 5 times: 4
        #   - Number of licenses that have been activated 6 times: 1
        #   - Number of licenses that have been activated 7 times: 1
        #   - Number of licenses that have been activated 8 times: 1
        #   - Number of licenses that have been activated 9 times: 1
        #
        #   -> We can see that so far, no license seems to have been publicly shared in a way that matters. This might mean it's okay to turn off some anti piracy measures that we currently implement. See this mail (message:<C7DE5F1A-CDED-47B6-BCAC-5CB40DF22DE3@gmail.com>) for more discussion.

        if False:
            all_license_keys = []
            uses_distribution = {} # Keys are a number of activations, and the value is how many license keys have been activated <key> many times.
            start_index = 3934
            
            for i in range(start_index, len(sales)):
                
                sale = sales[i]
                
                product_id = sale['product_id']
                license_key = sale['license_key']
                
                print(f"Getting license key info no {i}/{len(sales)}. prod id: {product_id}, license_key: {license_key}.")
                
                if i % 5 == 0:
                    print(f"Uses distribution so far:\n{uses_distribution}")
                
                response = None
                while True:
                    
                    r = requests.post(
                    gumroad_api_base + "/v2/licenses/verify", 
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded'
                    },
                    params={
                        'product_id': product_id,
                        'license_key': license_key,
                        'increment_uses_count': "false", # Important!!! Don't mess up ppls usage count
                    })
                    if r.status_code == 200:
                        response = r
                        break
                    print(f"License key request failed with code {r.status_code}. Retrying.")
                
                response_dict = response.json()
                
                if 'success' in response_dict and 'uses' in response_dict:
                    all_license_keys.append(response_dict)
                    old_uses_count = uses_distribution.get(response_dict['uses'], 0)
                    uses_distribution[response_dict['uses']] = old_uses_count + 1
                            
            all_license_keys.sort(key='uses')
            print('All license keys sorted by number of uses:')
            pprint(all_license_keys)
        
        # Premature return
        #   This happens e.g. if the no_api option is set and there is also no cache.
        if len(sales) == 0:
            template = template.replace('{very_generous}', 'NO_DATA').replace('{generous}', 'NO_DATA').replace('{sales_count}', 'NO_DATA')
            return template
        
        # Record all sales count
        
        all_sales_count = len(sales)
        
        # Log
        
        print('Filtering sales...')
        
        # Filter people who don't want to be displayed
        
        print('')
        sales = list(filter(wants_display, sales))
        print('')
        
        # Filter generous and very generous
        generous_sales = list(filter(is_generous, sales))
        very_generous_sales = list(filter(is_very_generous, sales))
    
        # Create cache and store in cache
        sales_data_cache = dict()
        sales_data_cache['all_sales_count'] = all_sales_count
        sales_data_cache['generous_sales'] = generous_sales
        sales_data_cache['very_generous_sales'] = very_generous_sales
    
    # Log
    print('Compiling generous contributor strings...')
    
    # Round sales count
    all_sales_count_rounded = round_to_multiple(all_sales_count, sales_count_rounder, math.floor)
    assert all_sales_count_rounded <= all_sales_count
    all_sales_count_rounded = str(all_sales_count_rounded) if all_sales_count_rounded == all_sales_count else f"{all_sales_count_rounded}+"
    
    # Generate generous markdown
    
    generous_string = ''
    first_iteration = True
    for sale in generous_sales:
        
        if not first_iteration:
            generous_string += nbsp + ' ' # nbsp + '| '
        first_iteration = False
        
        generous_string += display_name(sale)

    # Generate very generous markdown
        
    very_generous_string = ''
    
    last_month = None
    first_iteration = True
    
    for sale in very_generous_sales:
        date_string = sale['created_at']
        date = datetime.datetime.strptime(date_string, gumroad_date_format)
        if date == None:
            print('Couldnt extract date from string {}'.format(date_string))
            exit(1)
        
        if date.month != last_month:
            
            last_month = date.month
            
            if not first_iteration:
                very_generous_string += '\n\n'
            first_iteration = False
            
            locale = babel.Locale.parse(locale_str, sep='-')
            very_generous_string += '**{}**\n'.format(babel.dates.format_datetime(datetime=date, format='LLLL yyyy', locale=locale)) # See https://babel.pocoo.org/en/latest/dates.html and https://babel.pocoo.org/en/latest/api/dates.html#babel.dates.format_datetime.
        
        name = display_name(sale)
        message = user_message(sale, name)
        
        if len(message) > 0:
            very_generous_string += '\n- ' + name + f' - "{message}"'
        else:
            very_generous_string += '\n- ' + name
    
    # Log
    print('\nGenerous string:\n\n{}\n'.format(generous_string))
    print('Very Generous string:\n\n{}\n'.format(very_generous_string))
    
    print('Inserting into template:\n\n{}\n'.format(template))
    
    # Insert into template
    # str.format forces us to replace all the template placeholders at once, which we don't want, so we use str.replace
    
    # template = template.format(very_generous=very_generous_string, generous=generous_string, sales_count=all_sales_count)
    template = template.replace('{very_generous}', very_generous_string).replace('{generous}', generous_string).replace('{sales_count}', all_sales_count_rounded)
    
    # Return
    return template
    
def insert_locale_stuff(template: str, document_key: str, locale: str, development_locale: str, locales: list[str], translation_progress: dict):
    
    # Process `locale`
    language_name = f'{mflocales.locale_to_language_name(locale, locale, True)}'
    
    # Filter locales
    #   Note: We filter out locales from the locale picker whose progress is under show_locale_threshold. This follows the logic we use for the LocalePicker on the MMF website. See usage of `showLocaleThreshold` in the MMF Website.
    locales = list(filter(lambda l: (l == development_locale) or (l == locale) or (translation_progress[l]['percentage'] > show_locale_threshold), locales))

    # Generate language list ui string
    ui_language_list = ''
    for i, locale2 in enumerate(locales):
        
        is_last = i == len(locales) - 1
        
        language_name2 = f'{mflocales.locale_to_language_name(locale2, locale2, True)}'
        
        # Create relative path from the location of the `language_dict` document to the `language_dict2` document. This relative path works as a link. See https://github.blog/2013-01-31-relative-links-in-markup-files/
        path = construct_path(document_key, DocType.COMPILED_DOC, locale, development_locale)
        path2 = construct_path(document_key, DocType.COMPILED_DOC, locale2, development_locale)
        root_path = path_to_repo_root(path)
        relative_path = root_path + path2
        link = urllib.parse.quote(relative_path) # This percent encodes spaces and others chars which is necessary
        
        ui_language_list += '  '
        
        if language_name == language_name2:
            ui_language_list += f'**{language_name2}**'
        else:
            ui_language_list += f'[{language_name2}]({link})'
        
        ui_language_list += '\\'
        if not is_last: 
            ui_language_list += '\n'
        
    # Log    
    print(f'\nLanguage picker language list generated for language "{language_name}":\n{ui_language_list}\n')
    
    # Insert language list
    #   template = template.format(current_language=language_name, language_list=ui_language_list)
    template = template.replace('{language_list}', ui_language_list)
    
    # Gather info
    localization_progress_str = '100%' if (locale == development_locale) else (str(int(100 * translation_progress[locale]['percentage'])) + '%')

    # Insert other stuff    
    template = template.replace('{locale_code}', locale)
    template = template.replace('{localization_progress}', localization_progress_str)
    template = template.replace('{current_language}', mflocales.locale_to_language_name(locale, destination_locale_str=locale, include_flag=True)) # Note: Maybe rename current_language to locale_name?

    # Return
    return template

def insert_root_paths(template, path, locale, development_locale):
        
    # Notes: 
    # - Abstracting the "document_root" out makes it easy to link between markdown documents of the same language.
    #   For example, you can just `[link]({document_root}Acknowledgements.md)` to link to the acknowledgements file in the same language as the current document.
    # - Abstracting the "repo_root" makes it easy to link to any files in the repo, no matter where the compiled document ends up.
        
    # Extract info from language_dict
        
    # path = os.path.join(document_root, document_subpath, '') # The '' at the end makes it end with a separator `/`
    repo_root = path_to_repo_root(path)
    language_root = path_to_compiled_doc_root(path, locale, development_locale)
    
    template = template.replace('{repo_root}', repo_root)
    template = template.replace('{language_root}', language_root) # Maybe rename to 'locale_root'? We try to use 'locale' consistently in the python scripts now (as of 07.09.2024, see mflocales.py discussion)
    
    return template

# 
# Particle generators
#

 
def display_name(sale):
    
    name = ''

    # Special requests & rules
    if sale['email'] == 'rawad.aboud@icloud.com': # Gumroad api says he's from IL-TA (Tel Aviv, Israel), but he's Palestinian. See [this mail](message:<8C5D64EE-447A-4A65-89A4-27F99115C986@icloud.com>)
        return '🇵🇸 Rawad Aboud'
    
    # Get user-provided name field
    name = gumroad_custom_field_content(sale, gumroad_custom_field_labels_name)
    if name == None: name = ''
    
    # Fall back to full_name field
    if name == '':
        if 'full_name' in sale:
            name = sale['full_name']
    
    # Fall back to email-based heuristic
    if name == '':
        
        # Get email
        email = ''
        if 'email' in sale:
            email = sale['email']
        elif 'purchase_email' in sale:
            email = sale['purchase_email']
        else:
            sys.exit(1)
        
        # Split email
        n1, _, n2 = email.partition('@')
        
        # Remove plus addressing
        n1, _, _ = n1.partition('+')
        
        # Check blacklist
        use_n1 = True
        for non_name in name_blacklist:
            if non_name in n1:
                use_n1 = False
                break
        
        if use_n1:
            name = n1
        else:
            name = n2.partition('.')[0] # In a case like gm.ail.com, we want gm.ail, but this will just return gm. But should be good enough. Edit: Why would we display the users name as 'gmail'? Why not just 'A friendly user' at that point? I guess because some ppl have me@noah.nuebling.com addresses?

    # Replace weird separators with spaces
    for char in '._-–—+':
        name = name.replace(char, ' ')

    # Correct case
    #   The full_name field is sometimes in all caps and the email based heuristic returns all lower-case
    name = name.title()
    
    # Prepend flag
    flag = emoji_flag(sale)
    if flag != '':
        name = flag + ' ' + name

    # Escape special characters
    name = escape_user_generated(name)
    
    # Normalize whitespace
    name = normalize_whitespace_for_user_generated(name)
    
    # Debug
    if name == "🇩🇪 Gmail":
        print("Hughhhh")
    
    # Replace all spaces with non-breaking spaces
    name = name.replace(' ', nbsp)
    
    return name
 
def emoji_flag(sale):
    
    # TODO: Move this to Shared/ (Also why are we using pycountry instead of babel as we do everywhere else?)
    
    # Get country code
    country_code = sale.get('country_iso2', '')
    
    # pycountry-based fallback for determining country code
    #   Notes: Does the country code ever need a fallback? Edit: Yes, apparently for Taiwan.
    if country_code == '': 
    
        country_name = sale.get('country', '')
                
        pycountry_object = pycountry.countries.get(name=country_name)
        if pycountry_object:
            country_code = pycountry_object.alpha_2
        
        if country_code == '':
            
            # Fallback for Taiwan
            #   Note: I don't want to take a political stance or make either China or the USA angry with this. I only have a vague idea about the political issue and have no stance on it. I wrote this code so the script doesn't crash, if you can think of a better solution, please let me know.
            if country_name == 'Taiwan':
                country_code = "TW"
            
    
    if country_code == '':
        return ''
    
    result = ''
    for c in country_code.upper():
        result += chr(ord(c) + 127397)
    return result
 
def is_generous(sale):
    
    sale_pid = sale['product_id']
    
    if sale_pid == gumroad_product_id_euro:
        if sale['variants_and_quantity'] == '(2. Option)': 
            return True
        if sale['formatted_display_price'] == '€5': # Commenting this out doesn't change the results. Not sure why we wrote this - maybe the "variants_and_quantity" value used to be different from (2. Option) for a period?
            return True
    elif sale_pid == gumroad_product_id_dollar:
        if sale['variants_and_quantity'] == '(2. Option)':
            return True
    else:
        assert False
    
    return False
 
def is_very_generous(sale):
    
    sale_pid = sale['product_id']
    
    if sale_pid == gumroad_product_id_euro:
        if sale['variants_and_quantity'] == '(3. Option)':
            return True
        if sale['formatted_display_price'] == '€10': # Commenting this out doesn't change the results
            return True
    elif sale_pid == gumroad_product_id_dollar:
        if sale['variants_and_quantity'] == '(3. Option)':
            return True
    else:
        assert False
        
    return False
        
def wants_display(sale):
    
    # Declare result
    result = True
    
    while True: # This is a goto statement, not a loop
        
        # 
        # Special requests & rules
        #

        name = display_name(sale).replace(nbsp, ' ') # We should perhaps cache access to the display_name() and user_message(), since we calculcate it several times for each sale. But seems fast enough for now. And makes for easier code.
        message = user_message(sale, name)
        
        if name == "🇺🇸 Please Don'T Put Me In The Acknowledgements":
            result = False
            break
        
        # 
        # "Don't display" checkbox    
        #
        
        dont_display_checkbox_is_checked = gumroad_custom_field_content(sale, gumroad_custom_field_labels_dont_display)
        if dont_display_checkbox_is_checked == None: dont_display_checkbox_is_checked = False
        if dont_display_checkbox_is_checked:
            result = False
            break
        
        #
        # Break
        #
        #   (This is a goto statement, not a loop)
        
        break

    # Log
    if result == False:
        print("{} payed {} and does not want to be displayed".format(display_name(sale), sale['formatted_display_price']))
    
    # Return
    return result

def user_message(sale, name):
    
    # Notes:
    # - At the time of writing, the name that is being passed in contains &nbsp; chars instead of normal spaces.
    
    # Get raw message from sale data
    message = gumroad_custom_field_content(sale, gumroad_custom_field_labels_message)
    if message == None: message = ''

    # Remove leading / trailing whitespace
    message = message.strip()
    
    # Normalize whitespace
    message = normalize_whitespace_for_user_generated(message)
    
    # Escape special characters
    message = escape_user_generated(message)
    
    # Debug
    if len(message) > 0:
        print("{} payed {} and left message: {}".format(name, sale['formatted_display_price'], message))
    
    # Remove message if it's contained in the name of the purchaser (Because we assume they did that accidentally)
    if len(message) > 0 and (message.lower() in name.replace(nbsp, ' ').lower()):
        print("{}'s message is contained in their name, so we're filtering it out".format(name))
        message = ''
        
    # Special requests & rules
    while True:
        
        name = name.replace(nbsp, ' ')
        
        if name == "🇹🇼 Eugene" and message == "Taiwan no.1":
            message = ''
            break
        
        # This is not a loop but a a makeshift goto statement
        break
    
    # Return
    return message

def gumroad_custom_field_content(sale, custom_field_labels):
    
    content = None
    if sale['has_custom_fields']:
        for label in custom_field_labels:
            content = sale['custom_fields'].get(label, None)
            if content != None:
                break

    return content

def normalize_whitespace_for_user_generated(text):
    # Replace all whitespace with a single space
    #   Prevents weird display in case users entered linebreaks or multiple spaces. (This has never happened at the time of writing, so this might be totally unnecessary)
    text = re.sub(r'\s+', ' ', text)
    return text

def escape_user_generated(text):
    
    # In some cases, users used characters that messed up up the markdown generation 
    #   (At the time of writing, there was only one instance of this, where someone used { and })
    
    # Remove { and } because it messes up python string formatting
    text = text.replace(r'{', r'(')
    text = text.replace(r'}', r')')
    
    # Escape special characters for markdown
    #   Edit: This is not really necessary. If someone wants to add markdown let them have their fun.
    # special_characters = ['\\', '`', '*', '_', '[', ']', '(', ')'] # Note: ChatGPT additionally recommened to escape: '+', '-', '.', '!', '|', '>', '#', '{', '}' - but I don't think that's necessary in our case.
    # for char in special_characters:
    #     if char in text:
    #         text = text.replace(char, f"\\{char}")

    return text

def round_to_multiple(n, multiple, rounding_fn=round):
    return rounding_fn(n / multiple) * multiple

#
# Retrieve/cache gumroad sales
#

def get_latest_sales(cache_file, cache_shelf_life, gumroad_api_key, gumroad_api_base, gumroad_sales_api, gumroad_product_ids, no_api):
    
    # Log
    
    print('Getting latest gumroad sales using cache file...')
    
    # Defining helper function for control flow 
    #   (Does python have goto?)
    
    cache = {}
    
    def get_stitched_sales(cache_file):
        
        # Try to get sales from the cache file, then load newer sales from the gumroad API, and then stitch the cached sales and the fresh sales together.
        
        nonlocal cache # This is sort of a 'secondary return value' from this function I guess?
        
        try:
            with open(cache_file, 'r') as file:
                cache = json.load(file)
        except FileNotFoundError:
            print("Sales cache file not found. Will load all sales from the Gumroad API...")
            return None

        # Return cached_sales instead of all_sales in case of no_api
        if no_api:
            print("Using cached_sales due to no_api flag...")
            return cache['sales']
        
        # Check cache expiration
        cache_creation_date = datetime.datetime.strptime(cache['created_at'], gumroad_date_format) # We don't have to use the gumroad_date_format here, but why not
        cache_is_expired = datetime.datetime.utcnow() > (cache_creation_date + datetime.timedelta(hours=cache_shelf_life))
        if cache_is_expired:
            print('The cache is expired. Will load all sales from the Gumroad API...')
            return None

        # Extract sales from cache
        cached_sales = cache['sales']
        
        # Get date from which to fetch new sales
        latest_cached_sale = cached_sales[0] if len(cached_sales) > 0 else None
        latest_cached_sale_date = datetime.datetime.strptime(latest_cached_sale['created_at'], gumroad_date_format) 
        latest_cached_sale_day = babel.dates.format_datetime(datetime=latest_cached_sale_date, locale='en_US', format='yyyy-MM-dd') # YYYY-MM-DD format is required by gumroad sales fetching API according to docs. Not specifying `locale`` leads to weird issues in iTerm2 while still running fine from vscode Terminal. Weird.
        
        # Validate
        if not latest_cached_sale_day:
            print('Failed to get the day of the latest sale in the cache. Will load all sales from the Gumroad API...')
            return None
        
        # Get new sales
        new_sales = load_sales_from_api(gumroad_api_key, gumroad_api_base, gumroad_sales_api, gumroad_product_ids, after_day=latest_cached_sale_day)

        # Find index in cache to stitch together the new sales with the cache
        stitch_index = -1
        for i, sale in enumerate(new_sales):
            if sale['id'] == cached_sales[0]['id']: 
                stitch_index = i
                break
        
        # Validate
        #   That the cache and the newly fetched sales can be stitched together
        are_stitchable = stitch_index != -1
        if not are_stitchable:
            print('Failed to stitch new sales together with cached sales. Will load all sales from the Gumroad API...')
            return None

        # Get new_new_sales
        new_new_sales = new_sales[0:stitch_index]

        # Log
        print(f"Adding new sales to cache: {list(map(lambda x: display_name(x), new_new_sales))}...")
        
        # Stitch the sales together
        all_sales = new_new_sales + cached_sales
        
        # Return
        return all_sales
            
    # Try to get the stitched sales
    all_sales = get_stitched_sales(cache_file)
    
    # Fall back to loading ALL sales from the gumroad API
    cache_has_been_cleared = False
    if not all_sales and not no_api:
        print('Loading all sales fresh from the Gumroad API...')
        all_sales = load_sales_from_api(gumroad_api_key, gumroad_api_base, gumroad_sales_api, gumroad_product_ids, after_day=None)
        cache_has_been_cleared = True

    # Save the new sales to cache
    if not no_api:
        new_cache = {
            'created_at': datetime.datetime.utcnow().strftime(gumroad_date_format) if cache_has_been_cleared else cache['created_at'],
            'sales': all_sales,
        }
        with open(cache_file, 'w') as file:
            json.dump(new_cache, file)
    
    # Return
    return all_sales

def load_sales_from_api(gumroad_api_key, gumroad_api_base, gumroad_sales_api, gumroad_product_ids, after_day=None):
    
    # Load sales of the gumroad product on `after_day` and later
    
    sales = []
    
    for pid in gumroad_product_ids:
        
        page = 1
        api = gumroad_sales_api
        failed_attempts = 0

        while True:
            
            print('Fetching sales for product {} after date {} (page {})...'.format(pid, after_day, page))
            
            response = requests.get(
                gumroad_api_base + api, 
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                params={
                    'access_token': gumroad_api_key,
                    'product_id': pid,
                    **({'after': after_day} if after_day else {})
                }
            )
            
            if response.status_code == 200:
                failed_attempts = 0
            else:
                failed_attempts += 1
                if response.status_code == 401:
                    print('(The request failed because it is unauthorized (status 401). This might be because you are not providing a correct Access Token. See --help for more info')
                    sys.exit(1)
                elif failed_attempts <= 10:
                    print(f'The HTTP request failed with status {response.status_code}. Since the the gumroad servers sometimes randomly fail (normally with code 5xx), were trying again...')
                    continue
                else:
                    print(f'The HTTP request failed with status {response.status_code}. Exiting script.')
                    sys.exit(1)
            
            response_dict = response.json()
            if response_dict['success'] != True:
                print('Gumroad API returned failure. Exiting script.')
                sys.exit(1)
            
            sales += response_dict['sales']
            
            if 'next_page_url' in response_dict:
                api = response_dict['next_page_url']
            else:
                break
            
            page += 1    
         
    # Sort sales by date
    #   I feel like the Gumroad api should already return stuff sorted by data but it doesn't seem to work at least as I'm using it at the time of writing
    sales.sort(key=(lambda sale: datetime.datetime.strptime(sale['created_at'], gumroad_date_format)), reverse=True)
    
    # Return 
    return sales

#
# Call main
#
if __name__ == "__main__":
    main()
