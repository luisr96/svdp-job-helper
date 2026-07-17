"""
Sends the weekly job market snapshot as a Resend Broadcast to an existing
Resend Audience (created and populated via the Resend dashboard already --
this script only handles the recurring send, not setup).

Env vars needed (.env locally, GitHub secrets for the scheduled run):
    SUPABASE_URL               e.g. https://wvkbxhkrjrfetgwdlcaj.supabase.co
    SUPABASE_PUBLISHABLE_KEY   the publishable key (dashboard calls this
                               "Publishable key"; older Supabase docs call
                               the same thing "anon key" -- same value)
    RESEND_API_KEY             from resend.com
    RESEND_AUDIENCE_ID         from the Resend dashboard -- Audiences -> your audience -> copy its ID
    RESEND_FROM_EMAIL          e.g. onboarding@resend.dev for testing, or
                               your own verified domain once ready for a
                               real list

    python send_newsletter_resend.py
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

RESEND_BASE = "https://api.resend.com"


def _rpc(supabase_url: str, publishable_key: str, function_name: str) -> list[dict]:
    resp = requests.post(
        f"{supabase_url}/rest/v1/rpc/{function_name}",
        headers={"apikey": publishable_key, "Authorization": f"Bearer {publishable_key}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def build_html(top_categories: list[dict], movers: list[dict]) -> str:
    def change_color(change: int) -> str:
        if change > 0:
            return "#1a7f37"  # green
        if change < 0:
            return "#cf222e"  # red
        return "#57606a"  # neutral gray

    top_rows = "".join(
        f"""
        <tr>
          <td style="padding:10px 16px;border-bottom:1px solid #edf0f2;color:#24292f;font-size:14px;">
            {i}. {row['category_label']}
          </td>
          <td style="padding:10px 16px;border-bottom:1px solid #edf0f2;color:#24292f;font-size:14px;text-align:right;font-weight:600;">
            {row['listing_count']:,}
          </td>
        </tr>"""
        for i, row in enumerate(top_categories, start=1)
    )

    mover_rows = "".join(
        f"""
        <tr>
          <td style="padding:10px 16px;border-bottom:1px solid #edf0f2;color:#24292f;font-size:14px;">
            {row['category_label']}
          </td>
          <td style="padding:10px 16px;border-bottom:1px solid #edf0f2;color:#57606a;font-size:14px;text-align:right;">
            {row['this_week']:,}
          </td>
          <td style="padding:10px 16px;border-bottom:1px solid #edf0f2;color:#57606a;font-size:14px;text-align:right;">
            {row['last_week']:,}
          </td>
          <td style="padding:10px 16px;border-bottom:1px solid #edf0f2;font-size:14px;text-align:right;font-weight:600;color:{change_color(row['change'])};">
            {'+' if row['change'] >= 0 else ''}{row['change']:,}
          </td>
        </tr>"""
        for row in movers
    )

    return f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:640px;margin:0 auto;background-color:#ffffff;">

      <div style="background-color:#0b3d2e;padding:28px 24px;border-radius:8px 8px 0 0;">
        <p style="margin:0;color:#a7f3d0;font-size:13px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;">
          Job Pathway Program
        </p>
        <h1 style="margin:6px 0 0;color:#ffffff;font-size:22px;font-weight:700;">
          Weekly Job Market Snapshot
        </h1>
        <p style="margin:6px 0 0;color:#d1fae5;font-size:13px;">
          Collier County job listings, refreshed daily
        </p>
      </div>

      <div style="padding:24px;border:1px solid #edf0f2;border-top:none;">

        <h2 style="margin:0 0 4px;color:#24292f;font-size:16px;font-weight:700;">
          🏆 Top 10 Categories by Volume
        </h2>
        <p style="margin:0 0 16px;color:#57606a;font-size:13px;">
          New listings in the last 7 days
        </p>
        <table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;margin-bottom:28px;">
          <tr>
            <td style="padding:0 16px 8px;color:#57606a;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;">Category</td>
            <td style="padding:0 16px 8px;color:#57606a;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;text-align:right;">Listings</td>
          </tr>
          {top_rows}
        </table>

        <h2 style="margin:0 0 4px;color:#24292f;font-size:16px;font-weight:700;">
          📈 Biggest Movers
        </h2>
        <p style="margin:0 0 16px;color:#57606a;font-size:13px;">
          Week-over-week change in new listings
        </p>
        <table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;margin-bottom:8px;">
          <tr>
            <td style="padding:0 16px 8px;color:#57606a;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;">Category</td>
            <td style="padding:0 16px 8px;color:#57606a;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;text-align:right;">This Week</td>
            <td style="padding:0 16px 8px;color:#57606a;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;text-align:right;">Last Week</td>
            <td style="padding:0 16px 8px;color:#57606a;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;text-align:right;">Change</td>
          </tr>
          {mover_rows}
        </table>

      </div>

      <div style="padding:16px 24px;border:1px solid #edf0f2;border-top:none;border-radius:0 0 8px 8px;background-color:#f6f8fa;">
        <p style="margin:0;color:#57606a;font-size:12px;line-height:1.5;">
          Job listing data provided by
          <a href="https://www.adzuna.com" style="color:#0b3d2e;font-weight:600;text-decoration:none;">Jobs by Adzuna</a>.
        </p>
      </div>

    </div>
    """


def create_and_send_broadcast(api_key: str, audience_id: str, from_email: str, html: str) -> None:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    resp = requests.post(
        f"{RESEND_BASE}/broadcasts",
        headers=headers,
        json={
            "audience_id": audience_id,
            "from": from_email,
            "subject": "Weekly Job Market Snapshot",
            "html": html,
        },
        timeout=15,
    )
    if not resp.ok:
        print(f"Resend rejected the broadcast request ({resp.status_code}):")
        print(resp.text)
    resp.raise_for_status()
    broadcast_id = resp.json()["id"]
    print(f"Created broadcast draft: {broadcast_id}")

    send_resp = requests.post(f"{RESEND_BASE}/broadcasts/{broadcast_id}/send", headers=headers, json={}, timeout=15)
    if not send_resp.ok:
        print(f"Resend rejected the send request ({send_resp.status_code}):")
        print(send_resp.text)
    send_resp.raise_for_status()
    print("Broadcast sent:", send_resp.json())


def main() -> None:
    supabase_url = os.environ["SUPABASE_URL"]
    publishable_key = os.environ["SUPABASE_PUBLISHABLE_KEY"]
    resend_api_key = os.environ["RESEND_API_KEY"]
    audience_id = os.environ["RESEND_AUDIENCE_ID"]
    from_email = os.environ["RESEND_FROM_EMAIL"]

    print("Fetching top categories...")
    top_categories = _rpc(supabase_url, publishable_key, "top_categories_this_week")

    print("Fetching biggest movers...")
    movers = _rpc(supabase_url, publishable_key, "biggest_movers")

    html = build_html(top_categories, movers)

    print("Creating and sending broadcast...")
    create_and_send_broadcast(resend_api_key, audience_id, from_email, html)


if __name__ == "__main__":
    main()
