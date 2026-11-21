# Pin base images by digest

Pin every Docker base image by its digest (`node:22@sha256:…`), never by a tag alone. A tag like
`node:22` moves: the image behind it is rebuilt and repushed, so the same Dockerfile builds
something different next week and a broken build can't be reproduced. A digest names one image
for good. Renovate or Dependabot opens a PR when a newer digest ships, so updates still arrive,
reviewed.

Why it matters: a build that changes without a commit is the hardest kind of breakage to trace.

Source: [sources/2026-11-14-pin-base-images-by-digest.md](../sources/2026-11-14-pin-base-images-by-digest.md) (https://docs.example.org/containers/pinning)
