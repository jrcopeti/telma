---
source: pasted
captured_at: 2026-11-19T10:05:00Z
captured_by: agent
note: "great piece, so true"
fetch: text-only
---

Feature flags are debt with interest. Every flag doubles the paths through the code it guards, and
the tests rarely cover both. Teams add flags fast and remove them never: a year later nobody knows
whether `new_checkout` can go, so it stays, and the old path rots behind it.

The fix is a rule, not a tool: remove a flag within two weeks of its full rollout. A flag that has
to live longer gets an owner and an expiry date in the code, next to its definition, and the build
warns once the date has passed.
