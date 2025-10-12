`localization_compression_script.sh` is a script to help localizers compress the .xcloc files before sending them to me.
    - Use `embedscript.py` to wrap this script in a notarized .app bundle before distributing to localizers.
        - We're using this command: [Oct 2025]
            ```
            ./run embedscript ./mac-mouse-fix-scripts/scripts/uploadstrings/localization_compression/localization_compression_script.py \
            --app-path "./mac-mouse-fix-scripts/scripts/uploadstrings/localization_compression/Compress Translations.app/" \
            --bundle-id "com.nuebling.compresslocalizations"
            ```
    - uploadstrings.py will automatically include the .app bundle for localizers. (Where it will be sitting next to .xcloc files which it compresses when double-clicking.)

Why are we doing this / is this worth it? [Oct 2025]

    This is the tail of a series of workarounds for a bug in Xcode, that I wrote more about elsewhere (Forces us to duplicate the .jpeg files.) (Update: See FB20608107)
    None of this would be necessary if:
        - Xcode fixed that bug
        - We didn't include localizer screenshots
        - We used another distribution method like CrowdIn
        - We provided a method for localizers to upload localization files that accepts larger file sizes, like a MegaUpload link. (Currently we use Email and GitHub comments which have < 50 MB limits)
    Other benefits of this:
        - The `Compress Translations.app` shows a little message after compressing, telling localizers where they can submit their translations. That's kinda neat.

Testing app-translocation:

    Navigate to the directory of `Compress Translations.app`
        cd ...

    Add quarantine flag (simulates downloading from internet)
        xattr -w com.apple.quarantine "0081;$(printf '%x' $(date +%s));Safari;" "Compress Translations.app"

    Verify quarantine was added
        xattr -l "Compress Translations.app"

    Now double-click the app in Finder to test (it should get translocated and then undo the translocation automatically)
