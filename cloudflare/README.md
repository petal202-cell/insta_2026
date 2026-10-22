# Telegram webhook relay (not activated)

Cloudflare account Worker `kids-weekend-webhook` currently has its initial Hello World deployment only. Deploy worker.js before registering a webhook.

This relay removes cron waiting, but still dispatches GitHub Actions. Runner queue/startup delays remain. It is not a direct Cloudflare publisher.

1. Deploy this directory using Workers Free, never upgrade billing automatically.
2. Add encrypted secrets RELAY_SECRET (random 32 bytes) and GITHUB_TOKEN (fine-grained token restricted to petal202-cell/insta_2026, Actions write).
3. Register Zernio message.received webhook at /webhook, accountIds restricted to Telegram account 6ad763eed0cf171eade6fca6; set custom header X-Relay-Secret to matching secret. Do not change Telegram bot's own webhook (Zernio owns it).
4. Verify /health configured=true. Send webhook.test; it must NOT dispatch. Invalid secret must return 401. Send an owner hold command to a test ledger and verify an automatic workflow_dispatch run and held ledger; do not test by republishing a live post.
5. Preserve current schedule until end-to-end validation succeeds. Workflow concurrency must remain family-weekend-single-writer, cancel-in-progress=false. Processor re-fetches Telegram owner identity/time and verifies draft fingerprint/target before publication. Relay payload never authorizes publication.

No token or secret belongs in source control. No production webhook has been registered by this preparation.
