
#
# Discussion
#

# On `Language IDs` | `language tags` | `locales`.
#   The terminology is confusing because Apple, Vue and Babel all use different terminology for basically same thing.
#   
#   Apple -> Uses the term `languageID`
#   Babel -> Uses the term `raw locale string`
#   Vue I18n -> Uses the term `locale`
#   BCP 47 -> Uses the term `language tag`
#
#   -> These are all almost the same thing.
#
#   What is it? 
#   So all of these things are based on the BCP 47 `language tag` standard. A BCP `language tag` is string that specifies a language. 
#   most of the time, the tag follows the format:
#
#       de
#
#   Or the format:
#
#       de-AT
#
#   - Where `de` is an ISO alpha-2 (meaning it has 2 characters) language code. 
#   - Where `AT` is an ISO alpha-2 country code.
#   - There are some BCP 47 language tags that follow different formats for example. `es-419` stands for Spanish as spoken in Latin America and the Carribean. Or `sr-Latn` stands for Serbian written with Latin characters instead of Cyrillic ones.
#   - Sometimes, instead of `-`, we use `_` as a separator. Babel uses `_` by default (So it would be `de_AT` instead of `de-AT`). (But you can tell Babel it what separators to use.)
#
#   - Apples "Language ID"s, implement a subset of the BCP 47 specification if I understand correctly.
#   - Babel also follows the BCP 47 specification. So they should be compatible with the "Language ID"s used in Xcode.
#       -> Babel references a really old, outdated version of the BCP 47 spec, but chatGPT said it should still be compatible with the Apple language IDs, 
#   - I haven't found a direct reference that vue/nuxt I18n uses BCP 47 spec, but it has been perfectly compatible so I'm fairly sure it also follows the standard.
#
#   In our python scripts, we've used different terms for these `language tags` but from now on (26.08.2024) we'll try to use `locale` or `locale_str` consistently. 
#
#   References:
#       - ISO alpha-2 language codes: https://www.loc.gov/standards/iso639-2/php/code_list.php
#       - ISO alpha-2 country codes: https://www.iso.org/obp/ui/#search
#       - Apple language ID docs: https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPInternational/LanguageandLocaleIDs/LanguageandLocaleIDs.html
#       - Babel language tag docs: https://babel.pocoo.org/en/latest/api/core.html
#       - BCP 47 specification that babel docs reference: https://datatracker.ietf.org/doc/html/rfc3066.html
#       - BCP 47 latest specification at time of writing: https://datatracker.ietf.org/doc/html/rfc5646

# pip imports
import babel

# stdlib & local imports
import json
from collections import defaultdict
import re
import os

import babel.languages
import babel.lists
import mfutils

from dataclasses import dataclass

#
# Constants
#

