"""Watchdog & Log-Reader Auto-Healer (`recap/watchdog.py`).

Checks:
1. Per-show execution status & log tails in `state/<show>_status.json`.
2. GitHub Actions workflow run jobs & logs via the GitHub REST API (when `GITHUB_TOKEN` is available).
3. Live Dangal TV feed (`feed.find_episode(show)`) to detect any new unseen episode that was missed or failed.
4. Live YouTube channel (`youtube.already_uploaded()`) so an already-uploaded episode is NEVER rerun or duplicated.

If any show failed or has an unprocessed episode today, automatically triggers a targeted rerun
for that specific show via GitHub Actions `workflow_dispatch` (capped at MAX_RETRIES_PER_DAY per show).
"""
import datetime as dt, json, os, sys, time, requests
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import config as S, feed, youtube

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
MAX_RETRIES_PER_DAY = int(os.getenv("MAX_RETRIES_PER_DAY") or 4)
RETRY_FILE = os.path.join(S.BASE, "state", "watchdog_retries.json")

def _load_retries(today_str):
    try:
        data = json.load(open(RETRY_FILE))
        if data.get("date") == today_str:
            return data
    except Exception:
        pass
    return {"date": today_str, "counts": {}, "history": []}

def _save_retries(data):
    os.makedirs(os.path.join(S.BASE, "state"), exist_ok=True)
    json.dump(data, open(RETRY_FILE, "w"), ensure_ascii=False, indent=2)

def _diagnose_log(log_text, error_text):
    combined = ((error_text or "") + "\n" + (log_text or "")).lower()
    if "429" in combined or "quota" in combined or "resource_exhausted" in combined:
        return "RATE_LIMIT_OR_QUOTA"
    if "gemini" in combined or "generatecontent" in combined:
        return "GEMINI_TRANSIENT_FAILURE"
    if "edge" in combined or "voice" in combined or "gtts" in combined:
        return "TTS_VOICE_FAILURE"
    if "pollinations" in combined or "cloudflare" in combined or "image" in combined:
        return "IMAGE_GEN_FAILURE"
    if "ffmpeg" in combined:
        return "FFMPEG_RENDER_ERROR"
    if "youtube" in combined or "upload" in combined or "token" in combined:
        return "YOUTUBE_UPLOAD_ERROR"
    return "UNKNOWN_OR_TIMEOUT"

def _check_github_run_logs(repo, token, run_id):
    """Inspect jobs of the current or latest GitHub Actions workflow run to find failed/timed-out show jobs."""
    failed_shows = {}
    if not (repo and token and run_id):
        return failed_shows
    hdr = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs",
                         headers=hdr, params={"per_page": 50}, timeout=30)
        if r.status_code != 200:
            return failed_shows
        for job in r.json().get("jobs", []):
            name = (job.get("name") or "").lower()
            conclusion = (job.get("conclusion") or "").lower()
            if conclusion in ("failure", "timed_out", "cancelled"):
                for k in S.SHOWS:
                    if k in name:
                        # Fetch last lines of job log for diagnosis
                        log_snip = ""
                        try:
                            lr = requests.get(f"https://api.github.com/repos/{repo}/actions/jobs/{job['id']}/logs",
                                              headers=hdr, timeout=20)
                            if lr.status_code == 200:
                                log_snip = lr.text[-1200:]
                        except Exception:
                            pass
                        failed_shows[k] = {
                            "conclusion": conclusion,
                            "diagnosis": _diagnose_log(log_snip, conclusion),
                            "log_tail": log_snip[-500:],
                        }
    except Exception as e:
        print("   github job inspection warning:", str(e)[:120])
    return failed_shows

