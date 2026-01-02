
"""

This scripts creates .xcloc files for the MMF project and publishes them on GitHub.

"""

#
# Imports
# 

from dataclasses import dataclass
import tempfile
import os
import json
import shutil
import glob
import argparse
from pathlib import Path
from typing import Any, cast
import sys
import re
import requests
import plistlib

#
# Import functions from /shared folder
#

import mfutils
import mflocales
import mfgithub

# Print sys.path to debug
#   - This needs to contain the ../shared folder in oder for the import and VSCode completions to work properly
#   - We add the ../shared folder to the path through the .env file at the project root.

# print("Current sys.path:")
# for p in sys.path:
#     print(p)

# Note about vvv: Since we add the ../shared folder to the python env inside the .env file (at the project root), we don't need the code below vvv any more. Using the .env file has the benefit that VSCode completions work with it.

# code_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
# if code_dir not in sys.path:
#     sys.path.append(code_dir)
# from shared import shared

#    
# Constants
#

website_repo = './../mac-mouse-fix-website'

translation_guide_path     = sys.path[0] + '/translation_guide.md'
how_to_submit_path         = sys.path[0] + "/How To Submit Your Translations.txt"
about_app_screenshots_path = sys.path[0] + "/About App Screenshots.txt"

app_screenshots_link_name = 'App Screenshots'

xcloc_editor_download_url    = "https://github.com/noah-nuebling/mf-xcloc-editor/releases/latest/download/XclocEditor.zip"

translation_guide_github_issue_id = "1638"

# Screenshots
xcode_screenshot_taker_output_dir_variable = "MF_LOCALIZATION_SCREENSHOT_OUTPUT_DIR"
xcode_screenshot_taker_locale_variable     = "MF_LOCALIZATION_SCREENSHOT_LOCALE"
xcode_screenshot_taker_build_scheme = "Localization Screenshot Taker"
xcode_screenshot_taker_test_case    = "Localization Screenshot Taker/LocalizationScreenshotClass/testTakeScreenshots_Localization" # [Sep 2025] See: https://stackoverflow.com/a/37971495/10601702 || [Sep 2025] We've added testTakeScreenshots_Documentation() testcase now so we need to specify the test case
xcloc_screenshots_subdir = "Notes/Screenshots/"    # [Jan 1 2025] Simplify from "Notes/Screenshots/SomeTest/SomeDevice" -> "Notes/Screenshots/". The other subfolders were aping structure that I saw Xcode output IIRC, but simpler is better especially now that this is user-facing (See app_screenshots_link_name) [Jan 2026] || Old notes:  # See `XCLoc Screenshot Structure.md`. If we put spaces here they become %20 for some reason?

#
# Parse args
#

args: Any = None
if 1:
    parser = argparse.ArgumentParser()
    parser.add_argument('--api-key',                      required=False, default=os.getenv("GH_API_KEY"), help="The API key is used to interact with GitHub || You can also set the api key to the GH_API_KEY env variable (in the VSCode Terminal to use with VSCode) || To find the API key, see Apple Note 'MMF Localization Script Access Token'")
    parser.add_argument('--dry-run',                      required=False, action='store_true', help="Ignore the API key and don't interact with GitHub. This arg is kind of redundant [Oct 2025]")
    parser.add_argument('--only-en-screenshots',          required=False, action='store_true', help="Only take/include English screenshots in the xcloc files.")
    parser.add_argument('--no-additional-en-screenshots', required=False, action='store_true', help="By default we take/include English screenshots in addition to translated screenshots in the xcloc files [Nov 2025]")
    parser.add_argument('--recycle-screenshots',          required=False, action='store_true', help="Use localization screenshots taken during previous runs of the script. || Formerly --fresh-screenshots")
    parser.add_argument('--skip-xcloc-file-creation',     required=False, action='store_true', help="Don't create and upload fresh xcloc files. Instead only create the Translation Guide using existing, already uploaded xcloc files.")
    parser.add_argument('--only-update-locale',           required=False,                      help="Only update the xcloc files for this particular locale. Omit this to update all locales. Some stuff, like ./run syncstrings will run for all locales either way. [Dec 2025]")
    args = parser.parse_args()

    # Process dry_run arg
    
    if args.dry_run: args.api_key = ""
    
    if args.api_key:
        print(f"Working with api_key: <>\n")
    else:
        if not args.dry_run:
            print("No api key provided. Use --dry-run if this is intended.\n")
            parser.print_help()
            exit(1)
        print(f"Dry run: Running dry due to missing --api-key or --dry-run flag - not uploading/downloading from github.\n")

#
# Define main
#

