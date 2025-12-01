
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
import copy

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
xcloc_export_derived_data_temp_dir_subpath = 'xcode-derived-data-for-localization-export'

translation_guide_path = sys.path[0] + '/translation_guide.md'
how_to_submit_path     = sys.path[0] + "/How To Submit Your Translations.txt"

xcloc_editor_download_url    = "https://github.com/noah-nuebling/mf-xcloc-editor/releases/latest/download/XclocEditor.zip"

translation_guide_github_issue_id = "1638"

# Screenshots
xcode_screenshot_taker_output_dir_variable = "MF_LOCALIZATION_SCREENSHOT_OUTPUT_DIR"
xcode_screenshot_taker_locale_variable     = "MF_LOCALIZATION_SCREENSHOT_LOCALE"
xcode_screenshot_taker_build_scheme = "Localization Screenshot Taker"
xcode_screenshot_taker_test_case    = "Localization Screenshot Taker/LocalizationScreenshotClass/testTakeScreenshots_Localization" # [Sep 2025] See: https://stackoverflow.com/a/37971495/10601702 || [Sep 2025] We've added testTakeScreenshots_Documentation() testcase now so we need to specify the test case
xcloc_screenshots_subdir = "Notes/Screenshots/SomeTest/SomeDevice" # See `XCLoc Screenshot Structure.md`. If we put spaces here they become %20 for some reason?

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
    parser.add_argument('--fresh-screenshots',            required=False, action='store_true', help="Don't use localization screenshots taken during previous runs of the script")
    parser.add_argument('--skip-xcloc-file-creation',     required=False, action='store_true', help="Don't create and upload fresh xcloc files. Instead only create the Translation Guide using existing, already uploaded xcloc files.")
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
            translation_locales: list[str]
            development_locale: str

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
            translation_locales=[],
            development_locale=""
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

                # Get locales for this project
                development_locale, translation_locales = mflocales.find_xcode_project_locales(xcodeproj_path)
                repo_locales = [development_locale] + translation_locales
                
                # Log
                print(f"Extracted locales from .xcodeproject at {xcodeproj_path}: {repo_locales}\n")
                
                # Validate locales
                # We want all repos of the mmf project to have the same locales
                if 1:
                    if i > 0:
                            
                        missing_locales = set(previous_repo_locales).difference(set(repo_locales))
                        additional_locales = set(repo_locales).difference(set(previous_repo_locales))
                        
                        def _debug_names(locales):
                            return list(map(lambda l: f'{ mflocales.locale_to_language_name(l) } ({l})', locales))
                        assert len(missing_locales) == 0, f'There are missing locales in the xcode project {xcodeproj_path} compared to the locales in {previous_xcodeproj_path}:\nmissing_locales: {_debug_names(missing_locales)}\nAdd these locales to the former xcodeproj or remove them from latter xcodeproj to resolve this error.'
                        assert len(additional_locales) == 0, f'There are additional locales in the xcode project {xcodeproj_path}, compared to the locales in {previous_xcodeproj_path}:\nadditional_locales: {_debug_names(additional_locales)}\nRemove these locales from the former xcodeproj or add them to latter xcodeproj to resolve this error.'
                    
                    previous_xcodeproj_path = xcodeproj_path
                    previous_repo_locales = repo_locales
                
                # Aggregate locales from all projects
                repo_analysis.all_repos.translation_locales = translation_locales # Since we assert that the translation_locales are the same for all repos, this works
                repo_analysis.all_repos.development_locale  = development_locale

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
    
        # Get combined localization_progress
        repo_analysis.all_repos.localization_progress = mflocales.get_localization_progress(xcstrings_all_repos, repo_analysis.all_repos.translation_locales)
    
    # Skip xcloc creation
    if args.skip_xcloc_file_creation:
        
        # Skip straight to creating the guide
        download_urls = fallback_xcloc_download_urls(repo_analysis.all_repos.translation_locales) #   Note that the repo_analysis is based on the local files not the uploaded files we're linking to – so they are out-of-sync.
        create_translation_guide(download_urls, repo_analysis.all_repos.translation_locales, repo_analysis.all_repos.localization_progress)
        return

    # Export xcloc files
    for repo_name in repo_analysis.repo:

        # Extract
        repo_path = repo_analysis.repo[repo_name].path

        # Create a folder to store .xcloc files to
        xcloc_dir = os.path.join(temp_dir, f'{repo_name}-xcloc-export')
        if os.path.isdir(xcloc_dir):
            shutil.rmtree(xcloc_dir) # Delete if theres already something there (I think this is impossible since we freshly create the temp_dir)
        os.mkdir(xcloc_dir)
        
        # Build -exportLocalizations command
        # Notes:
        #   - This python list comprehension syntax is confusing. I feel like the `l in` and `arg in` sections should be swapped
        #   - We used to use the '-includeScreenshots' option here, but that doesn't seem to work, so now we have a custom XCUITest-runner that takes localization screenshots below
        #   
        #   Problem: This is slow
        #       `xcodebuild -exportLocalizations` builds the whole project from scratch, ignoring build-cache, .apps it produces are broken. Also, deletes build cache for subsequent normal builds.
        #       So when we run the XCUITest-Runner down below, we need to build the whole project from scratch again. (Tested this on Xcode 16 Beta 3)
        #
        #   Solution:
        #       Set a separate -derivedDataPath for -exportLocalizations, where it can build its broken products without deleting the cache for other builds.
        #       
        #   Notes:
        #       - Exporting localizations doesn't seem to be as slow when using the Xcode GUI. Not sure why.
        #       - I tried every xcodebuild option under the sun to speed things up, including: -sdk macosx15.0 -dry-run -skipPackageSignatureValidation -skipMacroValidation -skipPackagePluginValidation -skipPackageUpdates -onlyUsePackageVersionsFromResolvedFile -skipPackageUpdates -onlyUsePackageVersionsFromResolvedFile -disableAutomaticPackageResolution -skipUnavailableActions -destination 'name=My Mac,arch=arm64' -arch arm64 -configuration Debug -scheme "App" -project "Mouse Fix.xcodeproj"
        #           ... but none of these seemed to help.
        
        # Get paths
        project_path = mflocales.path_to_xcodeproj[repo_name]
        derived_data_path = os.path.join(temp_dir_persistent, xcloc_export_derived_data_temp_dir_subpath, repo_name, os.path.splitext(project_path)[0]) # Splitext removes the .xcodeproj

        export_localizations_command = ""
        if 1:

            # Get any scheme
            #   Note: I don't think the scheme matters, since xcodebuild -exportLocalizations builds all targets anyways. But xcodebuild still demands a -scheme when using -derivedDataPath.
            #           So we're just using the first scheme we find for the project.
            build_schemes = mfutils.find_xcode_project_build_schemes(repo_path, project_path)
            any_build_scheme = build_schemes[0]
            

            # Assemble command
            export_localizations_command = [
                f"xcrun xcodebuild -exportLocalizations",
                f"-scheme '{any_build_scheme}'",
                f"-derivedDataPath '{derived_data_path}'",
                f"-project '{project_path}'",
                f"-localizationPath '{xcloc_dir}'",
                *[f"-exportLanguage {l}" for l in repo_analysis.all_repos.translation_locales]
            ]
            export_localizations_command = " ".join(export_localizations_command)

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

    # Validate the xcstrings files we found against the contents of the exported xcloc files
    for repo_name in repo_analysis.repo:
        
        found_paths = repo_analysis.repo[repo_name].xcstrings_paths
        found_paths = [os.path.relpath(p, repo_analysis.repo[repo_name].path) for p in found_paths] # Make found_paths relative to repo_root so we can compare them to exported_paths [Oct 2025]

        exported_paths = []
        if 1:
            xliff = Path(repo_analysis.repo[repo_name].xcloc_dir + '/de.xcloc/Localized Contents/de.xliff').read_text() # We arbitrarily pick the German one since all the languages will contain the same file paths.
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
        
        # Delete cache
        if args.fresh_screenshots: # Don't use screenshots from previous runs of the script. The cache will still be used during this run of the script when screenshots are reused between different languages (E.g. due to args.only_en_screenshots) [Oct 2025]
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
                if args.no_additional_en_screenshots else 
                (['en'] + repo_analysis.all_repos.translation_locales)
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
                        mfutils.runclt(['mkdir', '-p', cache_dir]) # -p creates any intermediate parent folders
                        if os.listdir(cache_dir):
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
                        mfutils.runclt(test_runner_invocation, cwd=repo_path, print_live_output=True)        

                        # Log
                        print(f"Finished running test-runner")

                        # Also copy the additional English screenshots over
                        if not args.no_additional_en_screenshots and not locale == 'en':
                            
                            def get_name_for_additional_en_screenshot(p):
                                return os.path.splitext(os.path.basename(p))[0] + " (en).jpeg"

                            for screenshotp in glob.glob("*.jpeg", root_dir=get_xcloc_screenshots_dir('en', create=False), recursive=False): 
                                screenshotp_en    = os.path.join(get_xcloc_screenshots_dir('en', create=False),   screenshotp)
                                screenshotp_trans = os.path.join(xcloc_screenshots_dir, get_name_for_additional_en_screenshot(screenshotp))
                                shutil.copy(screenshotp_en, screenshotp_trans)
                            
                            # Modify `localizedStringData.plist` to include the " (en).jpeg" screenshots
                            strdata_en:    list = plistlib.loads(Path(get_xcloc_screenshots_dir('en', create=False) + "/localizedStringData.plist").read_bytes())
                            strdata_trans: list = plistlib.loads(Path(xcloc_screenshots_dir + "/localizedStringData.plist").read_bytes())
                            
                            for i_en in range(len(strdata_en)):
                                
                                i_trans = [
                                    k for k in range(len(strdata_trans)) 
                                    if strdata_trans[k]["stringKey"] == strdata_en[i_en]["stringKey"]
                                ]
                                
                                if not i_trans: # This can happen for the thanks.xx messages on the About Tab which are randomized [Nov 2025]
                                    strdata_trans.append(strdata_en[i_en])
                                else:
                                    i_trans = i_trans[0]

                                    # Merge strdata_en screenshots into strdata_trans
                                    for screenshot_en in strdata_en[i_en]["screenshots"]:
                                        screenshot_en["name"] = get_name_for_additional_en_screenshot(screenshot_en["name"])
                                        strdata_trans[i_trans]["screenshots"].append(screenshot_en)

                                    # Sort to get the strdata_en screenshots to be alternating with corresponding strdata_trans ones for easy comparison in `Xcloc Editor.app`
                                    strdata_trans[i_trans]["screenshots"].sort(key=lambda x: x["name"], reverse=True)

                            Path(xcloc_screenshots_dir + "/localizedStringData.plist").write_bytes(plistlib.dumps(strdata_trans))

                        # Fill cache
                        shutil.copytree(src=xcloc_screenshots_dir, dst=cache_dir, dirs_exist_ok=True)
                        
                        # Update did_build flag
                        f.did_build_test_runner = True
                fn()
        
    # Rename .xcloc files and put them in subfolders
    #   With one subfolder per locale
    #   (plus include extra files like `Xcloc Editor.app`
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

        locale_export_dirs = []
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

        
        print(f'Moved .xcloc files into folders: {locale_export_dirs}\n')
    
    # Zip folders containing .xcloc files 
    if 1:
        
        zip_file_format = "MacMouseFixTranslations.{}.zip" # GitHub Releases assets seemingly can't have spaces, that's why we're using this separate format
        
        zip_files = {}
        for l, l_dir in zip(repo_analysis.all_repos.translation_locales, locale_export_dirs):

            print(f"Zipping up .xcloc files at {l_dir} ...")

            base_dir = temp_dir
            zippable_dir_path = l_dir
            zippable_dir_name = os.path.basename(os.path.normpath(zippable_dir_path))
            zip_file_name = zip_file_format.format(l)
            zip_file_path = os.path.join(base_dir, zip_file_name)
            
            if os.path.exists(zip_file_path):
                rm_result = mfutils.runclt(['rm', '-R', zip_file_path]) # We first remove any existing zip_file, because otherwise the `zip` CLT will combine the existing archive with the new data we're archiving which is weird. (If I understand the `zip` man correctly`)
                print(f'Zip file of same name already existed. Calling rm on the zip_file returned: { mfutils.clt_result_description(rm_result) }')
                
            zip_result = mfutils.runclt(['zip', '-r', zip_file_name, zippable_dir_name], cwd=base_dir) # We need to set the cwd (current working directory) like this, if we use abslute path to the zip_file and xcloc file, then the `zip` clt will recreate the whole path from our system root inside the zip archive. Not sure why.
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
    

    # Upload the files and create the guide
    download_urls = upload_xcloc_files(zip_files) or fallback_xcloc_download_urls(repo_analysis.all_repos.translation_locales)
    create_translation_guide(download_urls, repo_analysis.all_repos.translation_locales, repo_analysis.all_repos.localization_progress)


