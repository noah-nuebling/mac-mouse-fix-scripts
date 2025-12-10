# quotes-damage-control.py: Hacky script for replacing dumb-quotes -> smart-quotes. [Dec 2025]
#   History & Purpose: [Dec 2025]
#       - I used find/replace in VSCode to replace smart-quotes -> dumb-quotes across all of mac-mouse-fix repo. 
#           But then I found that this shouldn't be done for zh-Hans, since dumb quotes mess up Chinese character spacing.
#           (See 333eaa574edf0301d7db0efa3462a9d87a4337e6 in mac-mouse-fix)
#       - Then I used this script to restore the smart-quotes for zh-Hans. 
#           (Ran 'fix' mode with 'zh-Hans' locale.)
#       - I also used this script to validate that the other dumb-quotes -> smart-quotes replacements were reasonable 
#           (Ran 'overview' mode on 'before' commit 0fb93ee4c0f598ea224223b7c90c335a40bdd3db and 'after' commit 4efa4b16149ca387ab8776777604804bc3840be8)
#           -> From this I could see that smart quotes weren't consistently used by any other locale than zh-Hans.)

import glob
import json
from pathlib import Path
import textwrap
import re

def count_single_quotes(s):
    if (0): # Don't think this is heuristic is correct [Dec 2025]
        return len(re.findall('( \'|\' )', s)) # English uses ' in other contexts like `You're Marc's best friend`.
    else:
        return s.count('\'')
    

