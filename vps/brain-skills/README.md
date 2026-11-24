# Telma's brain skills

The four skills Telma runs on the brain, copied from the brain repo's `skills/` folder, which she
reads at `/home/agent/brain/skills` (read-only in her sandbox).

| Skill | What it does | Used by |
|---|---|---|
| [capture](capture/SKILL.md) | "save this" → one file in `inbox/` | her chats |
| [ask-brain](ask-brain/SKILL.md) | answers from the notes, with a link to each one | her chats |
| [triage](triage/SKILL.md) | files each inbox item in one home and empties the inbox | the brain-triage job |
| [lint](lint/SKILL.md) | fixes index drift and dead links, reports contradictions | the brain-triage job, right after triage |

They come from Daniel Moka's [brain template](https://github.com/dmoka/brain-template), under its
MIT license ([LICENSE](LICENSE)). The owner has changed `triage` and `lint` since; each change goes
through a PR on the brain repo, and the triage skill's wording is tested by the eval.
