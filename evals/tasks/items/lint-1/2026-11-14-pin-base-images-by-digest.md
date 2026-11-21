---
source: https://docs.example.org/containers/pinning
captured_at: 2026-11-14T20:11:05Z
captured_by: agent
note: "image pinning"
fetch: text-only
---

Pinning container images. A tag is a pointer that can move; a digest is the hash of one image
and never changes. Pin base images by digest so a build is reproducible, and let an update bot
propose new digests as pull requests.
