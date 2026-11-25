# Kill switch: Telma

**When:** a canary or exfil-tripwire alert in brain-server `#alerts`, a cron alert for a job you
didn't ask for, or a memory diff with something nobody saved.
ticket-bay-bot keeps running; it shares nothing with Telma but the host. If the host itself looks
compromised (a root login you don't know, a changed `/etc`, an unknown process), run this and
[the bot's kill switch](https://github.com/jrcopeti/ticket-bay-bot/blob/main/vps/ticket-bay-bot/kill-switch.md),
then rebuild the VPS (see [README.md](README.md)).

**Read the canary alert first.** It shows the source IP and user agent:
- from the VPS's IP: Telma's browser tool opened the link;
- from a hosting company's IP with a desktop Chrome user agent, and a tripwire alert for `web_extract`
  in the same minute: her `web_extract` opened it. With no web backend set, Hermes sends it through
  keyless Exa, whose crawler does the fetch (step 6: FDCservers, Chrome on macOS);
- user agent `Discordbot`: she put it in a Discord reply and the link preview fetched it;
- from anywhere else: the content already left, and someone is using it. Unless it was you: your own
  open, or a preview of the link on your local machine or phone.

**A tripwire alert** names the tool, the session and the notes the call carried. The call went
ahead: treat the notes named as gone. A search you asked for with a note's words in it fires it too.
Every alert is also in `/home/agent/.local/state/exfil-tripwire/alerts.log`, kept even when Discord
didn't get it.

**A cron alert** names what she did with a cron job (created, changed, paused, resumed, ran,
cancelled or removed it), the job's name, schedule, prompt and toolsets, and the session. The call
went ahead. If you asked for it, nothing to do. If you didn't, a page or a message in that session
asked for it: remove the job (`sudo -iu agent hermes cron list`, then `sudo -iu agent hermes cron remove <id>`),
or put back the one she changed, then read the session. A job with web or browser tools is a way
out on a timer: treat it like a tripwire alert. Every cron alert is
also in `/home/agent/.local/state/cron-alert/alerts.log`.

## 1. Stop

```sh
sudo -iu agent hermes gateway stop --yes                    # chats and every cron job, sync-brain included; --yes interrupts live runs
sudo systemctl --user -M agent@ disable hermes-gateway      # stays off after a reboot (linger is on)
sudo -iu agent bash -c 'docker ps -aq --filter name=hermes- | xargs -r docker rm -f'
```

## 2. Cut credentials

- GitHub, brain repo → Settings → Deploy keys: delete Telma's key. Nothing can push to the brain now.
- OpenRouter → Keys: disable Telma's key.
- Discord developer portal: reset her bot token, only if a session shows it was read.

## 3. Look

```sh
sudo -iu agent /home/agent/.hermes/scripts/memory-diff.sh             # memory and skills saved since the last check
sudo -iu agent git -C /home/agent/brain log --stat origin/main..HEAD  # commits not pushed yet
sudo -iu agent ls /home/agent/brain-quarantine                        # pushes sync-brain refused, if any
```

On GitHub, read the brain's `telma/proposals` branch if there is one: her changes to skills and rules
wait there, not on `main`.

```sh
sudo grep -E 'tool_executor|Turn ended' /home/agent/.hermes/logs/agent.log | tail -50   # tool calls around the alert's time
```

The log names the tools; the messages and arguments are in the `messages` table of
`/home/agent/.hermes/state.db` (no `sqlite3` on the VPS: use Python's). Look for web or browser calls
and URLs in her replies that carry brain text. On GitHub, check the brain's commits since the last one
you know.

## 4. Back on

- Undo planted memory or skills with the restore line memory-diff prints.
- Delete the brain's `telma/proposals` branch on GitHub if it carries something planted. sync-brain says once that it was dropped.
- New deploy key in `/home/agent/.config/brain-deploy`, added on GitHub. New OpenRouter key in her `.env`.
- The canary is burned: delete its file from the brain, its token on canarytokens.org and its short
  link, then make a new one under a new name.
- `sudo systemctl --user -M agent@ enable --now hermes-gateway`