language_code_to_emoji_flag_map = { 
                              
    # When a translation's localeID doesn't contain a country, fallback to these flags
    #   Country code reference: https://www.iso.org/obp/ui/#home
    #   Language code reference: https://www.loc.gov/standards/iso639-2/php/code_list.php
    #   
    #   Perhaps I could use babel.languages.get_official_languages() or related function instead of this hard-coding approach.

    'en': '🇬🇧',     # english -> uk
    'af': '🇿🇦',     # afrikaans -> south africa
    'de': '🇩🇪',     # german -> germany
    'ha': '🇳🇬',     # hausa -> nigeria (Hausa is spoken in different countries. The hausa ethnic group has its own flag, but not available as an emoji.)
    'id': '🇮🇩',     # indonesian -> indonesia
    'sw': '🇹🇿',     # swahili -> tanzania (Swahili is spoken in different countries. Official language in Kenya and Tanzania. Tanzania has the largest swahili-speaking population.)
    'nl': '🇳🇱',     # dutch -> netherlands
    'vi': '🇻🇳',     # vietnamese -> vietnam
    'tr': '🇹🇷',     # turkish -> turkey
    'ca': '🇦🇩',     # catalan -> andorra (There's no emoji flag for Catalonia. Catalonia is in Spain. Andorra has Catalan as official language but tiny population.)
    'da': '🇩🇰',     # danish -> denmark
    'es': '🇪🇸',     # spanish -> spain
    'fr': '🇫🇷',     # french -> france
    'it': '🇮🇹',     # italian -> italy
    'hu': '🇭🇺',     # hungarian -> hungary
    'nb': '🇳🇴',     # norwegian bokmål -> norway
    'pl': '🇵🇱',     # polish -> poland
    'pt': '🇵🇹',     # portugese -> portugal (This should be unused since we only use the pt-BR and pt-PT locales which include country codes, and our code will figure out the flag from that.)
    'ro': '🇷🇴',     # romanian -> romania
    'sr': '🇷🇸',     # serbian -> serbia
    'fi': '🇫🇮',     # finnish -> finland
    'sv': '🇸🇪',     # swedish -> sweden
    'cs': '🇨🇿',     # czech -> czechia
    'el': '🇬🇷',     # modern greek -> greece
    'ru': '🇷🇺',     # russian -> russia
    'uk': '🇺🇦',     # ukrainian -> ukraine
    'he': '🇮🇱',     # hebrew -> israel
    'ar': '🇸🇦',     # arabic -> saudi arabia (Arabic is spoken in many countries. Such as Egypt, Quatar, and United Arab Emirates. ChatGPT says that Saudi Arabia is the birthplace of the language and most iconic representation.)
    'fa': '🇮🇷',     # persian/farsi -> iran (Interesting fact: Persia renamed itself to Iran in the 1930s)
    'ne': '🇳🇵',     # nepali -> nepal
    'hi': '🇮🇳',     # hindi -> india
    'bn': '🇧🇩',     # bangla -> bangladesh
    'th': '🇹🇭',     # thai -> thailand
    'my': '🇲🇲',     # burmese -> myanmar (formerly known as Burma)
    'am': '🇪🇹',     # amharic -> ethiopia (Amharic is the official language of Ethiopia, and isn't spoken much outside.)
    'km': '🇰🇭',     # khmer -> cambodia
    'zh': '🇨🇳',     # chinese -> china
    'ja': '🇯🇵',     # japanese -> japan    
    'ko': '🇰🇷',     # korean -> south korea    
}

language_name_override_map = {
    'en': {
        'zh-HK': 'Chinese (Honk Kong)', # I think this is unused?
    },
    'zh-HK': {
        'zh-HK': '中文（香港)', # The native Babel name for this locale is way too long. This is name used by Apple.
    }
}

# project_locales = ['en', 'de', 'zh-HK', 'zh-Hans', 'zh-Hant', 'vi', 'ko']   # This is used to check if the locales of the website and the main app are in-sync. Update: Now validating locales inside uploadstrings.py instead.


path_to_xcodeproj = {
    'mac-mouse-fix': 'Mouse Fix.xcodeproj', 
    'mac-mouse-fix-website': 'mac-mouse-fix-website-localization.xcodeproj',
}

#
# Language stuff
#
def sorted_locales(locales, source_locale):
    
    """
    - Sorts all the locales alphabetically by their display name, but puts the development aka source_locale (en) as the first language.
    - We plan to use this sorting whenever there's a language picker. (On the website and in the markdown language pickers)
    """
    smallest_char = "\u0000"
    result = sorted(locales, key=lambda l: smallest_char if l == source_locale else locale_to_language_name(l, l, False))
    return result