def main():
    
    # Inital free line to make stuff look nicer
    print("")
    
    # Get repo name
    repo_path = os.getcwd()
    repo_name = os.path.basename(repo_path)
    
    # Validate
    assert repo_name == 'mac-mouse-fix' and repo_name != 'mac-mouse-fix-website', 'This script should be ran in the mac-mouse-fix repo'
    assert os.path.isdir(website_repo), f'To run this script, the mac-mouse-fix-website repo should be placed at {website_repo} relative to the mac-mouse-fix repo.'

    # Get temp dirs
    temp_dir: str               = "" # Initialize to str to silence stupid typechecker
    temp_dir_persistent: str    = ""
    if 1:
        # Create temp_dir
        temp_dir = tempfile.gettempdir() + '/mmf-uploadstrings'
        if os.path.isdir(temp_dir): shutil.rmtree(temp_dir, ignore_errors=True) # Why ignore_errors=True? This sometimes errors and fails to remove the dir, but only a .DS_Store file will be left. Perhaps a race condition with macOS' creation/update of the .DS_Store file [Oct 2025]
        os.makedirs(temp_dir, exist_ok=True)                                    # Why exist_ok=True? See ignore_errors=True explanation above [Oct 2025]
        
        # Create persistent temp_dir
        #   This temp_dir is intended as a cache that will persist between launches of the script to speed things up.
        temp_dir_persistent = tempfile.gettempdir() + '/mmf-uploadstrings-persistent'
        if not os.path.isdir(temp_dir_persistent): os.mkdir(temp_dir_persistent)

    # Update strings
    #   `./run syncstrings` updates the Markdown strings. The Xcode-managed strings are sync automatically by `xcodebuild -exportLocalizations` down below (I believe) [Dec 2025]
    mfutils.runclt("./run syncstrings", print_live_output=True)

    # Analyze repos
    
    @dataclass
    class RepoAnalysis: # Not sure the overhead of creating a dataclass here is worth it. Could just use a dict [Oct 2025]
        @dataclass
        class AllRepos:
            localization_progress: dict
            development_locale: str
            translation_locales: list[str]
            translation_locales_unfiltered: list[str] # We filter the translation locales for the sake of `--only-update-locale`. But then when generating the translation_guide, we end up needing the unfiltered locales. (Cause we're regenerating it from scratch, not just updating part of it.) [Dec 2025]

        @dataclass
        class SpecificRepo:
            path: str
            xcloc_dir: str
            xcstrings_paths: list[str]

        all_repos:  AllRepos
        repo:       dict[str, SpecificRepo] # Map from repo_name -> RepoAnalysis

    repo_analysis = RepoAnalysis(
        all_repos = RepoAnalysis.AllRepos(
            localization_progress={},
            development_locale="",
            translation_locales=[],
            translation_locales_unfiltered=[],
        ),
        repo={
            'mac-mouse-fix': RepoAnalysis.SpecificRepo(
                path='./',
                xcloc_dir="",
                xcstrings_paths=[]
            ),
            'mac-mouse-fix-website': RepoAnalysis.SpecificRepo(
                path=website_repo,
                xcloc_dir="",
                xcstrings_paths=[]
            ),
        }
    )

    if 1:

        # Store stuff
        #   (To validate locales between repos)
        previous_xcodeproj_path = []
        previous_repo_locales = []
        
        # Store more stuff
        #   (To get localization progress)
        xcstrings_all_repos = []

        for i, repo_name in enumerate(repo_analysis.repo):
            
            # Extract repo_info
            repo_path = repo_analysis.repo[repo_name].path

            # Find xcodeproj path
            xcodeproj_subpath = mflocales.path_to_xcodeproj[repo_name]
            xcodeproj_path = os.path.join(repo_path, xcodeproj_subpath)
            
            # Process locales
            if 1:

                # Extract locales for this repo
                development_locale, translation_locales = mflocales.find_xcode_project_locales(xcodeproj_path)

                # Log
                print(f"Extracted locales from .xcodeproject at {xcodeproj_path}: {[development_locale] + translation_locales}\n")
            
                # Validate that all repos have the same locales
                if 1:
                    repo_locales = [development_locale] + translation_locales;
                    if i > 0:
                        missing_locales = set(previous_repo_locales).difference(set(repo_locales))
                        additional_locales = set(repo_locales).difference(set(previous_repo_locales))
                        
                        def _debug_names(locales):
                            return list(map(lambda l: f'{ mflocales.locale_to_language_name(l) } ({l})', locales))
                        assert len(missing_locales) == 0, f'There are missing locales in the xcode project {xcodeproj_path} compared to the locales in {previous_xcodeproj_path}:\nmissing_locales: {_debug_names(missing_locales)}\nAdd these locales to the former xcodeproj or remove them from latter xcodeproj to resolve this error.'
                        assert len(additional_locales) == 0, f'There are additional locales in the xcode project {xcodeproj_path}, compared to the locales in {previous_xcodeproj_path}:\nadditional_locales: {_debug_names(additional_locales)}\nRemove these locales from the former xcodeproj or add them to latter xcodeproj to resolve this error.'
                    
                    previous_xcodeproj_path = xcodeproj_path
                    previous_repo_locales = repo_locales
                
                # Store the locales in repo_analysis
                if 1:
                    repo_analysis.all_repos.development_locale              = development_locale # Since we assert that the locales are the same for all repos, storing in repo_analysis.all_repos works.
                    repo_analysis.all_repos.translation_locales             = translation_locales
                    repo_analysis.all_repos.translation_locales_unfiltered  = translation_locales

            # Process .xcstrings files
            if 1:

                # Log
                print(f"Loading all .xcstring files ...\n")
                
                # Load the xcstrings
                xcstrings_paths = mflocales.find_xcstrings_files(repo_path)
                xcstrings = [json.loads(Path(p).read_text()) for p in xcstrings_paths]
                
                # Store stuff
                xcstrings_all_repos += xcstrings
                repo_analysis.repo[repo_name].xcstrings_paths = xcstrings_paths
                
                # Log
                print(f".xcstrings paths: { json.dumps(xcstrings_paths, ensure_ascii=False, indent=2) }\n")
        
        # Apply args.only_update_locale
        if args.only_update_locale:
            
            assert args.only_update_locale in repo_analysis.all_repos.translation_locales, f"--only-update-locale is set to '{ args.only_update_locale }', but that locale is not found in the repo's translation locales: { repo_analysis.all_repos.translation_locales }"
            
            repo_analysis.all_repos.translation_locales = [args.only_update_locale] # Note that `repo_analysis.all_repos.translation_locales_unfiltered` stays the same [Dec 2025]
            
            print(f"--only-update-locale is set to '{ args.only_update_locale }'. Ignoring all project locales except: { repo_analysis.all_repos.translation_locales + [repo_analysis.all_repos.development_locale] }")
        
        # Get combined localization_progress
        print(f"Getting combined localization progress...")
        repo_analysis.all_repos.localization_progress = mflocales.get_localization_progress(xcstrings_all_repos, repo_analysis.all_repos.translation_locales_unfiltered)

    # Skip xcloc creation
    if args.skip_xcloc_file_creation:
        
        # Skip straight to creating the guide
        download_urls = xcloc_download_urls(repo_analysis.all_repos.translation_locales_unfiltered, validate=(not args.dry_run))
        create_translation_guide(download_urls, repo_analysis.all_repos.translation_locales_unfiltered, repo_analysis.all_repos.localization_progress)
        return

    # Export xcloc files
    for repo_name in repo_analysis.repo:

        print(f"Begin exporting .xcloc files...")

        # Extract
        repo_path = repo_analysis.repo[repo_name].path

        # Create a folder to store .xcloc files to
        xcloc_dir = os.path.join(temp_dir, f'{repo_name}-xcloc-export')
        if os.path.isdir(xcloc_dir):
            shutil.rmtree(xcloc_dir) # Delete if theres already something there (I think this is impossible since we freshly create the temp_dir)
        os.mkdir(xcloc_dir)
        
        # Build `xcodebuild -exportLocalizations` command
        #   Notes:
        #       - We used to use the '-includeScreenshots' option here, but that doesn't seem to work, so now we have a custom XCUITest-runner that takes localization screenshots below
        #   
        #   Problem: This is slow
        #       `xcodebuild -exportLocalizations` builds the whole project from scratch, ignoring build-cache, .apps it produces are broken. Also, deletes build cache for subsequent normal builds.
        #       So when we run the XCUITest-Runner down below, we need to build the whole project from scratch again. (Tested this on Xcode 16 Beta 3)
        #
        #       Solution:
        #           Set a separate -derivedDataPath for -exportLocalizations, where it can build its broken products without deleting the cache for other builds.
        #       
        #       Notes:
        #           - Exporting localizations doesn't seem to be as slow when using the Xcode GUI. Not sure why.
        #           - I tried every xcodebuild option under the sun to speed things up, including: -sdk macosx15.0 -dry-run -skipPackageSignatureValidation -skipMacroValidation -skipPackagePluginValidation -skipPackageUpdates -onlyUsePackageVersionsFromResolvedFile -skipPackageUpdates -onlyUsePackageVersionsFromResolvedFile -disableAutomaticPackageResolution -skipUnavailableActions -destination 'name=My Mac,arch=arm64' -arch arm64 -configuration Debug -scheme "App" -project "Mouse Fix.xcodeproj"
        #               ... but none of these seemed to help.
        
        # Get paths
        project_path = mflocales.path_to_xcodeproj[repo_name]
        derived_data_path = mflocales.xcodebuild_derived_data_path(temp_dir_persistent, repo_name)

        # Assemble -exportLocalizations command
        print(f"Assembling -exportLocalizations command...")
        export_localizations_command = ""
        if 1:

            # Assemble command
            export_localizations_command = [
                f"xcrun xcodebuild -exportLocalizations",
                f"-scheme '{mflocales.xcodebuild_any_build_scheme(repo_path)}'",
                f"-derivedDataPath '{derived_data_path}'",
                f"-project '{project_path}'", # Not sure this arg is necessary / useful, we're not using it in the xcodebuild invocation inside importstrings.py [Dec 2025]
                f"-localizationPath '{xcloc_dir}'",
                *[f"-exportLanguage {l}" for l in repo_analysis.all_repos.translation_locales]
            ]
            export_localizations_command = " ".join(export_localizations_command)
        print(f"Finished assembling -exportLocalizations command.")

        # Log
        print(f"Exporting .xcloc files in {repo_name} for each translations_locale (might take a while since Xcode will build the whole project) ... \nRunning command: {export_localizations_command}\n")
        
        # Run command
        try:
            mfutils.runclt(export_localizations_command, cwd=repo_path, print_live_output=True)
        except Exception as e:
            print(f"-exportLocalizations failed. Try searching the logs for 'error' or cleaning the derived_data_path ({derived_data_path}).\n\nException:\n\n{e}")
        
        # Log
        print(f"Exported .xcloc files using command: {export_localizations_command}\n")
        
        # Store result
        repo_analysis.repo[repo_name].xcloc_dir = xcloc_dir

    # Validate the .xcstrings files in the repo against the contents of the .xcloc files that xcodebuild exported [Dec 2025]
    for repo_name in repo_analysis.repo:
        
        found_paths = repo_analysis.repo[repo_name].xcstrings_paths
        found_paths = [os.path.relpath(p, repo_analysis.repo[repo_name].path) for p in found_paths] # Make found_paths relative to repo_root so we can compare them to exported_paths [Oct 2025]

        exported_paths = []
        if 1:
            first_locale = repo_analysis.all_repos.translation_locales[0] # We arbitrarily pick the first locale one since all the languages will contain the same file paths.
            xliff = Path(repo_analysis.repo[repo_name].xcloc_dir + f'/{first_locale}.xcloc/Localized Contents/{first_locale}.xliff').read_text() 
            exported_paths = re.findall('original="(.*?)"', xliff)
            if 1: # Map IB paths to the corresponding .xcstrings paths
                exported_paths2 = [] 
                for p in exported_paths:
                    if p.endswith('.xib') or p.endswith('.storyboard'):
                        xcs = glob.glob(os.path.normpath(p + f'/../../*.lproj/{os.path.splitext(os.path.basename(p))[0]}.xcstrings'), root_dir=repo_analysis.repo[repo_name].path, recursive=True) # IB files are in Base.lproj while their .xcstrings files are in neighboring mul.lproj folder [Oct 2025]
                        assert len(xcs) == 1
                        p = xcs[0]
                    if p.endswith('.xcstrings'): pass
                    else:                        assert False
                    exported_paths2.append(p)
                exported_paths = exported_paths2

        missing_paths = set(exported_paths) - set(found_paths)
        extra_paths   = set(found_paths) - set(exported_paths)

        assert not len(missing_paths),  f"Some exported .xcstrings files weren't found: {missing_paths}. (Found by find_xcstrings_files()) (In repo {repo_name})"
        assert not len(extra_paths), f"Some found .xcstrings files weren't exported: {extra_paths}.      (Found by find_xcstrings_files()) (In repo {repo_name}).You can fix this by adding them to xcstrings_blacklist."

    # Take localization screenshots (By running our XCUI test) and copy the screenshots into the xcloc files
    if 1:

        # Get cache dir
        localization_screenshot_cache_dir = temp_dir_persistent + "/localization-screenshot-cache/"
        
        # Track caches that we've freshly created during this run of the script.
        #   This contains locale-specific subfolders of localization_screenshot_cache_dir [Dec 2025]
        fresh_cache_dirs = []

        # Delete cache
        if 0: # We no longer delete the entire cache, only the subfolders of locales that we're taking new screenshots for. Not sure why. Feels right? [Dec 2025]
            if not args.recycle_screenshots:
                shutil.rmtree(localization_screenshot_cache_dir, ignore_errors=True)
        
        # Log
        print(f"Take localization screenshots and copy them into the .xcloc files\n")
        
        for repo_name in repo_analysis.repo:
            
            # Skip
            if repo_name == 'mac-mouse-fix-website': continue
            
            # Extract
            repo_path = repo_analysis.repo[repo_name].path

            for locale in (
                repo_analysis.all_repos.translation_locales            
                if args.no_additional_en_screenshots 
                else (['en'] + repo_analysis.all_repos.translation_locales)
            ):

                # Get the screenshots_dir paths inside the xcloc files. 
                def get_xcloc_screenshots_dir(locale: str, create: bool):
                    
                    # Get xcloc_dir
                    #   ...which was created through xcodebuild in the previous step
                    xcloc_dir = os.path.join(repo_analysis.repo[repo_name].xcloc_dir, f'{locale}.xcloc') # We just know xcodebuild put em here
                    
                    # Create screenshots path inside .xcloc file
                    xcloc_screenshots_dir = os.path.join(xcloc_dir, xcloc_screenshots_subdir)
                    if create:
                        if os.path.isdir(xcloc_screenshots_dir):
                            shutil.rmtree(xcloc_screenshots_dir) # Delete if theres already something there (Not sure this is possible)
                        mfutils.runclt(['mkdir', '-p', xcloc_screenshots_dir]) # -p creates any intermediate parent folders
                    else: 
                        assert os.path.isdir(xcloc_screenshots_dir)
                    
                    xcloc_screenshots_dir = os.path.abspath(xcloc_screenshots_dir) # abspath (Not sure if necessary)
                    
                    return xcloc_screenshots_dir
                
                xcloc_screenshots_dir = get_xcloc_screenshots_dir(locale, create=True)
                
                # Write localization screenshots
                def fn():

                    f: Any = fn

                    # Get screenshot_locale
                    
                    screenshot_locale = locale
                    if 1:

                        if screenshot_locale == 'en': 
                            assert not args.no_additional_en_screenshots
                        else:
                            if args.only_en_screenshots: 
                                screenshot_locale = 'en'
                            if repo_analysis.all_repos.localization_progress[locale]['percentage'] == 0:
                                screenshot_locale = 'en'

                    # Use cache
                    cache_dir = localization_screenshot_cache_dir + '/' + screenshot_locale
                    if 1:
                        mfutils.runclt(['mkdir', '-p', cache_dir]) # -p creates any intermediate parent folders || Prevents os.listdir() from erroring I think [Dec 2025]
                        use_cache = (
                            os.listdir(cache_dir)
                            and 
                            (args.recycle_screenshots or (cache_dir in fresh_cache_dirs)) # Use screenshots from previous runs of the script if args.recycle_screenshots is set. But even if it's not set, we still use caches that were 'freshly' created during this run of the script – That's useful when screenshots are reused between different languages (E.g. due to args.only_en_screenshots) [Dec 2025]
                        )
                        if use_cache:
                            shutil.copytree(src=cache_dir, dst=xcloc_screenshots_dir, dirs_exist_ok=True) # Copy cached screenshots over to output dir
                            print(f"Copied cached screenshots from {cache_dir} to {xcloc_screenshots_dir} (Instead of running another xcuitest to take the screenshots.)\n")
                            return
                    
                    # Take fresh_screenshots
                    if 1:
                        
                        # Create did_build flag
                        if not hasattr(f, 'did_build_test_runner'): f.did_build_test_runner = False

                        # Build xcuitest runner command
                        #   Notes:
                        #   `test-without-building` Speeds things up a lot, but if we don't build at least once the user experience can be confusing for me, since we always need to remember to build the runner in Xcode first before running this script. 
                        #       Maybe it would be ideal to always build the runner but not always build the MMF app? But I don't know how we could separate the two.
                        action = 'test' if not f.did_build_test_runner else 'test-without-building'
                        test_runner_invocation = " ".join([
                            f"xcrun xcodebuild {action}",
                            f"-scheme '{xcode_screenshot_taker_build_scheme}'",
                            f"'-only-testing:{xcode_screenshot_taker_test_case}'",
                        ])
                                
                        # Set env vars for the testrunner
                        #   The `TEST_RUNNER_` prefix makes xcodebuild pass the env variable through to the test-runner.
                        envvars = {
                            'TEST_RUNNER_' + xcode_screenshot_taker_output_dir_variable : xcloc_screenshots_dir,
                            'TEST_RUNNER_' + xcode_screenshot_taker_locale_variable     : screenshot_locale # xcodebuild also has -testLanguage arg but not sure how that works [Oct 2025]
                        }
                        os.environ.update(envvars)

                        # Log
                        print(f"Invoking localization screenshot test-runner with command:\n    {test_runner_invocation}\nenvvars: {envvars}")

                        # Run the screenshot-taker test runner
                        mfutils.runclt(test_runner_invocation, cwd=repo_path, print_live_output=True, beep_on_failure=True) # beep_on_failure=True in case we step away from the computer and the test-runner randomly fails. (Which just happened – I think for the first time) [Jan 2025]

                        # Log
                        print(f"Finished running test-runner")

                        if not args.no_additional_en_screenshots and not locale == 'en':

                            # Helper fn
                            def append_locale_suffix_to_screenshot_path(p, locale): # E.g. `Cool Screenshot.jpg` -> `Cool Screenshot (2, en).jpg`
                                order = 2 if locale == 'en' else 1 # Sort English screenshots after translated ones. [Dec 2025]
                                return os.path.splitext(p)[0] + f" ({order}, {locale}).jpeg"
                            
                            # Rename all the screenshots with a locale-suffix like " (de).jpeg"
                            #   This prevents conflicts with the English screenshots (see below) and allows for alternating English/translated screenshots when sorting by name. [Dec 2025]
                            print(f"Renaming translated screenshots...");
                            if 1:
                                for p in glob.glob(xcloc_screenshots_dir + "/*.jpeg", recursive=False):
                                    assert not p.endswith(f" ({locale}).jpeg"), f"The file '{p}' already seems to have a locale-suffix."
                                    newp = append_locale_suffix_to_screenshot_path(p, locale)
                                    shutil.move(p, newp)

                            # Copy the additional English screenshots over
                            print(f"Copying over additional English screenshots...")
                            if 1:
                                for screenshotp in glob.glob("*.jpeg", root_dir=get_xcloc_screenshots_dir('en', create=False), recursive=False): 
                                    screenshotp_en    = os.path.join(get_xcloc_screenshots_dir('en', create=False),   screenshotp)
                                    screenshotp_trans = os.path.join(xcloc_screenshots_dir,                           append_locale_suffix_to_screenshot_path(screenshotp, "en"))
                                    shutil.copy(screenshotp_en, screenshotp_trans)
                                
                            # Modify `localizedStringData.plist` to include the " (en).jpeg" and " (xx).jpeg" screenshots
                            print(f"Modifying localizedStringData.plist...")
                            if 1:
                                strdata_en:          list = plistlib.loads(Path(get_xcloc_screenshots_dir('en', create=False) + "/localizedStringData.plist").read_bytes())
                                strdata_translation: list = plistlib.loads(Path(xcloc_screenshots_dir + "/localizedStringData.plist").read_bytes())

                                # Modify strdata_translation with locale-suffixes (like " (de).jpeg")
                                for i in range(len(strdata_translation)):
                                    for screenshot in strdata_translation[i]["screenshots"]:
                                        screenshot["name"] = append_locale_suffix_to_screenshot_path(screenshot["name"], locale)

                                # Modify strdata_en with " (en).jpeg" suffixes and merge it into strdata_translation
                                for i_en in range(len(strdata_en)):
                                    
                                    i_trans = [
                                        k for k in range(len(strdata_translation)) 
                                        if strdata_translation[k]["stringKey"] == strdata_en[i_en]["stringKey"]
                                    ]
                                    
                                    if not i_trans: # This can happen for the thanks.xx messages on the About Tab which are randomized [Nov 2025]
                                        strdata_translation.append(strdata_en[i_en])
                                    else:
                                        i_trans = i_trans[0]

                                        # Merge strdata_en screenshots into strdata_trans
                                        for screenshot_en in strdata_en[i_en]["screenshots"]:
                                            screenshot_en["name"] = append_locale_suffix_to_screenshot_path(screenshot_en["name"], "en")
                                            strdata_translation[i_trans]["screenshots"].append(screenshot_en)

                                        # Sort alphabetically to get the strdata_en screenshots to be alternating with corresponding strdata_trans screenshots for easy comparison inside `Xcloc Editor.app`
                                        strdata_translation[i_trans]["screenshots"].sort(key=lambda x: x["name"])

                                # Write the modified strdata_translation
                                Path(xcloc_screenshots_dir + "/localizedStringData.plist").write_bytes(plistlib.dumps(strdata_translation))

                        # Fill cache
                        shutil.rmtree(cache_dir, ignore_errors=True) # Delete all existing cached files for the screenshot_locale || Might make things easier to debug? [Dec 2025]
                        shutil.copytree(src=xcloc_screenshots_dir, dst=cache_dir, dirs_exist_ok=True)
                        fresh_cache_dirs.append(cache_dir)
                        
                        # Update did_build flag
                        f.did_build_test_runner = True
                fn()
        
    # Rename .xcloc files and put them in subfolders
    #   With one subfolder per locale
    #   (plus include extra files like `Xcloc Editor.app`
    locale_export_dirs = []
    if 1:
        xcloc_file_names = {
            'mac-mouse-fix': 'Mac Mouse Fix.xcloc',
            'mac-mouse-fix-website': 'Mac Mouse Fix Website.xcloc',
        }
        folder_name_format = "Mac Mouse Fix Translations ({})"
        
        print(f"Downloading xcloc_editor...")
        xcloc_editor_zip_path = temp_dir + '/XclocEditor.zip'
        xcloc_editor_download = requests.get(xcloc_editor_download_url)
        assert xcloc_editor_download.status_code == 200, f"xcloc_editor download failed: {xcloc_editor_download.status_code}: {xcloc_editor_download}"
        Path(xcloc_editor_zip_path).write_bytes(xcloc_editor_download.content)
        print(f"Downloaded xcloc_editor at {xcloc_editor_zip_path}")

        for l in repo_analysis.all_repos.translation_locales:
            
            language_name = mflocales.locale_to_language_name(l)
            target_folder = os.path.join(temp_dir, folder_name_format.format(language_name))
            
            for repo_name in repo_analysis.repo:
                
                current_path = os.path.join(repo_analysis.repo[repo_name].xcloc_dir, f'{l}.xcloc')
                
                target_path = os.path.join(target_folder, xcloc_file_names[repo_name])
                mfutils.runclt(['mkdir', '-p', target_folder]) # -p creates any intermediate parent folders
                mfutils.runclt(['mv', current_path, target_path])
                  

            locale_export_dirs.append(target_folder)

            # Move how_to_submit
            mfutils.runclt(['cp', how_to_submit_path, target_folder])

            # Move `Xcloc Editor.app`
            mfutils.runclt(f"unzip '{xcloc_editor_zip_path}' -d '{target_folder}'")

            # Move app_screenshots
            #   [Jan 2026] Not sure this is actually useful
            if repo_analysis.all_repos.localization_progress[l]['percentage'] > 0: # Does this condition make sense? [Jan 2026]

                # Move about_app_screenshots
                mfutils.runclt(['cp', about_app_screenshots_path, target_folder])
                
                # Create symlink to screenshots folder
                xcloc_screenshots_dir = os.path.join(target_folder, xcloc_file_names['mac-mouse-fix'], xcloc_screenshots_subdir)
                symlink_path = os.path.join(target_folder, app_screenshots_link_name)
                symlink_target_path = os.path.relpath(xcloc_screenshots_dir, target_folder)
                mfutils.runclt(f"ln -s '{symlink_target_path}' '{symlink_path}'")
        
        print(f'Moved .xcloc files into folders: {locale_export_dirs}\n')
    
    # Zip folders containing .xcloc files 
    if 1:
        
        zip_files = {}
        for l, l_dir in zip(repo_analysis.all_repos.translation_locales, locale_export_dirs):

            print(f"Zipping up .xcloc files at {l_dir} ...")

            base_dir = temp_dir
            zippable_dir_path = l_dir
            zippable_dir_name = os.path.basename(os.path.normpath(zippable_dir_path))
            zip_file_name = xcloc_zip_file_name(l)
            zip_file_path = os.path.join(base_dir, zip_file_name)
            
            if os.path.exists(zip_file_path):
                rm_result = mfutils.runclt(['rm', '-R', zip_file_path]) # We first remove any existing zip_file, because otherwise the `zip` CLT will combine the existing archive with the new data we're archiving which is weird. (If I understand the `zip` man correctly`)
                print(f'Zip file of same name already existed. Calling rm on the zip_file returned: { mfutils.clt_result_description(rm_result) }')
                
            # Get all files in directory and sort alphabetically

            # Build list of file paths for zip command
            #   We sort these alphabetically, so that they are extracted in this order, which affects the 'Date Added' sorting in Finder that Translators might be using (We expect them to view this in their Downloads folder)
            files_to_zip = [os.path.join(zippable_dir_name, f) for f in sorted(os.listdir(zippable_dir_path))]

            zip_result = mfutils.runclt(['zip', '-r', '--symlinks', zip_file_name] + files_to_zip, cwd=base_dir) # We need to set the cwd (current working directory) like this, if we use abslute path to the zip_file and xcloc file, then the `zip` clt will recreate the whole path from our system root inside the zip archive. Not sure why. || [Jan 2026] --symlinks is necessary to work with app_screenshots_link_name
            # print(f'zip clt returned: { zip_result }')
            
            with open(zip_file_path, 'rb') as zip_file:
                # Load the zip data
                zip_file_content = zip_file.read()
                # Store the data in the GitHub API format
                zip_files[l] = {
                    'name': zip_file_name,
                    'content': zip_file_content,
                }
        
        # Log
        print(f"Finished zipping up .xcloc files at {temp_dir}\n")
    

    # Upload the xcloc files
    upload_xcloc_files(zip_files, delete_all_existing = (not args.only_update_locale))
    
    # Get xcloc download urls
    download_urls = xcloc_download_urls(repo_analysis.all_repos.translation_locales_unfiltered, validate=(not args.dry_run))

    # Create the guide
    create_translation_guide(download_urls, repo_analysis.all_repos.translation_locales_unfiltered, repo_analysis.all_repos.localization_progress)

