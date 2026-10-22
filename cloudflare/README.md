# Telegram webhook relay

Deployed 2026-10-22: https://kids-weekend-webhook.petal202.workers.dev. Encrypted GITHUB_TOKEN and RELAY_SECRET configured. Zernio webhook 6ad9ee969dee251af2f2e7cb subscribes to message.received for the Telegram account only. Test delivery succeeded; missing auth returns 401. A real owner reply (Telegram message 30397) received a successful 202 webhook response and triggered workflow dispatch.

This relay removes cron waiting, but still dispatches GitHub Actions. Runner queue/startup delays remain. It is not a direct Cloudflare publisher.

1. Deploy this directory using Workers Free, never upgrade billing automatically.
2. Add encrypted secrets RELAY_SECRET (random 32 bytes) and GITHUB_TOKEN (fine-grained token restricted to petal202-cell/insta_2026, Actions write).
3. Register Zernio message.received webhook at /webhook, accountIds restricted to Telegram account 6ad763eed0cf171eade6fca6; set custom header X-Relay-Secret to matching secret. Do not change Telegram bot's own webhook (Zernio owns it).
4. Verify /health configured=true. Send webhook.test; it must NOT dispatch. Invalid secret must return 401. Send an owner hold command to a test ledger and verify an automatic workflow_dispatch run and held ledger; do not test by republishing a live post.
5. Preserve current schedule until end-to-end validation succeeds. Workflow concurrency must remain family-weekend-single-writer, cancel-in-progress=false. Processor re-fetches Telegram owner identity/time and verifies draft fingerprint/target before publication. Relay payload never authorizes publication.

No token or secret belongs in source control. Production subscription is active. Group replies were verified; ordinary group text was not seen during initial testing, so reply to the bot's preview when sending commands.