def get_localization_progress(xcstring_objects: list[dict], translation_locales: list[str]) -> dict:
    
    """
    - You pass in a list of xcstrings objects, each of which is the content of an xcstrings parsed using json.load()
    - The return is a dict with structure:
        {
            '<locale>': {
                'translated': <number of translated strings>,
                'to_translate': <number of strings that should be translated overall>,
                'percentage': <fraction of strings that should be translated, which actually have been translated (as a float between 0.0 and 1.0)>,
                'missing_keys': <list of localizationKeys that should be translated but aren't translated.>
        }
        
        - Note that strings which are marked as 'stale' in the development language are not considered 'strings that should be translated'. Since the 'stale' state means that the string isn't used in the source files.
    """
    
    # Define states
    is_translated_states = ['translated']
    should_translate_states = ['new', 'needs_review', 'mmf_indeterminate']
    should_not_translate_states = ['stale', 'mmf_dont_translate']           # (Stale means that the kv-pair is superfluous and doesn't occur in the base file/source code file afaik, therefore it's not part of 'to_translate' set)
    all_states = is_translated_states + should_translate_states + should_not_translate_states
    
    # Create an overview of how many times each translation state appears for each language
    
    localization_state_counts = defaultdict(lambda: defaultdict(lambda: 0))
    missing_keys: dict[str, list] = defaultdict(lambda: [])
    
    for xcstring_object in xcstring_objects:
        for key, string_dict in xcstring_object['strings'].items():
            
            for locale in translation_locales:
                
                # Get state
                s = None
                if not string_dict.get('shouldTranslate', True):
                    s = 'mmf_dont_translate'
                else:                
                    s = string_dict.get('localizations', {}).get(locale, {}).get('stringUnit', {}).get('state', 'mmf_indeterminate')
                    
                # Validate
                assert(s in all_states)    

                # Append to result1
                localization_state_counts[locale][s] += 1
                
                # Append to result2
                if s in should_translate_states:
                    missing_keys[locale].append(key)
                    
    
    localization_state_counts = json.loads(json.dumps(localization_state_counts, ensure_ascii=False)) # Convert nested defaultdict to normal dict - which prints in a pretty way (Update: Why do we need it to print pretty? Update2: Should we use ensure_ascii?)
    
    # Get translation progress for each language
    #   Notes: 
    #   - Based on my testing, this seems to be accurate except that it didn't catch the missing translations for the Info.plist file. That's because the info.plist file doesn't have an .xcstrings file at the moment but we can add one.
    
    localization_progress = {}
    for locale, state_counts in localization_state_counts.items():
        translated_count = sum([state_counts.get(s, 0) for s in is_translated_states])
        to_translate_count = sum([state_counts.get(s, 0) for s in (is_translated_states + should_translate_states)])
        localization_progress[locale] = {'translated': translated_count, 'to_translate': to_translate_count, 'percentage': translated_count/to_translate_count, 'missing_keys:': missing_keys }

    # Return
    return localization_progress

def get_translation(xcstrings: dict, key: str, preferred_locale: str, fall_back_to_next_best_language: bool = True) -> tuple[str, str]:
    
    """
    -> Retrieves a `translation` for key `key` from `xcstrings` for the `preferred_locale`
    
    -> Returns a tuple with structure: (translation, locale_of_the_translation)
    
    If no translation is available for the preferred_locale, it will fall back to the next best language. 
        - For example, it could fall back from Swiss German to Standard German, if a String only has a German and English version. (Haven't tested this) 
        - As a last resort it will always fall back to the development language (English)
        - This logic is implemented by babel.negotiate_locale, and I'm not sure how exactly it behaves.

    Notes: 
    - The `xcstrings` dict argument is expected to be the content of an .xcstrings file which has been loaded using json.load()
    - The fall_back_to_next_best_language option might not make sense to use, if you have a string-retrieval system at runtime that implements a fallback. 
        I thought that nuxt-i18n had this? But I think we still decided to use the fall_back_to_next_best_language option for that. Not sure why anymore.
    """
    
    assert xcstrings['version'] == '1.0' # Maybe we should also assert this in other places where we parse .xcstrings files
    
    source_locale = xcstrings['sourceLanguage']
    localizations = xcstrings['strings'][key]['localizations']
    
    translation = None
    translation_locale = None
    
    if fall_back_to_next_best_language:
        
        available_locales = localizations.keys()
        preferred_locales = [preferred_locale, source_locale, *available_locales] # The leftmost is the most preferred in babel.negotiate_locale
        translation_locale = babel.negotiate_locale(preferred_locales, available_locales) # What's the difference to babel.Locale.negotiate()?
        
        translation = localizations[translation_locale]['stringUnit']['value']
        assert translation != None
        # assert len(translation) != 0 # Not asserting this since sometimes translations can be empty strings
    else:
        translation_locale = preferred_locale
        translation = localizations.get(translation_locale, {}).get('stringUnit', {}).get('value', '') # Why are we returning emptystring instead of None?
    
    return translation, translation_locale
        

