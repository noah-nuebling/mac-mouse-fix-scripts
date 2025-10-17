
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

import mfutils

from dataclasses import dataclass

import urllib.parse
from typing import Callable

from pathlib import Path
import glob

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
        'zh-HK': 'Chinese (Hong Kong)', # This is used in the table inserted into translation_guide.md. Maybe other places [Oct 2025]
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

# Path from the main repo (where most of these scripts are expected to run) to the website repo
path_to_website_repo = '../mac-mouse-fix-website/'

# xcstrings_blacklist
#   hardcoded list of xcstrings files that aren't exported by the `xcodebuild -exportLocalizations` command.
#       AFAIK preventing xcodebuild from exporting can only be achieved by not including the xcstrings file in any Xcode compilation target – that's how we do it currently.
#   Alternatives to hardcoding: I tried parsing .pbxproj but that's more complicated. Could run `xcodebuild -exportLocalizations` every time but that's slow.
#   Validation: We validate this in uploadstrings.py, against the paths found inside the actually exported .xcloc files [Oct 2025]

xcstrings_blacklist = [os.path.normpath(p) for p in [
    path_to_website_repo + 'locales/old/Localizable.xcstrings',
]]

#
# (P)rogram-defined (l)ocalizable (strings) – aka plstrings
#

#   Explanation: [Aug 2025] Most of our our localizable strings are defined in .md templates. 
#       - But sometimes we wanna generate part of the documents in code.
#       - The @dataclass is also used by the AI translation of update notes in mac-mouse-fix-update-feed, but the strings for that aren't defined here. 
#           (The strings defined here are for markdown doc generation in the main mac-mouse-fix repo)

# [Aug 2025] Define the xcstrings file that manages the translations for the plstrings
#   Update: [Sep 2025] It's weird that the plstring are defined in the mac-mouse-fix-scripts repo while the xcstrings file is in the mac-mouse-fix repo. Both should be in the same repo.
plstrings_xcstrings_path = 'Markdown/Strings/Shared.xcstrings' 

@dataclass
class mf_localizable_str:
    string: str
    hint: str|None = None

plstrings: dict[str, mf_localizable_str] = {
    'localization.progress-message': mf_localizable_str( # [Aug 2025] Keep in sync with the localization progress banner on macmousefix.com.
                                                         #      General learning: `Help translate!` used to be `To help translate, click [here]()!`. We often use the `<...>, click [here]()` phrasing, but if the first part is already an action, we can simplify that.
                                                         #      `Help translate` difference: In the 'localization progress' informational banner, we use a more subdued "Help translate" instead of "🌎 Help translate!" as in the language picker. We do this as not to be pushy – it's supposed to be an informational banner first! I might be overthinking this.
        mfutils.mfdedent(r"""
            This document is `{localization_progress}` translated into `{current_language}`
            [Help translate](https://redirect.macmousefix.com/?locale={locale_code}&target=mmf-localization-contribution)
        """),
        hint=mfutils.mfdedent(r"""
            .
        """)
    ),
    'localization.translate-prompt': mf_localizable_str(
        mfutils.mfdedent(r"""
            [🌎 Help translate!](https://redirect.macmousefix.com/?locale={locale_code}&target=mmf-localization-contribution)
        """),
        hint=mfutils.mfdedent(r"""                              
            Note: 'Help translate!' should sound like an invitation, not a command. In German I rephrased it a bit to avoid the imperative form (I landed on 'Beim Übersetzen helfen!')
        """)
    ),
    'docname.readme':                       mf_localizable_str("Readme"),
    'docname.acknowledgements':             mf_localizable_str("Acknowledgements"),
    'docname.support':                      mf_localizable_str("Support"),
    'docname.captured-buttons':             mf_localizable_str("Captured Mouse Buttons"),
    'docname.captured-scroll-wheels':       mf_localizable_str("Captured Scroll Wheels"),
    'guide.footer.hope-it-helped.1':        mf_localizable_str("I hope this guide was helpful!"),       # 3 variants to make it feel a bit more high-effort and less generic.
    'guide.footer.hope-it-helped.2':        mf_localizable_str("I hope this information was useful!"),
    'guide.footer.hope-it-helped.3':        mf_localizable_str("I hope this guide cleared things up!"),
    'guide.footer.still-have-questions':    mf_localizable_str("Still have questions? Click [here](https://redirect.macmousefix.com/?locale={locale_code}&target=mmf-support-still-have-questions)."),    
}