def main():

    locale = 'cs'
    mode = 'overview' # 'count'/'fix'/'print'/'overview'

    if mode == 'overview': # Print counts for all files by locale
        
        # Load all xcstrings files.
        xcstrings_objs = {};
        for f in glob.glob("**/*.xcstrings", recursive=True):
            xcstrings_objs[f] = json.loads(Path(f).read_text())

        # Get all locales
        locales: set = set();
        for f, xcstrings_obj in xcstrings_objs.items():
            for key in xcstrings_obj['strings']:
                locales = locales.union(set(xcstrings_obj['strings'][key].get('localizations', {}).keys()))
        
        print(f"Found locales: {locales}")

        # Init result
        result = {}
        for locale in locales:
            result[locale] = {
                'all_dumb_double': 0,
                'all_dumb_single': 0,
                'all_smart_double': 0,
                'all_smart_single': 0,
            }

        # Gather quote-counts
        for xcstrings_obj in xcstrings_objs.values():
            for key in xcstrings_obj['strings']:
                
                if not xcstrings_obj['strings'][key].get('shouldTranslate', True): 
                    continue;
                for locale in xcstrings_obj['strings'][key].get('localizations', {}):
                    zh: str = (
                        xcstrings_obj['strings'][key].get('localizations', {})
                            .get(locale, {}).get('stringUnit', {}).get('value', None)
                    );
                    if zh:

                        new_all_dumb_double  = zh.count('"')
                        new_all_dumb_single  = count_single_quotes(zh);
                        new_all_smart_double = zh.count('“') + zh.count('”')
                        new_all_smart_single = zh.count('‘') + zh.count('’')
                        
                        result[locale]['all_dumb_double']   += new_all_dumb_double
                        result[locale]['all_dumb_single']   += new_all_dumb_single
                        result[locale]['all_smart_double']  += new_all_smart_double
                        result[locale]['all_smart_single']  += new_all_smart_single

                        # Fill 'keys_with_quotes'
                        if (0):
                            new_count_all = (0
                                + new_all_dumb_double
                                + new_all_dumb_single
                                + new_all_smart_double
                                + new_all_smart_single
                            )
                            if (new_count_all > 0):
                                result[locale]['keys_with_quotes'][key] = result[locale]['keys_with_quotes'].get(key, 0) + new_count_all;
        
        # # Fill 'n_keys_with_quotes'
        if (0):
            for locale in locales:
                result[locale]['n_keys_with_quotes'] = len(result[locale]['keys_with_quotes'])


        # Print
        print(textwrap.dedent(f"""Quote count overview: {json.dumps(result, indent=4, sort_keys=True)}\
        """))


    else:

        counter = {}

        counter['all_dumb_double'] = 0
        counter['all_dumb_single'] = 0
        counter['all_smart_double'] = 0
        counter['all_smart_single'] = 0

        for i, f in enumerate(glob.glob("**/*.xcstrings", recursive=True)):
            
            def mfindex(string: str, substring):
                try:
                    return string.index(substring, None, None);
                except:
                    return None

            # Log filename
            if mode == 'print':
                print('\n')
                print(f);

            # Load xcstrings file
            xcstrings_text = Path(f).read_text()
            xcstrings_obj = json.loads(xcstrings_text);

            # Init counts for this file
            counter['file_dumb_double'] = 0
            counter['file_dumb_single'] = 0
            counter['file_smart_double'] = 0
            counter['file_smart_single'] = 0

            # Counting helper fn
            def increment_quote_count(zh: str):

                cnt_dbl   = zh.count('“') + zh.count('”')
                cnt_snl   = zh.count('‘') + zh.count('’')

                cnt_dbl_dumb   = zh.count('"')
                cnt_snl_dumb   = count_single_quotes(zh);

                counter['file_dumb_double'] += cnt_dbl_dumb;
                counter['file_dumb_single'] += cnt_snl_dumb;
                counter['file_smart_double'] += cnt_dbl;
                counter['file_smart_single'] += cnt_snl;

                counter['all_dumb_double'] += cnt_dbl_dumb;
                counter['all_dumb_single'] += cnt_snl_dumb;
                counter['all_smart_double'] += cnt_dbl;
                counter['all_smart_single'] += cnt_snl;

            if mode == 'print':

                for key in xcstrings_obj['strings']:
                    
                    zh: str = xcstrings_obj['strings'][key].get('localizations', {}).get(locale, {}).get('stringUnit', {}).get('value', None);
                    if zh:
                        print(key, zh)

            # Count the smart quotes (for validation)
            if mode == 'count':

                for key in xcstrings_obj['strings']:
                    zh: str = xcstrings_obj['strings'][key].get('localizations', {}).get(locale, {}).get('stringUnit', {}).get('value', None);
                    if zh:
                        increment_quote_count(zh);

            # Fix broken xcstrings files by replacing dumb quotes.
            if mode == 'fix':

                # Modify xcstrings file    
                for key in xcstrings_obj['strings']:
                    
                    zh: str = xcstrings_obj['strings'][key].get('localizations', {}).get(locale, {}).get('stringUnit', {}).get('value', None);
                    if zh:
                        
                        og_zh = zh;

                        # Replace double-quotes "
                        counter_double = 0
                        state = 'closed';
                        while 1:
                            next_idx = mfindex(zh, '"');
                            if next_idx is None: break;

                            if state == 'closed':   
                                zh = zh.replace('"', '“', count=1);
                                print(f"Replaced opening quote: {zh}")
                            elif state == 'open':   
                                zh = zh.replace('"', '”', count=1)
                                print(f"Replaced closing quote: {zh}")
                            else: assert False

                            state = 'closed' if state == 'open' else 'open';

                            counter_double += 1

                        assert state == 'closed', f'Mismatched double-quotes in: {key} ({og_zh})'

                        # Replace single quotes '
                        counter_single = 0
                        state = 'closed';
                        while 1:
                            
                            if mfindex(zh, '\'') is None: break;

                            if state == 'closed':     zh = zh.replace('\'', '‘', count=1); # This wouldn't work on English. See count_single_quotes() (`You're`) [Dec 2025]
                            elif state == 'open':     zh = zh.replace('\'', '’', count=1)
                            else: assert False
                        
                            state = 'closed' if state == 'open' else 'open';

                            counter_single += 1
                            
                        assert state == 'closed', f'Mismatched single-quotes in: {key} ({og_zh})'
                        
                        # Log
                        if counter_double > 0:
                            print(f"Replaced {counter_double} double-quotes in {key}.")

                        if counter_single > 0:
                            print(f"Replaced {counter_single} single-quotes in {key}.")

                        # Count
                        if counter_double > 0:
                            counter['file_smart_double'] += counter_double
                            counter['all_smart_double']  += counter_double
                        if counter_single > 0:
                            counter['file_smart_single'] += counter_single
                            counter['all_smart_single']  += counter_single
                        
                        # Store modified string
                        xcstrings_obj['strings'][key]['localizations']['zh-Hans']['stringUnit']['value'] = zh;


            if counter['file_smart_double'] + counter['file_smart_single']:
                
                # Log result for this file
                if mode == 'count':
                    print(textwrap.dedent(f"""\
                        Counted for file ({f}):
                            smart quotes: {counter['file_smart_double']} double-quotes and {counter['file_smart_single']} single-quotes.
                            dumb  quotes: {counter['file_dumb_double']} double-quotes and {counter['file_dumb_single']} single-quotes. 
                    """))
                if mode == 'fix':
                    print(f"Writing modified xcstrings file. Replaced {counter['file_smart_double']} double-quotes and {counter['file_smart_single']} single-quotes. (File {f})")
                
                # Write result for this file
                if mode == 'fix':
                    Path(f).write_text(json.dumps(xcstrings_obj, indent=2, ensure_ascii=False, separators=(',', ' : ')));  


        # Log overall result
        if mode == 'fix':
            print(f"Overall: replaced {counter['all_smart_double']} double-quotes and {counter['all_smart_single']} single-quotes.")

        if mode == 'count':
            print(textwrap.dedent(f"""\
                Counted Overall: 
                smart quotes: {counter['all_smart_double']} double-quotes and {counter['all_smart_single']} single-quotes.
                dumb  quotes: {counter['all_dumb_double']} double-quotes and {counter['all_dumb_single']} single-quotes.
            """))

main();