def make_custom_xcstrings_visible_to_xcodebuild(path_to_xcodeproj: str, custom_xcstrings_paths: list) -> dict:
    
    """
    This is sooo convoluted. But I guess I'm having fun. 
    
    Update: Gave up on this
    
    The point of this is to only make the strings inside Markdown.xcstrings 'visible' to Xcode while exporting.
        The only way I know to prevent Xcode from deleting the content of Markdown.xcstrigns is by 
        1. setting the strings' extractionState to manual 
        2. Not having the file be part of any build target 
            (aka not having the file 'visible' to Xcode. 'visible' is not the best term but that's what we mean)
        
        Simply setting the extractionState to manual would be a very simple and totally sufficient solution. We could still temporarily set it back to extracted_with_value while we sync the .xcstrings file. 
        If we do that, the only disadvantage that I can think of is that Xcode wouldn't disable editing the English version of the string in the .xcstrings editing GUI. (A GUI which normally only I can see) 
        -> This is really not important at all!
        However, this very slight problem (and me being pretty nerdy) prompted me to implement this function to make the Markdown.xcstrings file temporarily 'visible' to Xcode, by editing the .pbxproject file.
        This way, we can keep the file 'invisible' to Xcode normally, so that it doesn't attempt to delete its content, but then make the file 'visible' during exports, so that Xcode can properly extract the .xcloc files for us.
        
        -> This is totally unnecessary and quite hacky and brittle. We should just set the extractionState to manual inside Markdown.xcstrings. (But I don't want to)
        
        Update: If we do this, Xcode will STILL delete all the strings from Markdown.xcstrings as it's exporting .xcloc files. So we'd have to set the extractionState of every string to manual before exporting - on top of this 'visibility' stuff. 
                It's getting too annoying. I'll just keep the state as 'manual' and keep the files visible to Xcode, and the temporarily set it to extracted_with_value as we're syncing the strings.
        
    """
    
    assert False
    
    # Extract data
    pbxproj_path = f'{path_to_xcodeproj}/project.pbxproj'
    
    # Convert whole pbxproject file to json
    #   - Xcode can still read the json version, but will convert it back to legacy plist seemingly as soon as it interacts with it.
    #   - You can't seem to insert values into the proj file directly using plutil. This seems to be possible with PlistBuddy but that will 
    #       convert the proj file into xml. So just converting to json to begin with seems to be easiest. 
    #       See https://stackoverflow.com/questions/32133576/what-tools-support-editing-project-pbxproj-files
    
    mfutils.runCLT(f'plutil -convert json "{pbxproj_path}"')
    
    # Load xcode project json
    pbxproject_json = json.loads(mfutils.runCLT(f"cat '{pbxproj_path}'").stdout)
        
    for xcstrings_path in custom_xcstrings_paths:
        # Find xcstrings file
        xcstrings_name = os.path.basename(xcstrings_path) # Just ignore the path, just use the name
        xcstrings_uuids = []
        for uuid, info in pbxproject_json['objects'].items():
            if info['isa'] == 'PBXFileReference' and info['path'] == xcstrings_name:
                xcstrings_uuids.append(uuid)
                break
        
    # Validate
    #   This will fail if the xcstrings file's name is not unique throughout the project, or if the xcstrings files doesn't exist in the project.
    assert len(xcstrings_uuids) == 1
    
    # Extract
    markdown_xcstrings_uuid = xcstrings_uuids[0]
    
    # Create PXBuildFile object
    build_file_uuid = mfutils.xcode_project_uuid()
    build_file_value = {
         "fileRef" : markdown_xcstrings_uuid,
         "isa" : "PBXBuildFile"
      }
    
    # Insert PXBuildFile into project
    pbxproject_json['objects'][build_file_uuid] = build_file_value
    
    # Find build phase that adds resources
    
    build_phase_uuids = None
    for uuid, info in pbxproject_json['objects'].items():
        if info['isa'] == 'PBXNativeTarget' and info['name'] == 'Mac Mouse Fix':
            build_phase_uuids = info['buildPhases']
            break    
    resources_build_phase_uuid = None
    for uuid in build_phase_uuids:
        info = pbxproject_json['objects'][uuid]
        if info['isa'] == 'PBXResourcesBuildPhase':
            resources_build_phase_uuid = uuid
            break
    
    # Add PXBuildFile to PBXResourcesBuildPhase
    pbxproject_json['objects'][resources_build_phase_uuid]['files'].append(build_file_uuid)
            
    # Write json back to file
    with open(pbxproj_path, 'w') as file:
        file.write(json.dumps(pbxproject_json, ensure_ascii=True, indent=4)) # Not sure about ensure_ascii
    
    # Create 'undo payload'
    #   Pass this to the undo function to undo the changes that this function made
    undo_payload = {
        'pbxproj_path': pbxproj_path,
        'resources_build_phase_uuid': resources_build_phase_uuid,
        'inserted_build_file_uuid': build_file_uuid,
    }
    
    # Return
    return undo_payload
    
