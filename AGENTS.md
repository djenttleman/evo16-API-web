# EVO 16 Remote

- Protocol authority is `docs/PROTOCOLO-EVO16.md`, based on hardware findings from October 15–16,
  2026. Older EVO8/May research is historical and deprecated wherever it conflicts. Do not revert
  current controls to make an old comment or test pass; update the obsolete reference instead.
- API v2 and web use real gain dB −8…50. USB uses `dB + 8`, byte 0…58. Profile v1 stores bytes;
  profile v2 declares `formatVersion: 2` and `gainEncoding: db`. Never double-convert a v2 profile.
- Preserve DI CS=4 bit 1 with read/modify/write, link EU58 CS=3, main 0x36 CS=18 signed Q8.8,
  logarithmic main display, and the documented analog/ADAT mute entity split. Do not guess USB
  registers or apply older EVO8 assumptions to EVO16.
- AppKit app owns the backend process. No independent launcher, broad pkill or killing port owners.
  CLI is an adapter to the app. Default builds go to `build/`; installation is explicit.
- Tests must not acquire USB. Use `backend/fixtures/usb_helper.py` through `EVO16_HELPER_PATH` only
  in isolated test runs. Software tests do not constitute physical verification. Track outstanding
  device checks in `docs/VALIDATION-v2.md`.
- Required checks for API/protocol changes:
  `python3 -m unittest backend.test_contract backend.test_presets backend.test_lifecycle`,
  `python3 backend/test_protocol_smoke.py`, `python3 backend/test_health_state.py`.
  For UI/scripts: `node --check web/app.js`, `bash -n menubar/build.sh menubar/install.command bin/evo16-remote`.
  For native/packaging changes build with `EVO16_PYTHON=<python> ./menubar/build.sh --release`,
  run the service `--self-check` and verify the app signature. Do not overwrite the installed app
  while testing. Public signing/notarization requires the publisher's credentials.
