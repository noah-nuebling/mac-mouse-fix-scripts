
"""

This scripts creates .xcloc files for the MMF project and publishes them on GitHub.

"""

#
# Imports
# 

import tempfile
import os
import json
import shutil
import glob
from collections import namedtuple
from pprint import pprint
import argparse

#
# Import functions from ../Shared folder
#

import mfutils
import mflocales
import mfgithub

# Print sys.path to debug
#   - This needs to contain the ../Shared folder in oder for the import and VSCode completions to work properly
#   - We add the ../Shared folder to the path through the .env file at the project root.

# print("Current sys.path:")
# for p in sys.path:
#     print(p)

# Note about vvv: Since we add the ../Shared folder to the python env inside the .env file (at the project root), we don't need the code below vvv any more. Using the .env file has the benefit that VSCode completions work with it.

# code_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
# if code_dir not in sys.path:
#     sys.path.append(code_dir)
# from Shared import shared

#    
# Constants
#

website_repo = './../mac-mouse-fix-website'
xcloc_export_derived_data_temp_dir_subpath = 'xcode-derived-data-for-localization-export'

# Screenshots
xcode_screenshot_taker_output_dir_variable = "MF_LOCALIZATION_SCREENSHOT_OUTPUT_DIR"
xcode_screenshot_taker_build_scheme = "Localization Screenshot Taker"
xcloc_screenshots_subdir = "Notes/Screenshots/SomeTest/SomeDevice" # See `XCLoc Screenshot Structure.md`. If we put spaces here they become %20 for some reason?

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
    
    # Parse args
    parser = argparse.ArgumentParser()
    parser.add_argument('--api_key', required=False, default=os.getenv("GH_API_KEY"), help="The API key is used to interact with GitHub || You can also set the api key to the GH_API_KEY env variable (in the VSCode Terminal to use with VSCode) || To find the API key, see Apple Note 'MMF Localization Script Access Token'")
    parser.add_argument('--dry_run', required=False, action='store_true', help="Prevent uploads/mutations on github. (You can still pass an API key to let the script *download* stuff from github.)")
    parser.add_argument('--dev_language_screenshots', required=False, action='store_true', help="Only take screenshots in the development language instead of taking separate screenshots for every translation of the app.")
    args = parser.parse_args()
    
    dev_language_screenshots = args.dev_language_screenshots
    is_dry_run = args.dry_run    
    no_api_key = args.api_key == None or len(args.api_key) == 0
    
    # Parse args pt 2
    if is_dry_run:
        print(f"Dry run: Running dry - not uploading to github.\n")
        
        if not no_api_key:
            print(f"Dry run: Working with api_key: <>. Will use it to download but not upload/mutate from github.\n")
        else:
            print("Dry run: No api key provided. Will not interact with github at all.\n")
        
    else:        
        if not no_api_key:
            print(f"Working with api_key: <>\n")
        else:
            print("No api key provided Use --dry_run if this is intended.\n")
            parser.print_help()
            exit(1)
    
    # Store stuff
    #   (To validate locales between repos)
    
    previous_xcodeproj_path = None
    previous_repo_locales = None
    
    # Store more stuff
    #   (To get localization progress)
    xcstring_objects_all_repos = []
    localization_progess_all_repos = None
    translation_locales_all_repos = None
    
    # Create temp_dir
    temp_dir = tempfile.gettempdir() + '/mmf-uploadstrings'
    if os.path.isdir(temp_dir):
        shutil.rmtree(temp_dir)
    os.mkdir(temp_dir)
    
    # Create persistent temp_dir
    #   This temp_dir is intended as a cache that will persist between launches of the script to speed things up.
    temp_dir_persistent = tempfile.gettempdir() + '/mmf-uploadstrings-persistent'
    if not os.path.isdir(temp_dir_persistent):
        os.mkdir(temp_dir_persistent)
    
    # Iterate repos
    
    repo_data = {
        'mac-mouse-fix-website': {
            'path': website_repo,
            'xcloc_dir': None,
        },
        'mac-mouse-fix': {
            'path': './',
            'xcloc_dir': None, # This will hold the result of the loop iteration
        },
    }
    
    for i, (repo_name, repo_info) in enumerate(repo_data.items()):
        
        # Extract
        repo_path = repo_info['path']
        
        # Find xcodeproj path
        xcodeproj_subpath = mflocales.path_to_xcodeproj[repo_name]
        xcodeproj_path = os.path.join(repo_path, xcodeproj_subpath)
        
        # Get locales for this project
        development_locale, translation_locales = mflocales.find_xcode_project_locales(xcodeproj_path)
        repo_locales = [development_locale] + translation_locales
        
        # Log
        print(f"Extracted locales from .xcodeproject at {xcodeproj_path}: {repo_locales}\n")
        
        # Validate locales
        # We want all repos of the mmf project to have the same locales
        
        if i > 0:
                
            missing_locales = set(previous_repo_locales).difference(set(repo_locales))
            additional_locales = set(repo_locales).difference(set(previous_repo_locales))
            
            def _debug_names(locales):
                return list(map(lambda l: f'{ mflocales.language_tag_to_language_name(l) } ({l})', locales))
            assert len(missing_locales) == 0, f'There are missing locales in the xcode project {xcodeproj_path} compared to the locales in {previous_xcodeproj_path}:\nmissing_locales: {_debug_names(missing_locales)}\nAdd these locales to the former xcodeproj or remove them from latter xcodeproj to resolve this error.'
            assert len(additional_locales) == 0, f'There are additional locales in the xcode project {xcodeproj_path}, compared to the locales in {previous_xcodeproj_path}:\nadditional_locales: {_debug_names(additional_locales)}\nRemove these locales from the former xcodeproj or add them to latter xcodeproj to resolve this error.'
        
        previous_xcodeproj_path = xcodeproj_path
        previous_repo_locales = repo_locales
        
        # Log
        print(f"Loading all .xcstring files ...\n")
        
        # Load all .xcstrings files
        xcstring_objects = []
        glob_pattern = './' + os.path.normpath(f'{repo_path}/**/*.xcstrings') # Not sure normpath is necessary
        xcstring_filenames = glob.glob(glob_pattern, recursive=True)
        for f in xcstring_filenames:
            with open(f, 'r') as content:
                xcstring_objects.append(json.load(content))
        
        # Store stuff for localization_progress
        xcstring_objects_all_repos += xcstring_objects
        translation_locales_all_repos = translation_locales # Since we assert that the translation_locales are the same for all repos, this works
        
        # Log
        print(f".xcstring file paths: { json.dumps(xcstring_filenames, indent=2) }\n")
        
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
        
        # Get any scheme
        #   Note: I don't think the scheme matters, since xcodebuild -exportLocalizations builds all targets anyways. But xcodebuild still demands a -scheme when using -derivedDataPath.
        #           So we're just using the first scheme we find for the project.
        
        project_path = mflocales.path_to_xcodeproj[repo_name]
        build_schemes = mfutils.find_xcode_project_build_schemes(repo_path, project_path)
        any_build_scheme = build_schemes[0]
        
        # Get derived data path
        derived_data_path = os.path.join(temp_dir_persistent, xcloc_export_derived_data_temp_dir_subpath, repo_name, os.path.splitext(project_path)[0]) # Splitext removes the .xcodeproj
        
        # Assemble command
        export_localizations_command = [f"xcrun xcodebuild -exportLocalizations",
                                        f"-scheme '{any_build_scheme}'",
                                        f"-derivedDataPath '{derived_data_path}'",
                                        f"-project '{project_path}'",
                                        f"-localizationPath '{xcloc_dir}'"]
    
        for l in translation_locales:
              export_localizations_command.append(f"-exportLanguage {l}")
        
        export_localizations_command = " ".join(export_localizations_command)
        
        # Log
        print(f"Exporting .xcloc files in {repo_name} for each translations_locale (might take a while since Xcode will build the whole project) ... \nRunning command: {export_localizations_command}\n")
        
        # Run command
        mfutils.runclt(export_localizations_command, cwd=repo_path, print_live_output=True)
        
        # Log
        print(f"Exported .xcloc files using command: {export_localizations_command}\n")
        
        # Store result
        repo_data[repo_name]['xcloc_dir'] = xcloc_dir
    
    # Get combined localization_progress
    localization_progess_all_repos = mflocales.get_localization_progress(xcstring_objects_all_repos, translation_locales_all_repos)
    
    # Log
    print(f"Taking localization screenshots and storing them into the .xcloc file for every locale...\n")
    
    # Run the screenshot-taker XCUI tests
    for repo_name, repo_info in repo_data.items():
        
        # Skip
        if repo_name == 'mac-mouse-fix-website': continue
        
        # Extract
        repo_path = repo_info['path']
        repo_xcloc_dir = repo_info['xcloc_dir']
        
        # Define helper function
        def write_localization_screenshots(repo_path, locale, dev_language_screenshots, output_dir):
            
            # Get shorthand for this function
            f = write_localization_screenshots
            
            # Get or initialize the global variable (function attribute)
            if not hasattr(f, 'output_dir_cache'):
                f.output_dir_cache = dict()
            output_dir_cache = f.output_dir_cache
            
            # Preprocess locale
            screenshot_locale = development_locale if dev_language_screenshots else locale
            
            # Preprocess output_dir 
            #   (Not sure if necessary)
            output_dir = os.path.abspath(output_dir)
            
            # Get cached screenshots
            #       for the screenshot locale
            cached_output_dir = output_dir_cache.get(screenshot_locale, None)
            
            if cached_output_dir != None:
                
                # Copy cached screenshots over to output dir
                shutil.copytree(src=cached_output_dir, dst=output_dir, dirs_exist_ok=True)
                
                # Log
                print(f"Copied cached screenshots from {cached_output_dir} to {output_dir} (Instead of running another xcuitest to take the screenshots.)\n")
                
                # Return
                return
            
            else: # (Taking fresh screenshots )
                
                # Get global flag
                if not hasattr(f, 'did_build_for_testing'):
                    f.did_build_for_testing = False
                did_build_for_testing = f.did_build_for_testing
                
                # Build xcuitest runner command
                #   Notes:
                #   `test-without-building` Speeds things up a lot, but if we don't build at least once the user experience can be confusing for me, since we always need to remember to build the runner in Xcode first before running this script. 
                #       Maybe it would be ideal to always build the runner but not always build the MMF app? But I don't know how we could separate the two.
                action = 'test' if not did_build_for_testing else 'test-without-building'
                test_runner_invocation = f"xcrun xcodebuild {action} -scheme '{xcode_screenshot_taker_build_scheme}' -testLanguage {screenshot_locale}"
                        
                # Log
                print(f"Invoking localization screenshot test-runner with command:\n    {test_runner_invocation}\n")
                        
                # Set output path for test runner
                #   The `TEST_RUNNER_` prefix makes xcodebuild pass the env variable through to the test-runner.
                os.environ['TEST_RUNNER_' + xcode_screenshot_taker_output_dir_variable] = output_dir
                    
                # Run the screenshot-taker test runner
                mfutils.runclt(test_runner_invocation, cwd=repo_path, print_live_output=True)
                
                # Fill cache
                output_dir_cache[screenshot_locale] = output_dir
                
                # Update global flag
                f.did_build_for_testing = True
        
        # Iter locales
        for locale in translation_locales:
            
            # Get xcloc_dir
            #   ...which was created through xcodebuild in the previous step
            xcloc_dir = os.path.join(repo_xcloc_dir, f'{locale}.xcloc') # We just know xcodebuild put em here
            
            # Create screenshots path inside .xcloc file
            xcloc_screenshots_dir = os.path.join(xcloc_dir, xcloc_screenshots_subdir)
            if os.path.isdir(xcloc_screenshots_dir):
                shutil.rmtree(xcloc_screenshots_dir) # Delete if theres already something there (Not sure this is possible)
            mfutils.runclt(['mkdir', '-p', xcloc_screenshots_dir]) # -p creates any intermediate parent folders
            
            # Put the screenshots
            #   Using our local helper function
            write_localization_screenshots(repo_path, locale, dev_language_screenshots, xcloc_screenshots_dir)
            
    # Rename .xcloc files and put them in subfolders
    #   With one subfolder per locale
    
    xcloc_file_names = {
        'mac-mouse-fix': 'Mac Mouse Fix.xcloc',
        'mac-mouse-fix-website': 'Mac Mouse Fix Website.xcloc',
    }
    folder_name_format = "Mac Mouse Fix Translations ({})"
    
    locale_export_dirs = []
    for l in translation_locales:
        
        language_name = mflocales.language_tag_to_language_name(l)
        target_folder = os.path.join(temp_dir, folder_name_format.format(language_name))
        
        for repo_name, repo_info in repo_data.items():
            
            current_path = os.path.join(repo_info['xcloc_dir'], f'{l}.xcloc')
            
            target_path = os.path.join(target_folder, xcloc_file_names[repo_name])
            mfutils.runclt(['mkdir', '-p', target_folder]) # -p creates any intermediate parent folders
            mfutils.runclt(['mv', current_path, target_path])
            

        locale_export_dirs.append(target_folder)
    
    # Log
    print(f'Moved .xcloc files into folders: {locale_export_dirs}\n')
    
    # Zipping up folders containing .xcloc files 
    print(f"Zipping up .xcloc files ...\n")
    
    zip_file_format = "MacMouseFixTranslations.{}.zip" # GitHub Releases assets seemingly can't have spaces, that's why we're using this separate format
    
    zip_files = {}
    for l, l_dir in zip(translation_locales, locale_export_dirs):
        
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
            
    print(f"Finished zipping up .xcloc files at {temp_dir}\n")
    

    if no_api_key:
        print(f"No API key provided, can't interact with GitHub. Stopping the script here")
    else:
        do_github_stuff(args.api_key, is_dry_run, zip_files, translation_locales, localization_progess_all_repos)


    
    