def undo_make_custom_xcstrings_visible_to_xcodebuild(undo_payload):
    
    # Gave up on this
    assert False
    
    # Extract
    pbxproj_path = undo_payload['pbxproj_path']
    build_file_uuid = undo_payload['inserted_build_file_uuid']
    resources_build_phase_uuid = undo_payload['resources_build_phase_uuid']
    
    # Convert project to json
    mfutils.runCLT(f'plutil -convert json "{pbxproj_path}"')
    
    # Load json
    pbxproject_json = json.loads(mfutils.runCLT(f"cat '{pbxproj_path}'").stdout)
    
    # Remove build_file_object
    del pbxproject_json['objects'][build_file_uuid]
    
    # Remove build_file_object from build_phase_object
    pbxproject_json['objects'][resources_build_phase_uuid]['files'].remove(build_file_uuid)
    
    # Write to file
    with open(pbxproj_path, 'w') as file:
        file.write(json.dumps(pbxproject_json, ensure_ascii=True, indent=4)) # Not sure about ensure_ascii
    
    # Return
    return
    

def find_xcode_project_locales(path_to_xcodeproj) -> tuple[str, list[str]]:
    
    """
    Returns the development locale of the xcode project as the first argument and the list of translation locales as the second argument
    """
    
    # Load xcodeproj json
    pbxproject_json = json.loads(mfutils.runclt(['plutil', '-convert', 'json', '-r', '-o', '-', f'{path_to_xcodeproj}/project.pbxproj']))    # -r puts linebreaks into the json which makes it human readable, but is unnecessary here. `-o -` returns to stdout, instead of converting in place
    
    # Find locales in xcodeproj
    development_locale = None
    locales = None
    for obj in pbxproject_json['objects'].values():
        if obj['isa'] == 'PBXProject':
            locales = obj['knownRegions']
            development_locale = obj['developmentRegion']
            break
    
    # Filter out 'Base' locale
    locales = [l for l in locales if l != 'Base']
    
    # Filter out development_locale
    translation_locales = [l for l in locales if l != development_locale]
    
    # Validate
    assert(development_locale != None and locales != None and len(locales) >= 1)
    
    # Return
    return development_locale, translation_locales