def xcloc_zip_file_name(locale):
    return f"MacMouseFixTranslations.{locale}.zip" # GitHub Releases assets seemingly can't have spaces, that's why we're using this separate format

def xcloc_download_urls(locales, validate: bool):
    
    # Get urls
    download_urls = {locale: xcloc_download_url(locale) for locale in locales}
    
    # Validate
    if validate:
        print(f"Validating .xcloc download urls...")
        for locale, download_url in download_urls.items():
            print(f"Validating .xcloc download url: {download_url}...")
            response = requests.head(download_url, allow_redirects=True)
            assert 200 <= response.status_code < 300, f"Download url '{download_url}' (which we planned to include in the translation_guide) seems invalid. Received error response for HEAD request: {mfgithub.response_description(response)}"
        print(f"Finish validating .xcloc download urls.")

    return download_urls

def xcloc_download_url(locale):
    # - Purpose: [Dec 2025] Used to get download-urls of *existing*, uploaded .xcloc files,
    #       when we skip skip, regenerating/uploading the .xcloc files for iteration speed.
    # - ! Keep in-sync with `upload_xcloc_files()` [Dec 2025]
    
    return f"https://github.com/noah-nuebling/mac-mouse-fix-localization-file-hosting/releases/download/arbitrary-tag/MacMouseFixTranslations.{locale}.zip"

