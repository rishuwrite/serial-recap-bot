# Serial recap bot (Dangal TV serials -> 2-3 min "motion comic" recaps), standalone repo

## How a video is made
1. `feed.py`   finds the newest unseen "Full Episode" of a show on the Dangal TV channel (RSS, or YouTube Data API if YT_API_KEY is set).
2. `gemini.py` Gemini watches that public YouTube episode (audio + video) and writes: hook, 8-9 scenes (narration), cliffhanger, a clearly-labelled prediction, image prompts, keywords.
3. `voice.py`  narration -> speech (edge-tts hi-IN-SwaraNeural, falls back to gTTS). One voice for the whole video.
4. `images.py` one AI illustration per scene (Cloudflare Workers AI if configured, else Pollinations). Failed image -> designed title card (never blank).
5. `render.py`  each scene = illustration + slow zoom/pan (alternating), top chips (show/episode, scene n/N), big captions, yellow progress bar; then concatenated; background music: uses a user-provided licensed track from /music when present; otherwise generates a simple original ambient/suspense tone bed locally with FFmpeg (no downloaded music assets).
6. `meta.py`    title (true date + episode no.), chapters, ~480 chars of relevant tags, description with official-episode link, thumbnail (illustration + big Hindi hook).
7. `youtube.py` uploads (private + scheduled for the show's morning slot, or public now). Only when you turn it on.

## Test the quality FIRST (no upload)
Actions > serial-recaps > Run workflow: choose a show, leave **upload OFF**.
- test_mode ON  = 3 scenes (~5 min run). test_mode OFF = full 2-3 min video.
Download the result from the run page > Artifacts > recap-<show>: the .mp4, the .jpg thumbnail, and the `_preview` folder (every illustration, contact_sheet.jpg, script + prompts).
Judge: illustration look, voice, caption readability, length. If not happy, tell me what to change.

## Go live (only after you approve the quality)
1. Secrets: GEMINI_API_KEY (required). For upload: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN (own Google Cloud project for this channel).
   Optional: YT_API_KEY (see last 50 uploads), CF_ACCOUNT_ID + CF_API_TOKEN (more reliable images), POLLINATIONS_TOKEN.
2. Variables: ENABLE_SCHEDULE = true (turns the 03:30 IST daily run on), SERIAL_CHANNEL_NAME (optional), SERIAL_VOICE (optional).
3. Background music is automatic. For richer music, optionally put a track you have rights to use (.mp3 or .m4a) in `/music`; the bot will use it instead of the generated ambient bed. Do not add tracks unless their licence permits your intended YouTube use.
Schedule: all 8 shows run daily at 03:30 IST; each recap publishes at its slot (06:30 ... 10:00 IST, see config.py).


## Update: next-day episode targeting and animated captions
- Discovery scans up to 150 recent uploads when `YT_API_KEY` is configured, follows pagination, matches each of the eight configured shows using normalized aliases, and skips titles whose episode number cannot be parsed. RSS fallback can return fewer uploads; configure the API key for reliable discovery.
- Recap analysis uses the source episode number. The output title/date/on-screen label targets the next day and episode (+1); the description distinguishes the source recap from predictions. Date parsing uses the date in the source title when supported.
- Captions now highlight the currently spoken word in yellow. Word timings are estimated from character lengths within each narrated line, not forced-aligned to phonemes, so timing may need adjustment for expressive Hindi narration.
- Run a test for each show before enabling scheduled uploads.


### Background music

If `/music` contains an `.mp3` or `.m4a` track, the bot mixes it quietly under narration and fades it in/out. If no track is present, it creates a basic original ambient/suspense tone bed locally with FFmpeg. This avoids downloading copyrighted music, but the generated bed is deliberately simple rather than a full instrumental composition. Always listen to the final mix before publishing.
