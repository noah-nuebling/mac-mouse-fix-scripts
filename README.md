# mac-mouse-fix-scripts

Collection of Python scripts which we want to share between the mac-mouse-fix and mac-mouse-fix-website repos.

The reason for creating this is that we want to share the localization logic between mac-mouse-fix and mac-mouse-fix-website.

We plan to embed this repo as a submodule in both the mac-mouse-fix and mac-mouse-fix-website repos. This enables syncing the repo between both hosting repos.

(We also tried subtrees but pushing was extremely slow)

## How to set up

1. Add this repo as a submodule using this command:

    git submodule add https://github.com/noah-nuebling/mac-mouse-fix-scripts

2. git config stuff:

    Make commands such as `git pull` apply to submodules

        git config --global submodule.recurse true

    Enable warnings if you forget to `git push` changes to the submodule

        git config push.recurseSubmodules check

    Make `git diff` include the submodule
   
        git config --global diff.submodule log

    Show submodule changes in `git st`

        git config status.submodulesummary 1

3. Add an .env file at your repo root with this content:

    PYTHONPATH=mac-mouse-fix-scripts/Shared/

4. Add a bash script at your repo root with this content:

    #!/bin/bash
    python3 mac-mouse-fix-scripts/run.py "$@";

-> Now you can run the scripts using ./run <subcommand> <args>
-> You can also run the scripts using the VSCode debugger and linting should work properly. (The .env file is necessary for that.)

## How to sync

To push:

    git push --recurseSubmodules

To pull:

    git pull (make sure submodule.recurse option is enabled)