def upload_xcloc_files(zip_files: dict[str, dict[str, Any]], delete_all_existing: bool) -> dict: # Returns a map from locale -> xcloc_download_url [Oct 2025]

    if not args.api_key:
        print(f"Dry run: Not uploading xcloc files to GitHub.")
        return {}
    else:
        # Log
        print(f"Uploading to GitHub ...\n")
        
        # Find GitHub Release
        response = mfgithub.github_releases_get_release_with_tag(args.api_key, 'noah-nuebling/mac-mouse-fix-localization-file-hosting', 'arbitrary-tag') # arbitrary-tag is the tag of the release we want to use, so it is not, in fact, arbitrary
        release = response.json()
        print(f"Found release { release['name'] }, received response: { mfgithub.response_description(response) }")
    

        # Delete all Assets
        #   from GitHub Release
        if delete_all_existing:
            for asset in release['assets']:
                response = mfgithub.github_releases_delete_asset(args.api_key, 'noah-nuebling/mac-mouse-fix-localization-file-hosting', asset['id'], dbgname=asset['name'])
                print(f"Deleted asset { asset['name'] }, received response: { mfgithub.response_description(response) }")
                
        
        # Upload new Assets
        #   to GitHub Release
        download_urls = {}
        for zip_file_locale, value in zip_files.items():
            
            zip_file_name    = value['name']
            zip_file_content = value['content']
            
            # Delete
            if not delete_all_existing:
                for asset in release['assets']:
                    if asset['name'] == zip_file_name:
                        response = mfgithub.github_releases_delete_asset(args.api_key, 'noah-nuebling/mac-mouse-fix-localization-file-hosting', asset['id'], dbgname=asset['name'])
                        print(f"Deleted asset { asset['name'] } before uploading new asset with same name. Received response: { mfgithub.response_description(response) }")

            # Upload
            response = mfgithub.github_releases_upload_asset(args.api_key, 'noah-nuebling/mac-mouse-fix-localization-file-hosting', release['id'], zip_file_name, zip_file_content)
            
            print(f"Uploaded asset { zip_file_name }, received response: { mfgithub.response_description(response) }")

            download_urls[zip_file_locale] = response.json()['browser_download_url']
        
        # Log
        print(f"Finshed Uploading xcloc files to GitHub. Download urls: { json.dumps(download_urls, ensure_ascii=False, indent=2) }")

        # Validate xcloc_download_url()
        for locale, url in download_urls.items():
            assert url == xcloc_download_url(locale)

        # Return
        return download_urls

