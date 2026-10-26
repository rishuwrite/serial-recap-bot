# YouTube auto-upload setup (one time, ~20 min, free)

1. console.cloud.google.com -> New project (e.g. desh-ki-nabz)
2. APIs & Services -> Library -> "YouTube Data API v3" -> Enable
3. OAuth consent screen / Google Auth Platform -> External -> fill app name + your email.
   Add your Google account as Test user. Then press **Publish app (In production)**.
   (If you stay in "Testing", the refresh token expires after 7 days and uploads stop.)
4. Credentials -> Create credentials -> OAuth client ID -> Application type **Web application**
   Authorized redirect URI: https://developers.google.com/oauthplayground
   Copy the Client ID and Client secret.
5. Open developers.google.com/oauthplayground
   - gear icon -> tick "Use your own OAuth credentials" -> paste Client ID / secret
   - In "Input your own scopes" type: https://www.googleapis.com/auth/youtube.upload  -> Authorize APIs
   - Sign in with the Google account that owns the channel (pick the Desh Ki Nabz channel if asked)
   - "Advanced" -> "Go to ... (unsafe)" -> Allow
   - Click "Exchange authorization code for tokens" -> copy the **Refresh token**
6. GitHub repo -> Settings -> Secrets and variables -> Actions -> New repository secret:
   YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
7. IMPORTANT - API audit: for projects created after 28 Jul 2020, videos uploaded through the API stay
   PRIVATE until the project passes YouTube's compliance audit. Submit the free form:
   "YouTube API Services - Audit and Quota Extension Form" (support.google.com/youtube/contact/yt_api_form)
   Until approved, videos arrive private (you can still download them from Actions > Artifacts).