def fallback_xcloc_download_urls(translation_locales):
    # In case we skip running `upload_xcloc_files()` we can use this to get fallback values [Oct 2025]
    download_urls = {}
    for translation_locale in translation_locales:
        download_urls[translation_locale] = f"https://github.com/noah-nuebling/mac-mouse-fix-localization-file-hosting/releases/download/arbitrary-tag/MacMouseFixTranslations.{translation_locale}.zip"
    return download_urls

def upload_xcloc_files(zip_files) -> dict: # Returns a map from locale -> xcloc_download_url [Oct 2025]

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
        for asset in release['assets']:
            response = mfgithub.github_releases_delete_asset(args.api_key, 'noah-nuebling/mac-mouse-fix-localization-file-hosting', asset['id'])
            print(f"Deleted asset { asset['name'] }, received response: { mfgithub.response_description(response) }")
        
        # Upload new Assets
        #   to GitHub Release
        
        download_urls = {}
        for zip_file_locale, value in zip_files.items():
            
            zip_file_name = value['name']
            zip_file_content = value['content']
        
            response = mfgithub.github_releases_upload_asset(args.api_key, 'noah-nuebling/mac-mouse-fix-localization-file-hosting', release['id'], zip_file_name, zip_file_content)        
            download_urls[zip_file_locale] = response.json()['browser_download_url']
            
            print(f"Uploaded asset { zip_file_name }, received response: { mfgithub.response_description(response) }")
        
        # Log
        print(f"Finshed Uploading xcloc files to GitHub. Download urls: { json.dumps(download_urls, ensure_ascii=False, indent=2) }")

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
