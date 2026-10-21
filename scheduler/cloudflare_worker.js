/**
 * 100% FREE Cloudflare Worker Cron Trigger & Log Watchdog (`scheduler/cloudflare_worker.js`)
 *
 * Schedules (configure in Cloudflare Dashboard -> Workers -> Triggers -> Cron Triggers):
 * - `30 18 * * *`       -> Exact 12:00 AM IST (Midnight) nightly run for all 8 shows
 * - `30 20,22,0,2 * * *` -> Watchdog checks at 2:00 AM, 4:00 AM, 6:00 AM, 8:00 AM IST
 *
 * Environment Variables to set in Cloudflare Worker Settings -> Variables:
 * - `GITHUB_OWNER`: Your GitHub username
 * - `GITHUB_REPO`:  `serial-recap-bot`
 * - `GITHUB_PAT`:   Your GitHub Personal Access Token (with `repo` and `workflow` scope)
 */

const SHOW_KEYS = ["kaisi", "bhabhi", "sohni", "rimjhim", "mannsundar", "atisundar", "patibrahma", "ishq"];

export default {
  async scheduled(event, env, ctx) {
    const cron = event.cron;
    // 30 18 * * * UTC is exactly 00:00 (12:00 AM Midnight) IST
    if (cron === "30 18 * * *") {
      await dispatch(env, "all");
      return;
    }
    // Otherwise run the log-inspecting watchdog & self-healer
    await checkLogsAndRerun(env);
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/trigger") {
      const show = url.searchParams.get("show") || "all";
      const status = await dispatch(env, show);
      return new Response(`Triggered show=${show}: HTTP ${status}`);
    }
    if (url.pathname === "/watchdog") {
      const msg = await checkLogsAndRerun(env);
      return new Response(msg);
    }
    return new Response("Serial Recap Bot External Scheduler & Watchdog Active");
  }
};

async function dispatch(env, onlyShow) {
  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/recap.yml/dispatches`;
  const resp = await fetch(url, {
    method: "POST",
    headers: ghHeaders(env),
    body: JSON.stringify({
      ref: "main",
      inputs: {
        only_show: onlyShow,
        video_id: "",
        test_mode: "false",
        upload: "true",
        publish_now: "false"
      }
    })
  });
  return resp.status;
}

async function checkLogsAndRerun(env) {
  const runsUrl = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/recap.yml/runs?per_page=5`;
  const r = await fetch(runsUrl, { headers: ghHeaders(env) });
  if (!r.ok) return `Failed to fetch runs: ${r.status}`;
  const data = await r.json();
  const runs = data.workflow_runs || [];
  if (runs.some(x => x.status === "in_progress" || x.status === "queued")) {
    return "Run currently in progress; skipping watchdog.";
  }

  const latest = runs[0];
  if (!latest) {
    await dispatch(env, "all");
    return "No runs found; triggered full run.";
  }

  const jobsUrl = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/runs/${latest.id}/jobs?per_page=50`;
  const jr = await fetch(jobsUrl, { headers: ghHeaders(env) });
  const reruns = [];
  if (jr.ok) {
    const jdata = await jr.json();
    for (const job of (jdata.jobs || [])) {
      const name = (job.name || "").toLowerCase();
      const conclusion = (job.conclusion || "").toLowerCase();
      if (["failure", "timed_out", "cancelled"].includes(conclusion)) {
        for (const k of SHOW_KEYS) {
          if (name.includes(k)) {
            await dispatch(env, k);
            reruns.push(k);
          }
        }
      }
    }
  }
  // Also trigger internal repo watchdog to check Dangal TV feed vs state/<show>.json
  await dispatch(env, "watchdog");
  return `Watchdog complete. Targeted reruns: ${reruns.join(", ") || "none"}`;
}

function ghHeaders(env) {
  return {
    "Authorization": `Bearer ${env.GITHUB_PAT}`,
    "Accept": "application/vnd.github+json",
    "User-Agent": "SerialRecapBot-Watchdog/1.0"
  };
}
