"""Constants for Blink Live View."""

DOMAIN = "blink_liveview"
BLINK_DOMAIN = "blink"

# Interface the local relay listens on. Only Home Assistant (and the bundled
# go2rtc, which shares its network namespace) needs to reach it.
RELAY_HOST = "127.0.0.1"

# After Blink refuses a live view request, don't ask again for this long.
# Home Assistant's stream worker retries quickly; this keeps us from hammering
# the Blink API (and waking a battery camera over and over).
FAILURE_COOLDOWN = 15