def plstrings_get_xcstrings() -> dict:
    # [ ] TODO: Perhaps cache this – _buildmd.insert_locale_stuff() calls this many times.
    result = json.loads(Path(plstrings_xcstrings_path).read_text())
    return result

def plstrings_get_postprocessed_translation(key: str, locale: str):
    translation, locale = get_translation(plstrings_get_xcstrings(), key, locale, fall_back_to_next_best_language=True)
    translation = postprocess_translated_ui_string(translation, template_ui_string=plstrings[key].string)
    return translation

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

def get_localization_progress(xcstrings_objects: list[dict], translation_locales: list[str]) -> dict:
    
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
    
    for xcstrings_object in xcstrings_objects:
        for key, string_dict in xcstrings_object['strings'].items():
            
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

def fresh_xcstrings_content(development_locale: str) -> dict[str, str]:
    # [Jul 2025] 
    #   This is the content that Xcode 26.0 Beta 3 fills a fresh xcstrings file up with [Jul 2025] ... Actually, Xcode uses version 1.1 instead of 1.0 – but our scripts are built with 1.0 (not sure what the difference is)
    return mfutils.mfdedent( 
        """
        {{
            "sourceLanguage" : "{development_locale}",
            "strings" : {{}},
            "version" : "1.0"
        }}
        """).format(development_locale=development_locale)

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

def postprocess_template_ui_string(template_ui_string: str):

    # [Aug 2025] After a string is extracted from the template, and before it is inserted into the xcstrings file by syncstrings.py, we make some modifications to make the string easier to edit for translators.

    # [ ] TODO: Maybe rename to prepare_string_for_translation() and invert_prepare_string_for_translation()

    # Remove indentation from ui_string 
    #   (Otherwise translators have to manually add indentation to every indented line)
    #   (When we insert the translated strings back into the .md we have to add the indentation back in.)

    old_template_ui_string = template_ui_string
    old_indent_level, old_indent_char = mfutils.get_indent(template_ui_string)
    template_ui_string = mfutils.set_indent(template_ui_string, 0, ' ')
    new_indent_level, new_indent_char = mfutils.get_indent(template_ui_string)
    
    if old_indent_level != new_indent_level:
        print(f'syncstrings.py: [Changed {old_template_ui_string} indentation from {old_indent_level}*"{old_indent_char or ''}" -> {new_indent_level}*"{new_indent_char or ''}"]\n')

    # Remove all mdlink urls from extracted strings
    #       And replace with {url1}, {url2}, etc.
    #   Discussion: We do this so there's less margin for error for localizers. 
    template_ui_string = mfutils.replace_markdown_urls_with_format_specifiers(template_ui_string).md_string

    # Remove all <img> images
    template_ui_string = mfutils.replace_html_images_with_format_specifiers(template_ui_string).md_string

    # Return
    return template_ui_string

def postprocess_translated_ui_string(translated_ui_string: str, template_ui_string: str): 

    # [Aug 2025] Inverse of postprocess_template_ui_string()
    #   Before _buildmd.py inserts a translated string into the document, it needs to undo the modifications done by postprocess_template_ui_string() (Add indentation back and insert real urls)

    # Insert urls from the template into the translation
    urls_from_template = mfutils.replace_markdown_urls_with_format_specifiers(template_ui_string).removed_urls # We could cache the urls between languages but it doesn't seem to produce noticable slowdown
    translated_ui_string = mfutils.replace_format_specifiers_with_markdown_urls(translated_ui_string, urls_from_template)

    # Insert <img>s from the template into the translation
    imgs_from_template = mfutils.replace_html_images_with_format_specifiers(template_ui_string).removed_imgs
    translated_ui_string = mfutils.replace_format_specifiers_with_html_images(translated_ui_string, imgs_from_template)

    # Apply the original indentation to the translation
    indent_level, indent_char = mfutils.get_indent(template_ui_string)
    assert indent_char == ' ' or indent_char == None
    translated_ui_string = mfutils.set_indent(translated_ui_string, indent_level, ' ')

    # Return 
    return translated_ui_string

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

def find_exported_xcstrings_files(repo_root: str) -> list[str]:

    # Use this instead of globbing for .xcstrings files directly [Oct 2025]

    result = [os.path.normpath(p) for p in glob.glob(repo_root + '/**/*.xcstrings', recursive=True)]
    result = [x for x in result if x not in xcstrings_blacklist]
    return result

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
# Sourcefile parsing 
#   (Extracting localizable strings from .markdown/.vue files.)
#

