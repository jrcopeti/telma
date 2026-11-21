# Use floating base image tags

Build from a floating tag like `node:22`, never from a pinned digest. The tag's maintainers rebuild
it when a security fix lands, so every build picks up the patch with no PR to merge. A pinned
digest freezes the image as it was the day it was pinned, holes included, and the bot PRs that
bump it pile up unmerged.

Why it matters: an image nobody updates is the most common way a container ships a known
vulnerability.

Source: [sources/2026-11-15-use-floating-image-tags.md](../sources/2026-11-15-use-floating-image-tags.md) (https://blog.example.org/floating-tags)
