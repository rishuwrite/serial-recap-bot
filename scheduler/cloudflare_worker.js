/**
 * Optional Cloudflare Worker nightly scheduler (`scheduler/cloudflare_worker.js`)
 *
 * Schedules (configure in Cloudflare Dashboard -> Workers -> Triggers -> Cron Triggers):
 * - `30 18 * * *`       -> Exact 12:00 AM IST (Midnight) nightly run for all 9 shows
 *
 * Environment Variables to set in Cloudflare Worker Settings -> Variables:
 * - `GITHUB_OWNER`: Your GitHub username
 * - `GITHUB_REPO`:  `serial-recap-bot`
 * - `GITHUB_PAT`:   Your GitHub Personal Access Token (with `repo` and `workflow` scope)
 */

export default {
  async scheduled(event, env, ctx) {
    // 30 18 * * * UTC is exactly 00:00 (12:00 AM Midnight) IST
    if (event.cron === "30 18 * * *") await dispatch(env, "all");
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/trigger") {
      const show = url.searchParams.get("show") || "all";
      const status = await dispatch(env, show);
      return new Response(`Triggered show=${show}: HTTP ${status}`);
    }
    return new Response("Serial Recap Bot optional nightly scheduler active");
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

function ghHeaders(env) {
  return {
    "Authorization": `Bearer ${env.GITHUB_PAT}`,
    "Accept": "application/vnd.github+json",
    "User-Agent": "SerialRecapBot-Watchdog/1.0"
  };
}