def add_index_prefix_to_key(key: str, key_index: int, max_index: int) -> str:

    """
    'index_prefix' explanation:
        When we extract localized strings from the SomeDoc.md template, we then prepend an 'index_prefix' to the localized string keys, before storing the keys inside SomeDoc.xcstrings. 
        That way, the order of localizable strings inside SomeDoc.xcstrings is the same as in SomeDoc.md. (That is, when sorting SomeDoc.xcstrings file alphanumerically by key, which is the default in the Xcode editor)
        This should make it easier for localizers to understand and navigate SomeDoc.xcstrings or the .xcloc file derived from it.
        
        To implement this, we need to add/remove the index_prefixes at various points inside our syncstrings and buildmd scripts. (as of 09.09.2024)

        Examples:                               (Last updated on 10.09.2024)
            Example 1:
                Input:
                    key:        some.key
                    key_index:  0               (-> this key is the 1st one that appears in the template)
                    max_index:  50
                Output:
                    01: some.key                 (Note that we have 0-based indexes in the input, and 1-based indexes in the output, since I think 1-based indices look friendlier to localizers.)

            Example 2:
                Input:
                    key:        some.other.key
                    key_index:  3               (-> this key is the 4th one that appears in the template)
                    max_index:  150
                Output:
                    004: some.other.key          (Note that we're padding the key_index with zeros up to the width of the max_index. Otherwise you'd have have problems with where e.g. '12' < '2' under alphanumeric sorting. [Whereas '02' < '12' which is what we want.])
    """

    key_index += 1 # Make index 1-based instead of 0-based
    max_index += 1 # Also make max_index 1-based.

    max_index_width = len(str(max_index))
    padded_index = str(key_index).zfill(max_index_width)
    result = padded_index + ': ' + key              # Note that we're adding a space after the colon (:) for better legibility in the .xcstrings file.

    return result

def remove_index_prefix_from_key(key: str) -> str:
    
    result = None
    
    if ':' in key:
        index_prefix, result = key.split(':')
        if result[0] == ' ': # Strip the first space after the colon (:), since we sometimes add a space after the colon and sometimes not.
            result = result[1:]
        assert index_prefix.isdigit(), f"The prefix {index_prefix} before ':' in key {key} contains non-digit characters. This shouldn't happen. The characters before the first ':' are reserved for the index prefix."
    else:
        result = key

    return result