#
# Split up main
#

def do_github_stuff(gh_api_key, is_dry_run, zip_files, translation_locales, localization_progess_all_repos):
    
    print(f"Uploading to GitHub ...\n")
    
    # Find GitHub Release
    response = mfgithub.github_releases_get_release_with_tag(gh_api_key, 'noah-nuebling/mac-mouse-fix-localization-file-hosting', 'arbitrary-tag') # arbitrary-tag is the tag of the release we want to use, so it is not, in fact, arbitrary
    release = response.json()
    print(f"Found release { release['name'] }, received response: { mfgithub.response_description(response) }")
    
    # Delete all Assets 
    #   from GitHub Release
    for asset in release['assets']:
        response = mfgithub.github_releases_delete_asset(gh_api_key, 'noah-nuebling/mac-mouse-fix-localization-file-hosting', asset['id'], is_dry_run)
        print(f"Deleted asset { asset['name'] }, received response: { mfgithub.response_description(response) }")
    
    # Upload new Assets
    #   to GitHub Release
    
    download_urls = {}
    for zip_file_locale, value in zip_files.items():
        
        zip_file_name = value['name']
        zip_file_content = value['content']
        
        response = mfgithub.github_releases_upload_asset(gh_api_key, 'noah-nuebling/mac-mouse-fix-localization-file-hosting', release['id'], zip_file_name, zip_file_content, is_dry_run)        
        download_urls[zip_file_locale] = response.json()['browser_download_url']
        
        print(f"Uploaded asset { zip_file_name }, received response: { mfgithub.response_description(response) }")
        
    print(f"Finshed Uploading to GitHub. Download urls: { json.dumps(download_urls, indent=2) }")
    
    # Create markdown
    new_discussion_body = """\
<!-- AUTOGENERATED - DO NOT EDIT --> 
    
> [!WARNING]
> **This is a work in progress - do not follow the instructions in this document**
    
Mac Mouse Fix can now be translated into different languages! 🌍 

And you can help! 🧠

## How to Contribute

To contribute translations to Mac Mouse Fix, follow these steps:

1. **Download Translation Files**
    <details> 
      <summary><ins>Download</ins> the translation files for the language you want to translate Mac Mouse Fix into.</summary>
    <br>

{download_table}

    *If your language is missing from this list, please let me know in a comment below.*
    
    </details>
    
    <!--
    
    #### Further Infooo
    
    The download will contain two files: "Mac Mouse Fix.xcloc" and "Mac Mouse Fix Website.xcloc". Edit these files to translate Mac Mouse Fix.
    
    -->
    
2. **Download Xcode**
    
    [Download](https://apps.apple.com/de/app/xcode/id497799835?l=en-GB&mt=12) Xcode to be able to edit the translation files.
    <!--
    > [!NOTE] 
    > **Do I need to know programming?**
    > No. Xcode is Apples Software for professional Software Development. But don't worry, it has a nice user interface for editing translation files, and you don't have to know anything about programming or software development.
    --> 
    
3. **Edit the translation files files using Xcode**
    
    The Translation Files you downloaded have the file extension `.xcloc`. 
    
    Open these files in Xcode and then fill in your translations until the 'State' of every Translation shows a green checkmark.
    
    <br>
    
    <img width="759" alt="Screenshot 2024-06-27 at 10 38 27" src="https://github.com/noah-nuebling/mac-mouse-fix/assets/40808343/fb1067e9-18f4-4579-b147-cfea7f38caeb">
    
    <br><br>
    
    <details> 
      <summary><ins>Click here</ins> for a more <b>detailed explanation</b> about how to edit your .xcloc files in Xcode.</summary>
    
    1. **Open your Translation Files**
    
        After downloading Xcode, double click one of the .xcloc files you downloaded to begin editing it.
    
        <img width="607" alt="Screenshot 2024-06-27 at 09 24 39" src="https://github.com/noah-nuebling/mac-mouse-fix/assets/40808343/a70addcf-466f-4a92-8096-eee717ecc9fe">
    
    2. **Navigate the UI**
    
        After opeing your .xcloc file, browse different sections in the **Navigator** on the left, then translate the text in the **Editor** on the right.
    
        <img width="1283" alt="Screenshot 2024-06-27 at 09 25 44" src="https://github.com/noah-nuebling/mac-mouse-fix/assets/40808343/62eb0db2-02a0-46dd-bc59-37ad892915ee">
    
    3. **Find translations that need work**
    
        Click the 'State' column on the very right to sort the translatable text by its 'State'. Text with a Green Checkmark as it's state is probably ok, Text with other state may need to be reviewd or filled in.
    
        <img width="1341" alt="Screenshot 2024-06-27 at 09 30 10" src="https://github.com/noah-nuebling/mac-mouse-fix/assets/40808343/daea7f0d-d823-4c75-9f06-5a81c56f836e">
    
    4. **Edit Translations**
        
        Click a cell in the middle column to edit the translation.
    
        After you edit a translation, the 'State' will turn into a green checkmark, signalling that that you have reviewed and approved the translation.
        
        <img width="1103" alt="Screenshot 2024-06-27 at 10 47 04" src="https://github.com/noah-nuebling/mac-mouse-fix/assets/40808343/56b1f109-6319-4ba8-991d-8fced7b35f9b">
    
    
    </details>
    
4. **Submit your translations!**
    
    Once all your translations have a green checkmark, you can send the Translation files back to me and I will add them to Mac Mouse Fix!
    
    To send your Translation Files:
    - **Option 1**: Add a comment below this post. When creating the comment, drag-and-drop your translation files into the comment text field to send them along with your comment.
    - **Option 2**: Send me an email and add the translation files as an attachment.

## Credits

If your translations are accepted into the project you will receive a mention in the next Update Notes and your name will be added as a Localizer in the Acknowledgments!

<!--
(if your contribution was more than 10 strings or sth?)    
-->

## Conclusion

And that's it. If you have any questions, please write a comment below.

Thank you so much for your help in bringing Mac Mouse Fix to people around the world!


"""

    #
    # More minimalist
    # 

    new_discussion_body = new_discussion_body = """\
    
<!-- AUTOGENERATED - DO NOT EDIT --> 
    
> [!WARNING]
> **This is a work in progress - do not follow the instructions in this document**
    
Mac Mouse Fix can now be translated into different languages! 🌍 

And you can help! 🧠

## How to Contribute

To contribute translations to Mac Mouse Fix, follow these steps:

### 1. **Download Translation Files**
<details> 
    <summary><ins>Download</ins> the translation files for the language you want to translate Mac Mouse Fix into.</summary>
<br>

{download_table}

*If your language is missing from this list, please let me know in a comment below.*

</details>

<!--

#### Further Infooo

The download will contain two files: "Mac Mouse Fix.xcloc" and "Mac Mouse Fix Website.xcloc". Edit these files to translate Mac Mouse Fix.

-->

### 2. **Download Xcode**

[Download](https://apps.apple.com/de/app/xcode/id497799835?l=en-GB&mt=12) Xcode to be able to edit the translation files.
<!--
> [!NOTE] 
> **Do I need to know programming?**
> No. Xcode is Apples Software for professional Software Development. But don't worry, it has a nice user interface for editing translation files, and you don't have to know anything about programming or software development.
--> 

### 3. **Edit the translation files files using Xcode**

The Translation Files you downloaded have the file extension `.xcloc`. 

Open these files in Xcode and then fill in your translations until the 'State' of every Translation shows a green checkmark.

<br>

<img width="759" alt="Screenshot 2024-06-27 at 10 38 27" src="https://github.com/noah-nuebling/mac-mouse-fix/assets/40808343/fb1067e9-18f4-4579-b147-cfea7f38caeb">

<br><br>

<details> 
    <summary><ins>Click here</ins> for a more <b>detailed explanation</b> about how to edit your .xcloc files in Xcode.</summary>

1. **Open your Translation Files**

    After downloading Xcode, double click one of the .xcloc files you downloaded to begin editing it.

    <img width="607" alt="Screenshot 2024-06-27 at 09 24 39" src="https://github.com/noah-nuebling/mac-mouse-fix/assets/40808343/a70addcf-466f-4a92-8096-eee717ecc9fe">

2. **Navigate the UI**

    After opeing your .xcloc file, browse different sections in the **Navigator** on the left, then translate the text in the **Editor** on the right.

    <img width="1283" alt="Screenshot 2024-06-27 at 09 25 44" src="https://github.com/noah-nuebling/mac-mouse-fix/assets/40808343/62eb0db2-02a0-46dd-bc59-37ad892915ee">

3. **Find translations that need work**

    Click the 'State' column on the very right to sort the translatable text by its 'State'. Text with a Green Checkmark as it's state is probably ok, Text with other state may need to be reviewd or filled in.

    <img width="1341" alt="Screenshot 2024-06-27 at 09 30 10" src="https://github.com/noah-nuebling/mac-mouse-fix/assets/40808343/daea7f0d-d823-4c75-9f06-5a81c56f836e">

4. **Edit Translations**
    
    Click a cell in the middle column to edit the translation.

    After you edit a translation, the 'State' will turn into a green checkmark, signalling that the translation has been reviewed and approved.
    
    <img width="1103" alt="Screenshot 2024-06-27 at 10 47 04" src="https://github.com/noah-nuebling/mac-mouse-fix/assets/40808343/56b1f109-6319-4ba8-991d-8fced7b35f9b">


</details>

### 4. **Submit your translations!**

Once all your translations have a green checkmark, you can send the Translation files back to me and I will add them to Mac Mouse Fix!

To send your Translation Files:
- **Option 1**: Add a comment below this post. When editing the comment, drag-and-drop your translation files into the comment text field to send them along with your comment.
- **Option 2**: Send me an email and add the translation files as an attachment.

## Credits

If your translations are accepted into the project you will receive a mention in the next Update Notes and your name will be added as a Localizer in the Acknowledgments!

<!--
(if your contribution was more than 10 strings or sth?)    
-->

## Conclusion

And that's it. If you have any questions, please write a comment below.

Thank you so much for your help in bringing Mac Mouse Fix to people around the world!


"""
    
    # Fill in data into markdown table
    
    download_table = ""
    
    download_table += """\
| Language | Translation Files | Completeness |
|:--- |:---:| ---:|
"""

    for locale in sorted(translation_locales, key=lambda l: mflocales.language_tag_to_language_name(l)): # Sort the locales by language name (Alphabetically)
        
        progress = localization_progess_all_repos[locale]
        progress_percentage = int(100 * progress['percentage'])
        download_name = 'Download'
        download_url = download_urls[locale]
        
        emoji_flag = mflocales.language_tag_to_flag_emoji(locale)
        language_name = mflocales.language_tag_to_language_name(locale)
        
        entry = f"""\
| {emoji_flag} {language_name} ({locale}) | [{download_name}]({download_url}) | ![Static Badge](https://img.shields.io/badge/{progress_percentage}%25-Translated-gray?style=flat&labelColor={'%23aaaaaa' if progress_percentage < 100 else 'brightgreen'}) |
"""
        download_table += entry
    
    new_discussion_body = new_discussion_body.format(download_table=download_table)
    
    # Escape markdown
    new_discussion_body = mfgithub.escape_for_upload(new_discussion_body)
    
    # Find discussion #1022
    find_discussion_result = mfgithub.github_graphql_request_query(gh_api_key, """                                                                                      
repository(owner: "noah-nuebling", name: "mac-mouse-fix") {
  discussion(number: 1022) {
    id
    url
  }
}
""")
    discussion_id = find_discussion_result['data']['repository']['discussion']['id']
    discussion_url = find_discussion_result['data']['repository']['discussion']['url']

    # Mutate the discussion body
    mutate_discussion_result = mfgithub.github_graphql_request_mutation(gh_api_key, is_dry_run, f"""                    
updateDiscussion(input: {{discussionId: "{discussion_id}", body: "{new_discussion_body}"}}) {{
    clientMutationId
}}
""")
    
    # Check for success
    print(f" Mutate discussion result:\n{json.dumps(mutate_discussion_result, indent=2)}")
    print(f" Discussion available at: { discussion_url }")
    
    
#
# Call main
#

if __name__ == "__main__":
    main()
