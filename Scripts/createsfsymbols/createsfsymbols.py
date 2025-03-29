
import shlex
import mfutils
import os
import shutil
import tempfile

# Handle CFF Table
from fontTools.cffLib import CFFFontSet
from fontTools.cffLib import TopDict

# Handl eTTF Table
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._n_a_m_e import NameRecord

"""

This script generates a subset font of Apple's SF Pro font.

Explanation:  
    Normally, you should use NSImage to load an SF Symbol, but in some cases (For tooltips, where you have to use plaintext) that is not possible.
    To display SF Symbols in plaintext, we create a new font, that only contains the symbols we'd like to use, and then we ship the font with Mac Mouse Fix.
    
    Note that the system font of macOS does not have the ability to display SF Symbols. Only the SF fonts downloaded from Apple's website have this ability.

Why 'regular' variant of the font?:
    We're currently only exporting regular-weight-regular-width-sf-text (as opposed to -sf-display) symbols (by subsetting "SF-Pro-Text-Regular.otf"). 
    We could also export all variants of the symbols by using "SF-Pro.ttf" instead of "SF-Pro-Text-Regular.otf".
    However, SF-Pro-Text-Regular should be enough, since we only need to use this in tooltips, where we cannot control the stringAttributes and have to work with plainText
    displayed in the standard style and weight for system text on macOS. (Which uses weight 'regular'. See Apple human-interface-guidelines/typography)
    If we're in a context where there are any other font weights or widths being used, then we can probably control the attributedString, and then we can insert the SF Symbol 
    into our text through an NSImage, instead of using our custom font - which seems to be the standard approach supported by Apple.
    
    Note:
        Maybe use `Medium` font variant instead of 'Regular' since it might look closer to how we render the SF Symbols in our NSImages inside `keyStringWithSymbol:` in MMF? (There we use NSFontWeight 0.3 for lightMode and 0.4 for darkmode.)
        
For More info see CoolSFSymbolsFont.m in the Mac Mouse Fix repo.

"""

# Constant

postscript_name_for_output_font = "SFProText-Regular-WithLargeFry-AndExtraSauce" # Used in objc to find the font - keep in sync!

sf_file_name = "SF-Pro-Text-Regular.otf"
search_paths = ['./', '/Library/Fonts', '~/Library/Fonts', '/System/Library/Fonts']
output_file_name = "./CoolSFSymbols.otf"

# Define SFSymbols we want to export
#   -> NOTE: Keep this in sync with the fallback strings inside `UIStrings -getStringForSystemDefinedEventOrSymbolicHotkey:`

symbolic_hotkey_symbols = """\
􀆫
􀆭
􀊉
􀊇
􀊋
􀊠
􀊤
􀊨
􀇭
􀇮
􀆨
􀆡
"""

system_defined_event_symbols = """\
􀇴
􀊰
􀊫
􀆹
􀆪
􀇵
"""

some_other_sf_symbols_that_we_dont_include = "􀥺􀛸􁖎􀜊􁘭􁜪􀯓" # To test installing/uninstalling our font interspersed with activating/deactivating SF Pro Text - to see if there are any conflicts.

symbols = (symbolic_hotkey_symbols + system_defined_event_symbols).replace('\n', '').replace('\t', '').replace(' ', '')

