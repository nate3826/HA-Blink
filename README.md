# Blink Live View for Home Assistant

The built-in Blink integration only shows the last thumbnail. This custom
integration adds a **Live view** camera to each Blink camera, so you see real
live video in Home Assistant.

## How it works

When you request live view, Blink doesn't send RTSP. It sends an `immis://`
address that uses Blink's own protocol over TLS, and Home Assistant can't play
that. This integration:

1. Reuses the login of your existing **Blink** integration, so there's no
   second sign-in or 2FA.
2. Opens a local relay for each camera at `tcp://127.0.0.1:<port>`.
3. When someone opens the live view, starts a Blink live view session and
   passes the MPEG-TS video (H.264 + AAC) to Home Assistant's stream
   component. You get HLS, or WebRTC through go2rtc.
4. When nobody is watching, ends the session so the camera can sleep.

## Install (HACS)

1. Set up the core **Blink** integration first (Settings → Devices & services).
2. In HACS → ⋮ → **Custom repositories**, add this repository's URL with type
   **Integration**.
3. Install **Blink Live View** and restart Home Assistant.
4. Settings → Devices & services → **Add integration** → **Blink Live View**.

To install by hand, copy `custom_components/blink_liveview` into your
`config/custom_components/` folder and restart.

Each Blink camera device gets a new entity, such as
`camera.front_door_live_view`.

## Show it on a dashboard

```yaml
type: picture-entity
entity: camera.front_door_live_view
camera_view: live
```

Or open the entity's more-info dialog, which always streams live.

## Things to know

* **Battery:** live view keeps a battery camera awake. Leave
  **Preload stream** turned off on these entities.
* **Session length:** Blink ends live view sessions after a while (often 30 s
  to a few minutes, depending on the camera and your plan). Home Assistant
  then reconnects on its own and the relay starts a new session, so expect a
  short gap.
* **Startup delay:** the camera has to wake up, so the first frame takes a few
  seconds.
* **Thumbnail:** the entity's still image is the normal Blink thumbnail. It
  doesn't wake the camera.
* **Errors:** if Blink refuses live view (camera offline or busy, sync module
  issues), the reason is logged and the relay waits 15 s before trying again.

## Debug logging

```yaml
logger:
  logs:
    custom_components.blink_liveview: debug
    blinkpy.livestream: debug
```