def _trigger_show_rerun(repo, token, show_key, ref="main"):
    """Trigger a targeted workflow_dispatch run for a single show that failed or was missed."""
    if not (repo and token):
        print(f"   [local mode] would re-trigger show={show_key} (set GITHUB_TOKEN & GITHUB_REPOSITORY to dispatch)")
        return False
    hdr = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    payload = {
        "ref": ref,
        "inputs": {
            "only_show": show_key,
            "video_id": "",
            "test_mode": "false",
            "upload": "true",
            "publish_now": "false",
        }
    }
    r = requests.post(f"https://api.github.com/repos/{repo}/actions/workflows/recap.yml/dispatches",
                      headers=hdr, json=payload, timeout=30)
    if r.status_code in (200, 204):
        print(f"   -> AUTO-RERUN DISPATCHED for '{show_key}' (HTTP {r.status_code})")
        return True
    print(f"   -> dispatch failed for '{show_key}': {r.status_code} {r.text[:200]}")
    return False

def run_watchdog():
    now_ist = dt.datetime.now(IST)
    today = now_ist.strftime("%Y-%m-%d")
    repo = os.getenv("GITHUB_REPOSITORY", "")
    token = os.getenv("GH_PAT") or os.getenv("GITHUB_TOKEN", "")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    ref = os.getenv("GITHUB_REF_NAME") or "main"

    print(f"== WATCHDOG LOG INSPECTOR & AUTO-HEALER | {now_ist.strftime('%Y-%m-%d %H:%M:%S IST')} ==")
    retries = _load_retries(today)
    gh_failures = _check_github_run_logs(repo, token, run_id)

    to_rerun = []
    for k, show in S.SHOWS.items():
        st = feed.get_status(k)
        st_status = st.get("status", "unknown")
        st_date = st.get("date_ist", "")
        used_retries = retries["counts"].get(k, 0)

        # 1. Check if Dangal TV currently has an unseen full episode for this show
        unseen_ep = feed.find_episode(k)

        # 2. If unseen episode exists, verify if it was already uploaded to YouTube (prevents duplicates)
        if unseen_ep and youtube.enabled():
            src_ep = unseen_ep.get("episode") or ""
            target_ep = str(int(src_ep) + 2) if str(src_ep).isdigit() else src_ep
            yt_existing = youtube.already_uploaded(show, target_ep, source_vid=unseen_ep["id"])
            if yt_existing:
                print(f"   [{k}] unseen episode {src_ep} already on YouTube ({yt_existing}); syncing state")
                feed.mark_done(k, unseen_ep["id"], episode_no=src_ep, target_ep=target_ep, yt_id=yt_existing)
                continue

        # 3. Determine if show failed in logs or missed an available unseen episode
        reason = None
        if k in gh_failures:
            diag = gh_failures[k]["diagnosis"]
            reason = f"GitHub job {gh_failures[k]['conclusion']} ({diag})"
        elif st_date == today and st_status == "failed":
            diag = _diagnose_log(st.get("log_tail", ""), st.get("error", ""))
            reason = f"status=failed ({diag}: {st.get('error', '')[:100]})"
        elif unseen_ep:
            reason = f"unprocessed new episode {unseen_ep.get('episode')} ({unseen_ep['id']})"

        if reason:
            if used_retries >= MAX_RETRIES_PER_DAY:
                print(f"   [{k}] NEEDS RERUN ({reason}) -> max retries ({MAX_RETRIES_PER_DAY}) reached for {today}; skipping")
            else:
                print(f"   [{k}] NEEDS RERUN ({reason}) -> scheduling retry {used_retries + 1}/{MAX_RETRIES_PER_DAY}")
                to_rerun.append((k, reason))
        else:
            print(f"   [{k}] OK (status={st_status}, last_date={st_date or 'n/a'}, no pending episode)")

    if not to_rerun:
        print("== All shows healthy & up-to-date. Zero reruns needed. ==")
        return 0

    for k, reason in to_rerun:
        time.sleep(2)
        if _trigger_show_rerun(repo, token, k, ref=ref):
            retries["counts"][k] = retries["counts"].get(k, 0) + 1
            retries["history"].append({
                "show": k,
                "time_ist": now_ist.strftime("%H:%M:%S IST"),
                "reason": reason,
                "attempt": retries["counts"][k],
            })
    _save_retries(retries)
    return 0

if __name__ == "__main__":
    sys.exit(run_watchdog())