def main():

    # Search SF Font
    sf_file_path = None
    for search_path in search_paths:
        maybe_sf_file_path = os.path.abspath(os.path.join(search_path, sf_file_name))
        if os.path.exists(maybe_sf_file_path):
            sf_file_path = maybe_sf_file_path
            break
    
    # Validate
    assert sf_file_path is not None, f"No SF font file of name '{sf_file_name}' found in search paths '{search_paths}. You can download the font from the Apple website. (You can then deactivate it in FontBook without uninstalling it and this script will still work.)'"

    # Convert to unicode
    unicodes = [ord(s) for s in symbols]
    
    # Convert to fonttools input format
    unicodes_arg = ",".join(map(lambda c: hex(c)[2:], unicodes)) # [2:] cuts off the 0x prefix of the hex numbers

    # Get output path
    tempdir = tempfile.gettempdir()
    output_file_path = os.path.join(tempdir, output_file_name)

    # Validate that fonttools is installed
    assert shutil.which('fonttools') is not None, f"This script requires fonttools which is not available. To install fonttools run: pip install fonttools"
    
    # Call fonttools
    #   Create a subset
    #   Not totally sure what I'm doing with the args
    mfutils.runclt(f"fonttools subset {shlex.quote(sf_file_path)} --unicodes={unicodes_arg} --output-file={shlex.quote(output_file_path)} --glyph-names --no-ignore-missing-unicodes --no-ignore-missing-glyphs", print_live_output=True)

    # Update the nameTable records for the font
    #   Why update all the names? 
    #       We update all fields that show up in FontForge to prevent any potential name conflicts if the user has the real SF Pro fonts installed. (This font is generated as a subset of an SF Pro fonts and initially has the same names and identifiers) Please don't sue me Apple thank you.
    #   Very confusing API, based this implementation on:
    #   - Microsoft docs ('name' table record indexes) : https://learn.microsoft.com/en-gb/typography/opentype/spec/name#name-ids
    #   - Python debugger ('CFF ' table)
    #   - Fonttools example code (general renaming usage): https://github.com/fonttools/fonttools/blob/main/Snippets/rename-fonts.py

    ttFont = TTFont(output_file_path)
    name_table = ttFont["name"] 
    name_records: list[NameRecord] = name_table.names # What is this api

    def append_to_record(record: NameRecord, appendix: str):
        record.string = (record.toUnicode() + appendix).encode('utf-16-be')

    append_to_record(name_records[0], " Please don't sue me Apple.")                # Update Copyright notice "© 2015-2024 Apple ..."  || Note1: FontForge complains that the family name is too long for some versions of Windows, if we go over 31 char limit || Note2: We put praying hands emojis here but they are stripped from the output
    append_to_record(name_records[1], " but different")                             # Update Font Family name "SF Pro Text"
    append_to_record(name_records[2], " soda please")                               # Update font subfamily name "Medium"
    append_to_record(name_records[3], "-but-different")                             # Update UID "SF Pro Text Medium; 20.0d8e1; 2024-05-22"
    append_to_record(name_records[4], " soda please")                               # Update full name "SF Pro Text Medium"
    append_to_record(name_records[5], "butdiffernt")                                # Update Version "Version 20.0d8e1" (lack of spaces is intentional)
    name_records[6].string = postscript_name_for_output_font.encode('utf-16-be')    # Replace postscript name "SFProText-Medium" (Doesn't show up in FontForge I think, but does show up as the NSFontNameAttribute for the fontDescriptor in objc.)
    pass                                                                            # Index 7 is out of range for this font
    
    ttFont["name"].names = name_records
    
    # Update the CFF Table
    #   No idea what that is, but have to do this to make all the fields in FontForge be renamed
    
    cf_table = ttFont['CFF ']
    cf_set: CFFFontSet = cf_table.cff
    cf_top_dicts: list[TopDict] = cf_set.topDictIndex
    
    assert len(cf_top_dicts) == 1
    
    for (i, topDict) in enumerate(cf_top_dicts):
        
        # Notes:
        # - There's also a ```'Weight' = 'Medium'``` field in the dict but not updating that maybe the name is magic.`
        
        topDict.rawDict["FullName"] += " Soda Please"                           # Update FullName "SFProText Regular"
        topDict.rawDict["FamilyName"] += "IsTotallyDifferentFromThis"           # Update FamilyName "SFProText"                 Note: I think this is also a postscript name and could be used to find the font in objc?
        cf_set.fontNames[i] = postscript_name_for_output_font                   # Update postscript name "SFProText-Regular" .  Note: Need to update this weird way (not through the topDict or nameRecord) to show up in FontForge.
        
    # Write to file
    ttFont.save(output_file_path)
    ttFont.close()
    
    # Print success
    unicodes_print = ','.join([hex(u) for u in unicodes])
    symbols_print = '  '.join(symbols) + '  '
    names_print = ', '.join(['(' + r.toStr() + ')' for r in ttFont["name"].names])
    cff_print = 'cffFontNames: ' + str(cf_set.fontNames) + 'cffTopDicts: ' + ', '.join(['(' + str(topDict.rawDict) + ')' for topDict in ttFont["CFF "].cff])
    print(f"Exported symbols [{unicodes_print}] ({symbols_print}) from San Francisco font at {sf_file_path}\nto new font file:\n\n{output_file_path}\n\n    (^^^Include this file in the MMF Xcode project)\n\nUpdated font's name_table: [{names_print}].\nUpdated font's cff_table: {cff_print}")
    
    
if __name__ == '__main__':
    main()
