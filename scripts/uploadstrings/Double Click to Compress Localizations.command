#!/bin/bash

# This is a script to help localizers compress the .xcloc files before uploading them. 
#   (This is the tail of a series of workarounds for a bug in Xcode, that I wrote more about elsewhere (Forces us to duplicate the .jpeg files.) – not sure if this is the best solution.)
# Credits to Claude 4.5


cd "$(dirname "$0")"

echo ""
echo "- Starting..."
echo "- Compressing .xcloc files..."

# Glob for .jpeg files and deduplicate them using hardlinks
python3 - <<'EOF'
import os
import hashlib
from pathlib import Path

seen = {}
linked_count = 0

for file in Path('.').rglob('*.jpeg'):
    if not file.is_file():
        continue
    
    checksum = hashlib.md5(file.read_bytes()).hexdigest()
    
    if checksum not in seen:
        seen[checksum] = str(file)
    else:
        original = seen[checksum]
        file.unlink()
        os.link(original, str(file))
        linked_count += 1
EOF

# Compress using tar (zip doesn't preserve the hardlink deduplication)
tar -czf "Compressed Localizations (Upload This).tar.gz" *.xcloc

echo "- Done. Created file \"Compressed Localizations (Upload This).tar.gz\"."
echo "    - You can upload the compressed localizations via:"
echo "        - GitHub: https://redirect.macmousefix.com/?target=mmf-localization-contribution"
echo "        - Email:  https://redirect.macmousefix.com/?target=mailto-noah"
echo ""