def locale_to_language_name(locale_str: str, destination_locale_str: str = 'en', include_flag = False):
    
    # Query override map
    language_name = language_name_override_map.get(destination_locale_str, {}).get(locale_str)
    
    if language_name == None:
        
        # Query babel        
        locale_obj = babel.Locale.parse(locale_str, sep='-')
        destination_locale_obj = babel.Locale.parse(destination_locale_str, sep='-')
        
        language_name = locale_obj.get_display_name(destination_locale_obj) # .display_name is the native name, .english_name is the english name
    
    # Capitalize
    language_name = language_name[0].upper() + language_name[1:]
    
    # Add flag emoji
    if include_flag:
        flag_emoji = locale_to_flag_emoji(locale_str)
        language_name = f"{flag_emoji} {language_name}"
    
    # Return
    return language_name


def locale_to_country_code(locale: str) -> str:
    
    # Get locale obj
    locale_obj = babel.Locale.parse(locale, sep='-')

    # Get country code directly from locale
    country_code = locale_obj.territory
    if country_code != None: 
        return country_code

    # Get country code from emoji flag
    language_code = locale_obj.language
    emoji_flag = language_code_to_emoji_flag_map.get(language_code, None)
    if emoji_flag == None: return None

    country_code = flag_to_country_code(emoji_flag)

    # Return
    return country_code

def country_code_to_flag(country_code):
    return ''.join(chr(ord(c) + 127397) for c in country_code.upper())

def flag_to_country_code(emoji_flag):
    return ''.join(chr(ord(c) - 127397) for c in emoji_flag)

def locale_to_flag_emoji(locale_str: str):
    
    # Parse locale_str
    locale = babel.Locale.parse(locale_str, sep='-')
    
    # Get flag from country code
    if locale.territory:
        return country_code_to_flag(locale.territory)
    
    # Fallback
    flag = language_code_to_emoji_flag_map.get(locale.language, None)
    if flag:
        return flag
    
    # Fallback to Unicode 'Replacement Character' (Missing emoji symbol/questionmark-in-rectangle symbol)
    return "�" 

#
# Continent stuff
#

def all_continent_codes():

    # Unused
    #   We thought about grouping languages by continent to make the LocalePicker UI nicer,.
    #   but all of our languages are from Europe or Asia, (with the sole exception of Brazilian Portugese), so that doesn't make sense.
    #   (We wanted to add some African Languages like Swahili and Amharic, but since macOS itself is not translated into those languages it doesn't really make sense.)
    #   (^ Last updated: 26.08.2024)

    assert False

    # List of continent codes as per ISO 3166-1
    continent_codes = ['001', '002', '019', '142', '150', '009']
    return continent_codes

def continent_code_to_continent_name(continent_code: str, destination_locale_str='en') -> str:

    assert False # Unused

    # Declare result
    _name = None

    # Create a Locale object for the destination language
    destination_locale_obj = babel.Locale.parse(destination_locale_str, sep='-')
        
    # Get the localized continent name
    continent_name = destination_locale_obj.territories.get(continent_code)

    # Return
    return continent_name

def country_code_to_continent_code(country_code: str) -> str:

    assert False # Unused

    continent_code = None # pycountry_convert.country_alpha2_to_continent_code(country_code)

    return continent_code


#
# Markdown parsing (Localizable strings)
#

