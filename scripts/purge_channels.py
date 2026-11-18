"""Deprecated unsafe multi-channel purge entry point.

Use ``scripts/reset_one_discord_channel.py`` instead. It only accepts one configured
channel and requires a matching channel ID plus the reviewed message count before
any deletion. This module intentionally performs no Discord or database operation.
"""

if __name__ == "__main__":
    raise SystemExit(
        "This multi-channel purge command is disabled. Use "
        "scripts/reset_one_discord_channel.py with an explicit channel and reviewed count."
    )