def get_localizable_strings_from_markdown(md_string: str):


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
    - The block syntax was created in this regex101 project: https://regex101.com/r/R39rXW/3
    - To test, you might want to post the whole .md file on regex101. That way you can see any under or overmatching which might not be obvious when testing a smaller example string.

    """

    # Declare return type
    @dataclass
    class LocalizedStringData:
        condition: str | None       # A string specifying the condition under which to include this localizable string in the rendered document (Instead of this we should probably just use our more powerful jinja-style {% if blocks %} – See conditional_render_with_jinja_if_blocks())
        key: str                    # a.key.that identifies the string across different languages
        key_with_index_prefix: str  # Key that looks like 001:some.key or 002:some.other.key, etc. Where we call '002:' the 'index_prefix'. The index tells us the order that the keys appear in the template.
        value: str                  # The user-facing string in the development language (english). The goal is to translate this string into differnt languages.
        comment: str | None         # A comment providing context for translators.
        full_match: str             # The entire substring of the .md file that we extracted the key, value, comment (and condition) from. Replace all full_matches with translated strings to localize the .md file.

    # Extract translatable strings with inline syntax
    inline_regex = r"\{\{(.*?)\|\|(.*?)\|\|(.*?)\}\}"           # r makes it so \ is treated as a literal character and so we don't have to double escape everything
    inline_matches: re.Iterator[re.Match[str]] = re.finditer(inline_regex, md_string)
    
    # Extract translatable strings with block syntax
    block_regex = r"^[^\S\r\n]*?```(?:\n\s*?if:\s*(.*?)\s*)?\n\s*?key:\s*(.*?)\s*\n\s*?```\n\s*(^.*?$)\s*```\n\s*?comment:\s*?(.*?)\s*\n\s*?```"
    block_matches: re.Iterator[re.Match[str]] = re.finditer(block_regex, md_string, re.DOTALL | re.MULTILINE)

    # Get ranges of all HTML comments
    comment_regex = r"<!--.*?-->"
    comment_matches: list[re.Match[str]] = list(re.finditer(comment_regex, md_string, re.DOTALL | re.MULTILINE))

    # Assemble result

    all_matches = list(map(lambda m: ('inline', m), inline_matches)) + list(map(lambda m: ('block', m), block_matches)) # 'all' matches doesn't included comments [Sep 2025]
    all_matches.sort(key=lambda match: match[1].start(0)) # Sort by where the match appears in the string

    result: list[LocalizedStringData] = []
        
    for i, match in enumerate(all_matches):
        
        # Get info from match
        
        full_match = match[1].group(0)
        condition = None
        comment = None
        value = None
        key = None
        key_with_index_prefix = None
        
        if match[0] == 'inline':
            value, key, comment = match[1].groups()
        elif match[0] == 'block':
            condition, key, value, comment = match[1].groups()    
        else: 
            assert False    

        # Filter out HTML comments
        continue_outer_loop = False
        for comment_match in comment_matches:
            if (comment_match.start(0) <= match[1].start(0)) and (match[1].end(0) <= comment_match.end(0)):
                print(f"syncstrings.py: Skipping localized string '{key}' since it's commented out inside the template.")
                continue_outer_loop = True
                break
        if continue_outer_loop: continue

        # Validate
        assert ' ' not in (condition or ''), f'condition contains space: {condition}'
        assert ' ' not in key, f'key contains space: {key}' # I don't think keys are supposed to contain spaces in objc and swift. We're trying to adhere to the standard xcode way of doing things. 
        assert len(key) > 0   # We need a key to do anything useful
        assert len(value) > 0 # English ui strings are defined directly in the markdown file - don't think this should be empty
        for st in [condition or '', value, key, comment]:
            assert r'}}' not in st, f"st: {st}" # Protect against matching past the first occurrence of }}
            assert r'||' not in st, f"st: {st}" # Protect against ? - this is weird
            assert r'{{' not in st, f"st: {st}" # Protect against ? - this is also weird
        # TODO: Maybe somehow protect against over matching on block syntax, too
        
        # Strip results
        #   The comment sometimes contained whitespace, I'm not sure if the key can contain whitespace with the way the regex is set up.
        #   Stripping the value is not good since we want to preserve the indent (Update: [Jul 2025] Might be cleaner to strip the indent here and return the indent as a number.)
        key = key.strip()
        comment = comment.strip() 

        # Guard duplicate keys
        assert all(key != k.key for k in result), f"There's a duplicate key '{key}' in the md file."

        # Get key_with_index_prefix
        key_with_index_prefix = add_index_prefix_to_key(key, i, len(all_matches) - 1)
        
        # Store
        result.append(LocalizedStringData(condition, key, key_with_index_prefix, value, comment, full_match))
    
    # Return
    
    return result

def get_localizable_strings_from_website_source_code(source_code: str):

    """
    Returns a list of LocalizedStringData instances extracted from the `source_code` string.

    We do this by looking for invocations of the ```MFLocalizedString(<englishUIString>, <key>, <comment>)``` function in the source code, and returning the <englishUIString>, <key>, and <comment> triplets we find in a list.

    Notes: 
    - Regex was created/tested with this regex101 project: https://regex101.com/r/HkyrTo
    - This function is very similar to the get_localizable_strings_from_markdown() function. Maybe we should combine them into one?
    """

    # Declare return type
    @dataclass
    class LocalizedStringData:
        key: str                    # a.key.that identifies the string across different languages
        key_with_index_prefix: str  # Key that looks like 001:some.key or 002:some.other.key, etc. Where we call '002:' the 'index_prefix'. The index tells us the order that the keys appear in the source code (usually .vue files).
        value: str                  # English UI String
        comment: str | None         # A comment providing context for translators.
        full_match: str             # The entire substring of the source file that we extracted the key, and comment from. Replace all full_matches with translated strings to localize the .md file.

    # Extract translatable strings
    #    using regex that matches ```MFLocalizedString('<english ui string>', '<key>', '<localizerHint>')``` calls.
    #    Notes:
    #       - We created and tested this regex using regex101.com - using the source code of index.vue as the test string.
    #       - [Feb 2025] When testing this on regex101.com, don't forget to set the flavour (python) and the flags (re.DOTALL | re.MULTILINE).
    #       - [Feb 2025] Added matching for code comments, is this overkill?

    regex = r"""(?x)                                            # `(?x)` activates verbose mode. (Letting us use comments and linebreaks inside the regex)
    MFLocalizedString                                           # Match 'MFLocalizedString'
    (\s*?((/\*.*?\*/)|(//.*?$)))*?                              # Match code comments
    \s*?\(                                                      # Match opening parenthesis
    (\s*?((/\*.*?\*/)|(//.*?$)))*?                              # Match code comments
    \s*?(?P<quote_1>[`'\"])(?P<value>.*?)(?<!\\)(?P=quote_1)    # Match Match English UI string      (Note: `(?<!\\)` prevents the backreference `(?P=quote_1)` from matching escaped quotes (such as `\'`))
    (\s*?((/\*.*?\*/)|(//.*?$)))*?                              # Match code comments
    \s*?,                                                       # Match comma 1
    (\s*?((/\*.*?\*/)|(//.*?$)))*?                              # Match code comments
    \s*?(?P<quote_2>[`'\"])(?P<key>.*?)(?<!\\)(?P=quote_2)      # Match localization key. (Note: The key being empty or containing any char except [a-zA-Z0-9\.\-] is an error. But we still match in those cases so we can notify the developer about the error.)
    (\s*?((/\*.*?\*/)|(//.*?$)))*?                              # Match code comments
    \s*?,                                                       # Match comma 2
    (\s*?((/\*.*?\*/)|(//.*?$)))*?                              # Match code comments
    \s*?(?P<quote_3>[`'\"])(?P<comment>.*?)(?<!\\)(?P=quote_3)  # Match localizer hint
    (\s*?((/\*.*?\*/)|(//.*?$)))*?                              # Match code comments
    \s*?,?                                                      # Match trailling comma (See https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Trailing_commas)
    (\s*?((/\*.*?\*/)|(//.*?$)))*?                              # Match code comments
    \s*?\)                                                      # Match closing parenthesis
    """

    """
    On VSCode search:

        Steps to transform the regex for use in **VSCode Search**:
                (Last updated: Sep 2024)
            1. Replace `.` with `[\s\S\r]` to match all chars including newlines.
            2. Wrap all the comma and parens sections into capture groups (so we can reuse them in the `replace` field.)
            3. Remove any `\` before `'` and `"`, since that's an 'invalid escape sequence'.
            4. Remove the python capture group **names** (The `P?<>` syntax), to turn the capture groups into regular, numbered capture groups.
            5. Replace python's named-capture-group-backreferences (The `(?P=)` syntax) with regular numbered-capture-group-backreferences (`\1`, `\2` etc.)
            6. Remove comments and whitespace
            7. Move everything onto one line
    
        Result: [Sep 2024]
            MFLocalizedString(\s*?\(\s*?)([`'"])([\s\S\r]*?)(?<!\\)\2(\s*?,\s*?)([`'"])([\s\S\r]*?)(?<!\\)\5(\s*?,\s*?)([`'"])([\s\S\r]*?)(?<!\\)\8(\s*?,?)(\s*?\))
        Result: [Feb 2025] (After adding comment matching)
            <Fill in when needed>

    """

    matches = list(re.finditer(regex, source_code, re.DOTALL | re.MULTILINE))

    # Assemble result
    result: list[LocalizedStringData] = []

    for i, match in enumerate(matches):

        # Get info from match
        groupdict = match.groupdict()

        full_match = match.group(0)
        comment = groupdict['comment']
        value = groupdict['value']
        key = groupdict['key']
        key_with_index_prefix = None
        
        # Validate
        assert re.match(r"[^a-zA-Z0-9\.\-]", key) == None ,                             f"key contains invalid characters: '{key}' (Should only contain a-z, A-Z, 0-9, . or -)"
        assert len(key) > 0,                                                            f"key is empty. Need a key to do anything useful."
        assert all((r'MFLocalizedString(' not in st) for st in [value, key, comment]),  f"value, key, or comment contains 'MFLocalizedString('. This probably means the regex over-matched.\nvalue:{value}\nkey:{key}\ncomment:{comment}"
        
        # Strip results
        #   As they appear in the source code, the `comment` and `value` strings may be 
        #       - Indented
        #       - Contain leading/trailling empty lines
        #       We want to remove these things here, since these things are not part of the localized string, but just artifacts to make them nicely writable in the source code.
        #       
        #   Sidenote: I'm not sure if the key can contain whitespace with the way the regex is set up.

        def cool_strip(s: str) -> str:

            # Remove leading/trailling empty lines
            s = mfutils.trim_empty_lines(s)

            # Remove indent
            s = mfutils.set_indent(s, 0, '')

            # Return 
            return s

        key = cool_strip(key)
        value = cool_strip(value)
        comment = cool_strip(comment)

        # TEST
        #   Skip duplicate keys. Right now, we sometimes use the same key twice in the same .vue file. Maybe we should restructure .vue files to avoid this, and then assert 'no duplicate keys' here.
        if not all(key != k.key for k in result):
            continue

        # Get key_with_index_prefix
        key_with_index_prefix = add_index_prefix_to_key(key, i, len(matches) - 1)
        
        # Store
        result.append(LocalizedStringData(key, key_with_index_prefix, value, comment, full_match))
    
    # Return
    return result

#
# URL Localization
#

# Discussion [Mar 2025] 
#   This finds URLs following specific patterns in a text and replaces them with localized versions. 
#   I wrote this is for our AI translation system for the update notes.
#   In general, we should prefer a mored structure approach where we generate the URLs in code, and insert them via format specifiers.
#   However, this more dynamic approach was the best I could come up with for this purpose (Translating all the existing update notes from GitHub Releases)

def localize_urls(source_locale: str, locale: str, text: str) -> str:
    
    # URL prefix patterns
    #   For the urls we wanna localize
    #   Note: `s?` lets us match `http` and `https` (not sure that's necessary)
    urlpref_redirect1   = 'https?://redirect.macmousefix.com'
    urlpref_redirect2   = 'https?://noah-nuebling.github.io/redirection-service'
    urlpref_ghrelease = 'https?://github.com/noah-nuebling/mac-mouse-fix/releases'

    # Replace urls for our 'redirection-service'
    def replurls_redirection_service(url: str) -> str:
        def f(querydict): querydict['locale'] = [locale]
        new_url = _modify_query_params_in_url(f, url)
        print(f"Replacing url '{url}' -> '{new_url}'")
        return new_url
    text = _replace_urls_in_text(replurls_redirection_service, [urlpref_redirect1, urlpref_redirect2], text)

    # Replace urls for direct links to GitHub Releases
    def replurls_ghreleases(url: str) -> str:
        if locale == source_locale: # The GitHub Releases pages are already in the source language (English)
            return url
        if url.endswith('/'): url = url[:-1]
        if url.endswith('releases'):                    # Trying to match url https://github.com/noah-nuebling/mac-mouse-fix/releases/
            new_url = mmf_release_overview_url(locale)
        elif '/tag/' in url:                            # Trying to match urls https://github.com/noah-nuebling/mac-mouse-fix/releases/tag/<releasetag>
            parsed = urllib.parse.urlsplit(url)
            release_tag = parsed.path.split('/')[-1]
            new_url = mmf_release_url(locale, release_tag)
        else: assert False, f"Unexpected GitHub Releases URL: {url}"
        print(f"Replacing url '{url}' -> '{new_url}'")
        return new_url
    text = _replace_urls_in_text(replurls_ghreleases, [urlpref_ghrelease], text)

    # Return
    return text

def mmf_release_overview_url(locale: str) -> str:
    result = f"https://redirect.macmousefix.com/?target=mmf-releases-overview&locale={locale}"
    return result

def mmf_release_url(locale: str, release_tag: str) -> str:
    # Note: [Mar 2025] The original GitHub Releases pages are in the source language (English) 
    #   They are at `https://github.com/noah-nuebling/mac-mouse-fix/releases/tag/{release_tag}`
    #   Users of this function might wanna link to that directly for decreased page loading times (?) That theoretically makes things less flexible if we ever wanna move the releases to another address, but I think in that case, we'll have to restructure this a bit anyways.
    result = f"https://redirect.macmousefix.com/?target=mmf-release&tag={release_tag}&locale={locale}"
    return result

def _find_urls_in_text(url_prefix_patterns: list[str], text: str) -> list[str]:

    # Regex pattern matching chars that might appear in a URL
    #   Sources: 
    #       - https://support.exactonline.com/community/s/knowledge-base#All-All-DNO-Content-urlcharacters
    #       - http://www.blooberry.com/indexdot/html/topics/urlencoding.html
    #   Notes:
    #       - The only allowed type of 'enclosing' chars are `(` and `)`.
    #       - `,` and `'` are allowed - weird!
    #       - What is `;` reserved for?
    #  Also see:
    #       - John Gruber's solution: https://daringfireball.net/2010/07/improved_regex_for_matching_urls
    purlchar = mfutils.mfdedent(r"""
        (?x)
        [0-9a-zA-Z]         # Alphanumerics
        |
        [\$\-_\.\+!\*'\(\),] # Other 'safe' chars
        |
        [;\/?:@=&]          # 'reserved' chars
        |
        [#%]                # 'unsafe' chars that are used inside URLs (Why aren't these considered 'reserved'?)
        """)

    # Find urls in text
    result = []
    for i in range(len(text)):      # Note: [Mar 2025] Not sure it causes any significant slowdown to manually iterate through each index? Using regex for this is probably faster, but this works.
        
        # Find URL start
        match = None
        for pat in url_prefix_patterns:
            if match := re.match(pat, text[i:], re.NOFLAG): 
                break

        # Skip
        if match is None: continue

        # Find end of URL
        #   Note: 
        #   - The parentheses-depth-tracking is because URLs can contain `(` and `)`, 
        #       but markdown also uses `)` as a delimiter e.g. in `[abc](https://google.com/)`
        #       Based on minimal testing on https://kip2.github.io/MarkdownToHTML/:
        #           It seems that markdown parsers resolve this ambiguity by counting matching parentheses inside the URL. 
        #           (Also making them incompatible with URLs containing unbalanced parentheses)
        #           We're mirroring that behavior here.
        #       For urls with mismatched parentheses outside of [markdown](links), there might be some cases where this fails to parse the url, while a markdown parser would succeed. (Haven't tested this) But that's an edge-case.
        paren_depth = 0
        urlend = None                       # Note: [Mar 2025] If we don't find a urlend before the end of the text, this stays None, and we slice to the end of the text – which is correct.
        for j in range(i+1, len(text)):
            c = text[j]
            if      '(' == c: paren_depth += 1
            elif    ')' == c: paren_depth -= 1
            is_urlchar = None is not re.match(purlchar, c, re.NOFLAG)
            is_urlend = not is_urlchar or (paren_depth < 0)
            if is_urlend: 
                urlend = j
                break
        
        # Get URL
        url = text[i:urlend]

        # Store URL
        result.append(url)

    # Return
    return result

def _replace_urls_in_text(url_replacer: Callable[[str], str], url_prefix_patterns: list[str], text: str) -> str:

    # Define datatype
    @dataclass
    class Replacement:
        old: str
        new: str

    # Find urls
    urls = _find_urls_in_text(url_prefix_patterns, text)

    # Get replacements for the urls
    url_replacements: list[Replacement] = []
    for url in urls:
        new_url = url_replacer(url)
        url_replacements.append(Replacement(old=url, new=new_url))

    # Replace urls
    searchi = 0
    new_release_notes = text
    for repl in url_replacements:
        oldlen = len(repl.old); newlen = len(repl.new)
        foundi = new_release_notes.find(repl.old, searchi, None)
        new_release_notes = new_release_notes[:foundi] + repl.new + new_release_notes[foundi+oldlen:]
        searchi = foundi + newlen
    
    # Return
    return new_release_notes

def _modify_query_params_in_url(param_modifier: Callable[[dict[str, list[str]]], None], url: str) -> str:
        
        # Parse url
        parsed_url = urllib.parse.urlparse(url)

        # Extract query
        query = parsed_url.query
        querydict = urllib.parse.parse_qs(query, keep_blank_values=True, strict_parsing=True)

        # Apply modification
        param_modifier(querydict)

        # Assemble query
        new_query = urllib.parse.urlencode(query=querydict, doseq=True)

        # Assemble url
        new_parsed_result = parsed_url._replace(query=new_query)
        new_url = urllib.parse.urlunparse(new_parsed_result)

        # Return
        return new_url

#
# MainRepo document paths
#
# Naming:
#   [Jul 2025] We use prefix `mainmdp_` which stands for: Functions for obtaining file [p]aths involved in compiling and translating .[md] files in the [main] repo (The 'main' repo is mac-mouse-fix)
#
# Context: 
#   [Jul 2025] These functions are used by the scripts that translate markdown documents in the main repo. (_buildmd.py and syncstrings.py)
#   The functions here have knowledge about where all the files (templates, xcstrings, compiled) should go. To share this knowledge between the scripts, we're putting it here into shared/mflocales. Maybe we should just combine those two scripts into one?
#
# Explanation:
#   syncstrings.py  extracts the localizable data from the `templates` and updates the `xcstrings` files with that.
#   _buildmd.py     takes a `template` .md file plus an `.xcstrings` file and then compiles them into a series of localized `compiled` .md files - one for each locale in the .xcstrings file.
#   
#   The `template`, `xcstrings`, and `compiled` files all have the same filename stem, but with different extensions. 
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
#   To compile one of these documents, run _buildmd.py and pass in the `filename stem` ('Readme' in this example) as the `--document`
#   
# Notes:
#   - All the hardcoded paths in this script are relative to the root directory of the repo - we expect this script to be run from the repo root.

mainmdp_template_root = "Markdown/Templates"                                        # The script will look for document templates in this directory (It's relative to the repo root)
mainmdp_xcstrings_root = "Markdown/Strings"                                         # The script will look for xcstrings files in this dir
mainmdp_compiled_doc_root_for_development_locale = ""                                  # Compiled documents in the 'development language' (English) will be put into this dir
mainmdp_compiled_doc_root_for_translated_locales = "Markdown/LocalizedDocuments"       # Compiled documents in translated languages will be put into this dir

from enum import Enum
class mainmdp_DocType(Enum):
    TEMPLATE = 2
    XCSTRINGS = 1
    COMPILED_DOC = 3

def mainmdp_get_document_keys():
    
    # Returns the relative filepaths of all files in the 'mainmdp_template_root' folder.
    # These filepaths are used as 'document keys' - they identify a certain document that we might want to compile.

    result_lowercase = []
    result = []

    for filepath in glob.glob(f"{mainmdp_template_root}/**/*.md", recursive=True):
        
        # Normalize
        filepath = filepath[len(mainmdp_template_root)+1:]

        # Get stem
        filename_stem, ext = os.path.splitext(filepath)

        # Filter stuff
        if "Old (for reference)/" in filepath: continue
        if (0): 
            if not os.path.isfile(filepath): continue
        if not ext == '.md': continue

        # Store result
        result.append(filepath)

        # Validate
        assert filepath.lower() not in result_lowercase, f"Found duplicate template name: {filepath}. (Checked case-insensitively.) (This is a problem because the template names determine the document keys, which we might want to use case-insensitively. So the template names need to be case-insensitively unique.)"
        result_lowercase.append(filepath.lower())
    
    return result

def mainmdp_construct_path(filepath: str, doc_type: mainmdp_DocType, locale: str|None = None, development_locale: str = 'en'):

    assert filepath.endswith('.md')
    filepath_stem = filepath[0:-3]

    match doc_type:
        case mainmdp_DocType.TEMPLATE:
            return os.path.join(mainmdp_template_root, filepath_stem + '.md')
        
        case mainmdp_DocType.XCSTRINGS:
            return os.path.join(mainmdp_xcstrings_root, filepath_stem + '.xcstrings')
        
        case mainmdp_DocType.COMPILED_DOC:

            assert locale != None and len(locale) > 0

            if (locale == development_locale):
                return os.path.join(mainmdp_compiled_doc_root_for_development_locale, filepath_stem + '.md')
            else:
                return os.path.join(mainmdp_compiled_doc_root_for_translated_locales, locale, filepath_stem + '.md')
        
        case _:
            assert False
            return None

def mainmdp_path_to_repo_root(path):
    parent_count = len(Path(path).parents)
    root_path = '../' * (parent_count-1)
    return root_path

def mainmdp_path_to_compiled_doc_root(thisdoc_path: str, locale: str, development_locale: str):
    
    # Construct docroot for locale
    docroot = None
    if locale == development_locale:
        docroot = mainmdp_compiled_doc_root_for_development_locale
    else:
        docroot = os.path.join(mainmdp_compiled_doc_root_for_translated_locales, locale)
    
    # Validate
    assert(thisdoc_path.startswith(docroot))

    # Get thisdoc path relative to docroot.
    thisdoc_path_relative = thisdoc_path.removeprefix(docroot)

    # Construct path from thisdoc to docroot
    parent_count = len(Path(thisdoc_path_relative).parents)
    root_path = '../' * (parent_count-1)

    # Return
    return root_path
