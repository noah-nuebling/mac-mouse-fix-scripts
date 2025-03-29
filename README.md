# mac-mouse-fix-scripts

Collection of Python scripts utility functions which we want to share between the different repos of the Mac Mouse Fix project.
    (As of [Mar 2025]: mac-mouse-fix, mac-mouse-fix-website, and mac-mouse-fix/update-feed)

We plan to embed this repo as a submodule in both the mac-mouse-fix and mac-mouse-fix-website repos. This enables syncing the repo between both hosting repos.

(We also tried subtrees but pushing was extremely slow)

GH Submodule resources:

    gitaarik's GH Gist:
        https://gist.github.com/gitaarik/8735255
    gitsubmodules docs:
        https://git-scm.com/docs/gitsubmodules
    git-submodule docs: (verbose)
        https://git-scm.com/docs/git-submodule
    Git-Tools-Submodules docs: (its a book)
        https://git-scm.com/book/en/v2/Git-Tools-Submodules

## Setup

1. Add mac-mouse-fix-scripts as a submodule to a host repo use this command:

       git submodule add https://github.com/noah-nuebling/mac-mouse-fix-scripts

2. Add an ./.env file at your repo root with this content:

       PYTHONPATH=mac-mouse-fix-scripts/shared/

3. Add a `./run` bash script at your repo root with this content:

       #!/bin/bash
       python3 mac-mouse-fix-scripts/run.py "$@";

   Then make it executable using

       chmod +x ./run

## Workflow

1. You can now run any python scripts inside your repo (including the mac-mouse-fix-scripts submodule) using:
       ./run <subcommand> <args>
2. You can also run the scripts using the VSCode debugger and the ./.env should make linting work properly.
3. If you add a new script, and it has dependencies, make sure to include a requirements.txt file with those dependencies in the same folder, so that run.py can find the dependencies.
4. 
**How to work with Git Submodules?**

Basically, you have 2 nested repos. They're both their own repo, but the outer repo has a reference to a specific commit of the inner repo (instead of tracking that folder directly.)
That's really it. Just commit and push in the inner repo, then you can create a commit in the outer repo referencing that commit.