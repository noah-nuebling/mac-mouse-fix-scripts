Terminology

    We're using 'translate' instead of 'localize' for translator-facing stuff since both kinda mean the same thing and 'translate' is more widely understood. [Oct 2025]  
      - Con: Xcode uses 'localization' (e.g. .xc*loc*) and localizers will interact with that.
      - Renamed many things from 'localize' -> 'translate' in commit c3062736eaa44cdb56590d6713a972da3082fc07 [Oct 2025]

On the localization_guide.md screenshots: [Oct 2025]

Random tips / considerations: (By far not all, not sure why I'm choosing to write these down [Oct 2025])
    -  Remove the `height=` tag after uploading image to GitHub to preserve aspect ratio. 
    - For the Finder screenshot I used the 'default' size of a new Finder window I think [Oct 2025]
    - For the .xcloc editor screenshots I made the window as small as possible so the UI elements would be big in the screenshot [Oct 2025]

`compress_translations`

    `compress_translations.py` is a script to help translators compress the .xcloc files before sending them to me.
        - Use `embedscript.py` to wrap this script in a notarized .app bundle before distributing to translator.
            - We're using this command: [Oct 2025]
                ```
                ./run embedscript ./mac-mouse-fix-scripts/scripts/uploadstrings/compress_translations/compress_translations.py \
                --app-path "./mac-mouse-fix-scripts/scripts/uploadstrings/compress_translations/Compress xcloc files.app/" \
                --bundle-id "com.nuebling.compress-translations"
                ```
        - uploadstrings.py will automatically include the .app bundle for translators. (Where it will be sitting next to .xcloc files which it compresses when double-clicking.)

    Why are we doing this / is this worth it? [Oct 2025]

        This is the tail of a series of workarounds for a bug in Xcode, that I wrote more about elsewhere (Forces us to duplicate the .jpeg files.) (Update: See FB20608107)
        None of this would be necessary if:
            - Xcode fixed that bug
            - We didn't include translator screenshots
            - We used another distribution method like CrowdIn
            - We provided a method for translators to upload translation files that accepts larger file sizes, like a MegaUpload link. (Currently we use Email and GitHub comments which have < 50 MB limits)
        Other benefits of this:
            - The `Compress xcloc files.app` shows a little message after compressing, telling translators where they can submit their translations. That's kinda neat.

    Testing app-translocation:

        Navigate to the directory of `Compress xcloc files.app`
            cd ...

        Add quarantine flag (simulates downloading from internet)
            xattr -w com.apple.quarantine "0081;$(printf '%x' $(date +%s));Safari;" "Compress xcloc files.app"

        Verify quarantine was added
            xattr -l "Compress xcloc files.app"

        Now double-click the app in Finder to test (it should get translocated and then undo the translocation automatically)