def create_translation_guide(download_urls, translation_locales, localization_progess_all_repos):
    
    # Upload .xcloc files to GitHub file hosting
    
    # Define helper (Written by Claude 4.5)
    def interpolate_color(start_hex, end_hex, percentage):
        """Interpolate between two hex color strings based on percentage (0.0 to 1.0)"""

        # Convert hex to RGB
        start_r, start_g, start_b = int(start_hex[0:2], 16), int(start_hex[2:4], 16), int(start_hex[4:6], 16)
        end_r, end_g, end_b = int(end_hex[0:2], 16), int(end_hex[2:4], 16), int(end_hex[4:6], 16)

        # Interpolate each channel
        r = int(start_r + (end_r - start_r) * percentage)
        g = int(start_g + (end_g - start_g) * percentage)
        b = int(start_b + (end_b - start_b) * percentage)

        # Return as hex string
        return f"{r:02x}{g:02x}{b:02x}"

    # Create markdown
    new_translation_guide_body = None
    if 1:

        # Read template
        new_translation_guide_body = Path(translation_guide_path).read_text()
    
        # Insert table
        if 1:
            download_table = ""
            
            download_table += mfutils.mfdedent("""
                | Language | Translation Files | Completeness |
                |:--- |:---:| ---:|

            """)

            for locale in sorted(translation_locales, key=lambda l: mflocales.locale_to_language_name(l)): # Sort the locales by language name (Alphabetically)
                
                progress_dict = localization_progess_all_repos[locale]
                progress = progress_dict['percentage']
                download_name = 'Download'
                download_url = download_urls[locale]
                
                emoji_flag = mflocales.locale_to_flag_emoji(locale)
                language_name = mflocales.locale_to_language_name(locale)

                label_color = "000000"
                if progress == 0.0:
                    label_color = "aaaaaa" # Grey, subdued
                elif progress < 0.95:
                    label_color = "eeeeee" # White looks nice and sorta honors the work people have put in. || Bright orange ("ff9900") also looks nice but I don't like the negative connotation.
                else:
                    label_color = interpolate_color(
                        "aaaaaa",  # nice light gray
                        "44cc11",  # brightgreen on shields.io
                        mfutils.scale(progress, (0.95, 1.0), (0.75, 1)) # We don't like interpolating over the whole range, cause the very grayish greens look very ugly. 95%+ is green so everything doesn't become completely grayed out just cause I changed a little string. [Oct 2025]
                    )
                entry = mfutils.mfdedent(f"""
                    | {emoji_flag} {language_name} ({locale}) | [{download_name}]({download_url}) | ![Static Badge](https://img.shields.io/badge/{int(100*progress)}%25-Complete-gray?style=flat&labelColor=%23{label_color}) |
                
                """)
                download_table += entry
            
            new_translation_guide_body = new_translation_guide_body.format(download_table=download_table)
        
        # Escape markdown
        new_translation_guide_body = mfgithub.escape_for_upload(new_translation_guide_body)
    
    # Update the gh issue
    if not args.api_key:
        print(f"Dry run: Not updating the translation guide on GitHub.")
        print(f"Not uploading markdown:\n")
        print(new_translation_guide_body)
    else:
        # Find the issue
        gh_graphql_response = mfgithub.github_graphql_request_query(args.api_key, mfutils.mfdedent(f"""                                                                                      
            repository(owner: "noah-nuebling", name: "mac-mouse-fix") {{
                issue(number: {translation_guide_github_issue_id}) {{
                    id
                    url
                }}
            }}
        """))
        issue_id  = gh_graphql_response['data']['repository']['issue']['id']
        issue_url = gh_graphql_response['data']['repository']['issue']['url']

        # Mutate the document body
        gh_graphql_response = mfgithub.github_graphql_request_mutation(args.api_key, mfutils.mfdedent(f"""                    
            updateIssue(input: {{id: "{issue_id}", body: "{new_translation_guide_body}"}}) {{
                clientMutationId
            }}
        """))
        
        # Check for success
        print(f" Mutate translation guide result:\n{json.dumps(gh_graphql_response, ensure_ascii=False, indent=2)}")
        print(f" Translation guide available at: { issue_url }")
    
    
#
# Call main
#

if __name__ == "__main__":
    main()