def get_localizable_strings_from_markdown(md_string: str):

    # Declare return type
    @dataclass
    class LocalizedStringData:
        condition: str | None       # A string specifying the condition under which to include this localizable string in the rendered document (Instead of this we should probably just use our more powerful jinja-style {% if blocks %})
        key: str                    # a.key.that identifies the string across different languages
        value: str                  # The user-facing string in the development language (english). The goal is to translate this string into differnt languages.
        comment: str | None         # A comment providing context for translators.
        full_match: str             # The entire substring of the .md file that we extracted the key, value, and comment from. Replace all full_matches with translated strings to localize the .md file.

    """
    Returns a list of LocalizedStringData instances extracted from the `md_string`.
        
    The localizable strings inside the .md file can be specified in 2 ways: Using the `inline syntax` or the `block syntax`.
    
    The `inline sytax` follows the pattern:
    
        {{value||key||comment}}
        
        Examples:

            bla blah {{🙌 Acknowledgements||acknowledgements.title||This is the title for the acknowledgements document!}}
            
            blubb
            
            bli blubb {{😔 Roasting of Enemies||roast.title||This is the title for the roasting of enemies document!}} blah
    
    The `block syntax` follows the pattern:

        ```
        [if: <condition>]
        key: <key>
        ```
        <value>
        ```
        comment: <comment>
        ```

        The `if: <condition>` line can also be omitted.
        
        Example:
        
            ```
            if: do_acknowledge
            key: acknowledgements.body
            ```
            Big thanks to everyone using Mac Mouse Fix.

            I want to especially thank the people and projects named in this document.
            ```
            comment: This is the intro for the acknowledgements document
            ```

    Keep in mind!
    
        For the `block_syntax`, any free lines directly above or below the <value> will be ignored and removed. 
        
        So it doesn't make any difference whether the markdown source looks like this:

            ```
            key: <key>
            ```
            abcefghijklmnop
            qrstuvwxyz
            ```
            comment: <comment>
            ```
        
        Or like this:
            
            ```
            key: <key>
            ```
            
            
            
            abcefghijklmnop
            qrstuvwxyz

            ```
            comment: <comment>
            ```
        
        -> I tried to respect the free lines around the <value>, but I couldn't ge the regex to work like that. But honestly, it's probably better this way. 
            Since, this way, translators will never have to add blank lines above or below their content to make the layout of the .md file work as intended.
            
    Notes:
    - The block syntax was created in this regex101 project: https://regex101.com/r/IcHuN0
    - To test, you might want to post the whole .md file on regex101. That way you can see any under or overmatching which might not be obvious when testing a smaller example string.
    """

    # Extract translatable strings with inline syntax

    inline_regex = r"\{\{(.*?)\|\|(.*?)\|\|(.*?)\}\}"           # r makes it so \ is treated as a literal character and so we don't have to double escape everything
    inline_matches = re.finditer(inline_regex, md_string)
    
    # Extract translatable strings with block syntax
    
    block_regex = r"```(?:\n\s*?if:\s*(.*?)\s*)?\n\s*?key:\s*(.*?)\s*\n\s*?```\n\s*(^.*?$)\s*```\n\s*?comment:\s*?(.*?)\s*\n\s*?```"
    block_matches = re.finditer(block_regex, md_string, re.DOTALL | re.MULTILINE)

    # Assemble result

    all_matches = list(map(lambda m: ('inline', m), inline_matches)) + list(map(lambda m: ('block', m), block_matches))
    
    result: list[LocalizedStringData] = []
        
    for match in all_matches:
        
        # Get info from match
        
        full_match = match[1].group(0)
        condition = None
        comment = None
        value = None
        key = None
        
        if match[0] == 'inline':
            value, key, comment = match[1].groups()
        elif match[0] == 'block':
            condition, key, value, comment = match[1].groups()    
        else: 
            assert False    

        # Validate
        assert ' ' not in (condition or ''), f'condition contains space: {condition}'
        assert ' ' not in key, f'key contains space: {key}' # I don't think keys are supposed to contain spaces in objc and swift. We're trying to adhere to the standard xcode way of doing things. 
        assert len(key) > 0   # We need a key to do anything useful
        assert len(value) > 0 # English ui strings are defined directly in the markdown file - don't think this should be empty
        for st in [condition or '', value, key, comment]:
            assert r'}}' not in st # Protect against matching past the first occurrence of }}
            assert r'||' not in st # Protect against ? - this is weird
            assert r'{{' not in st # Protect against ? - this is also weird
        # TODO: Maybe somehow protect against over matching on block syntax, too
        
        # Stript results
        #   The comment sometimes contained whitespace, I'm not sure if the key can contain whitespace with the way the regex is set up.
        #   Stripping the value is not good since we want to preserve the indent
        key = key.strip()
        comment = comment.strip() 
        
        # Store
        result.append(LocalizedStringData(condition, key, value, comment, full_match))
    
    # Return
    
    return result
