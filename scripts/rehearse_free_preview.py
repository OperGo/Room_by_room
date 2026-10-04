"""Sprint 2B: rehearse the free-preview configuration end to end, locally.

Run the app exactly as the free Render web service will (production settings, PostgreSQL, database storage,
`python manage.py migrate --noinput && gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers 1 --timeout 120`),
create the owner with `create_owner`, then run this script. It stands in for Render's proxy: a small local
TLS terminator adds `X-Forwarded-Proto: https` (as Render does) in front of Gunicorn, and Chromium drives the
phone flow through it.

    PREVIEW_OWNER_PW=... PREVIEW_INTRUDER_PW=... python scripts/rehearse_free_preview.py \
        --app http://127.0.0.1:10000 --username alistair --intruder intruder

Passwords come from the environment, never from arguments. No paid calls are made.
"""

import argparse
import http.client
import io
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots" / "sprint2b-preview"
HOP_BY_HOP = {"connection", "keep-alive", "proxy-connection", "transfer-encoding", "upgrade", "te", "trailer"}
RESULTS = []
REVIEW_URL = re.compile(r"/receipts/[0-9a-f-]{36}/$")  # not /receipts/new/


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{' — ' + detail if detail else ''}")
    if not ok:
        raise SystemExit(f"Check failed: {name}")


def start_tls_proxy(app_url, port):
    """HTTPS on localhost:port → plain HTTP app, adding X-Forwarded-Proto like Render's edge."""
    target = urlparse(app_url)
    certdir = tempfile.mkdtemp()
    cert, key = f"{certdir}/c.pem", f"{certdir}/k.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj",
                    "/CN=localhost", "-keyout", key, "-out", cert], check=True, capture_output=True)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _forward(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
            headers["X-Forwarded-Proto"] = "https"
            headers["X-Forwarded-For"] = self.client_address[0]
            upstream = http.client.HTTPConnection(target.hostname, target.port, timeout=120)
            upstream.request(self.command, self.path, body=body, headers=headers)
            response = upstream.getresponse()
            data = response.read()
            self.send_response(response.status, response.reason)
            for k, v in response.getheaders():
                if k.lower() not in HOP_BY_HOP and k.lower() != "content-length":
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
            upstream.close()

        do_GET = do_POST = do_HEAD = _forward

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"https://localhost:{port}"


def synthetic_image(text_colour, size=(600, 900)):
    """A plain synthetic image (no real receipt or photo)."""
    image = Image.new("RGB", size, "white")
    for x in range(40, size[0] - 40):
        for y in range(80, 90):
            image.putpixel((x, y), text_colour)
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    path = Path(tempfile.mkdtemp()) / "synthetic.jpg"
    path.write_bytes(buf.getvalue())
    return path


def plain_get(app_url, path, headers=None):
    target = urlparse(app_url)
    conn = http.client.HTTPConnection(target.hostname, target.port, timeout=30)
    conn.request("GET", path, headers={"Host": "localhost", **(headers or {})})
    response = conn.getresponse()
    return response.status, dict(response.getheaders()), response.read()


def sign_in(page, base, username, password):
    page.goto(f"{base}/account/sign-in/")
    page.fill("#id_username", username)
    page.fill("#id_password", password)
    page.click("button[type=submit]")
    page.wait_for_url(f"{base}/")


def shot(page, name):
    page.wait_for_load_state("networkidle")
    page.screenshot(path=OUT / f"{name}.png", full_page=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", default="http://127.0.0.1:10000")
    parser.add_argument("--proxy-port", type=int, default=10443)
    parser.add_argument("--username", default="alistair")
    parser.add_argument("--intruder", default="intruder")
    args = parser.parse_args()
    owner_pw, intruder_pw = os.environ["PREVIEW_OWNER_PW"], os.environ["PREVIEW_INTRUDER_PW"]
    OUT.mkdir(parents=True, exist_ok=True)

    # Platform-level checks straight against Gunicorn (as Render's internal health check sees it).
    status, _, body = plain_get(args.app, "/healthz/")
    check("health check /healthz/ over plain HTTP", status == 200 and json.loads(body) == {"status": "ok"}, f"{status} {body.decode()}")
    status, headers, _ = plain_get(args.app, "/")
    check("plain HTTP is redirected to HTTPS", status == 301 and headers.get("Location", "").startswith("https://"),
          f"{status} → {headers.get('Location')}")

    base = start_tls_proxy(args.app, args.proxy_port)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        phone = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                                    has_touch=True, ignore_https_errors=True)
        page = phone.new_page()

        response = page.goto(f"{base}/")
        check("anonymous visitor is sent to sign-in", "/account/sign-in/" in page.url, page.url)
        sign_in_response = page.goto(f"{base}/account/sign-in/")
        check("HSTS header on HTTPS responses", "strict-transport-security" in sign_in_response.headers,
              sign_in_response.headers.get("strict-transport-security", ""))
        css = page.locator("link[rel=stylesheet][href*='/static/']").first.get_attribute("href")
        css_response = page.request.get(f"{base}{css}")
        check("static CSS served by WhiteNoise with a hashed name",
              css_response.status == 200 and re.search(r"\.[0-9a-f]{12}\.css$", css) is not None,
              f"{css} {css_response.status} cache-control={css_response.headers.get('cache-control')}")
        shot(page, "p1-sign-in-390")

        sign_in(page, base, args.username, owner_pw)
        cookies = {c["name"]: c for c in phone.cookies()}
        check("session cookie is Secure and HttpOnly",
              cookies["sessionid"]["secure"] and cookies["sessionid"]["httpOnly"])
        shot(page, "p2-empty-owner-home-390")

        # The owner account starts empty: create a project to allocate to.
        page.goto(f"{base}/projects/new/")
        page.fill("#id_title", "Preview kitchen")
        page.fill("#id_room", "Kitchen")
        page.fill("#id_budget", "500")
        page.get_by_role("button", name="Create project").click()
        expect(page.locator("h1")).to_have_text("Preview kitchen")
        project_url = page.url
        project_uuid = project_url.rstrip("/").split("/")[-1]

        # Project photo → private database storage.
        page.goto(f"{base}/projects/{project_uuid}/photos/new/")
        page.set_input_files("#id_photo", str(synthetic_image((40, 120, 60), size=(800, 600))))
        page.get_by_role("button", name="Upload").click()
        page.wait_for_url(f"{project_url}?tab=photos")
        photo_src = page.locator("img[src*='/photos/']").first.get_attribute("src")
        photo_response = page.request.get(f"{base}{photo_src}")
        check("owner can open the private project photo", photo_response.status == 200
              and photo_response.headers.get("content-type", "").startswith("image/"),
              f"{photo_src} {photo_response.status}")

        # Receipt: upload, missing-key message, manual entry, reconciliation, confirm.
        page.goto(f"{base}/receipts/new/")
        page.set_input_files("input[aria-label='Upload a receipt image']", str(synthetic_image((10, 10, 10))))
        page.wait_for_url(REVIEW_URL)
        review_url = page.url
        notes = page.get_by_text("Automatic extraction not configured").all_inner_texts()
        read_buttons = page.get_by_role("button", name="Read receipt automatically").count()
        check("missing API key: automatic reading is reported as not configured",
              len(notes) >= 1 and read_buttons == 0, f"{notes} read buttons={read_buttons}")
        receipt_href = page.locator("a[href*='/receipts/file/']").first.get_attribute("href")
        receipt_response = page.request.get(f"{base}{receipt_href}")
        check("owner can open the private receipt file", receipt_response.status == 200, f"{receipt_href}")
        shot(page, "p3-receipt-not-configured-390")

        page.fill("#f-merchant", "Preview Hardware (synthetic)")
        page.fill("#f-date", "2026-10-03")
        page.fill("#f-total", "13.00")
        page.fill("#l0-desc", "Wood filler")
        page.fill("#l0-amt", "10.00")
        page.select_option("#l0-a0-dest", f"project:{project_uuid}")
        page.get_by_role("button", name="Add item", exact=True).click()
        page.fill("#l1-desc", "Sandpaper")
        page.fill("#l1-amt", "2.50")
        page.select_option("#l1-a0-dest", f"project:{project_uuid}")
        status_text = page.locator("[data-reconcile-status]").inner_text()
        check("reconciliation flags a mismatch before confirming", "not itemised" in status_text, status_text)
        shot(page, "p4-reconcile-mismatch-390")
        page.get_by_role("button", name="Confirm purchase").click()
        page.locator("#editor-errors").wait_for()
        check("server refuses an unreconciled purchase and keeps the entries",
              "/costs/purchases/" not in page.url and page.locator("#f-merchant").input_value() == "Preview Hardware (synthetic)",
              page.locator("#editor-errors").inner_text().replace("\n", " "))
        page.fill("#f-total", "12.50")
        status_text = page.locator("[data-reconcile-status]").inner_text()
        check("reconciliation matches after correction", page.locator("[data-reconcile].good").count() == 1, status_text)

        form_data = page.evaluate("""() => {
            const form = document.querySelector('form[data-editor-form]');
            return {action: form.action, fields: [...new FormData(form).entries()].filter(([k, v]) => typeof v === 'string')};
        }""")
        page.get_by_role("button", name="Confirm purchase").click()
        page.wait_for_url(re.compile(r"/costs/purchases/[0-9a-f-]{36}/$"))
        purchase_url = page.url
        check("manual receipt confirmed into a purchase", page.get_by_text("£12.50").count() >= 1, purchase_url)
        shot(page, "p5-purchase-confirmed-390")

        # Repeat confirmation (double tap / resubmit) must not post twice.
        replay = page.request.post(form_data["action"], form={k: v for k, v in form_data["fields"]},
                                   headers={"Referer": review_url, "Origin": base})
        check("repeat confirmation returns the same purchase", replay.url.rstrip("/") == purchase_url.rstrip("/"),
              replay.url)
        page.goto(f"{base}/costs/")
        costs_text = page.locator("main").inner_text()
        check("cost totals count the purchase once",
              "Total recorded\n£12.50" in costs_text and "Preview kitchen\t£12.50\t£487.50" in costs_text,
              "total £12.50; Preview kitchen £12.50 of £500 budget")
        shot(page, "p6-costs-once-390")

        # Layout on an iPhone-density phone (DPR 3): no page may scroll sideways.
        dense = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True,
                                    has_touch=True, ignore_https_errors=True)
        dense_page = dense.new_page()
        sign_in(dense_page, base, args.username, owner_pw)
        purchase_path = urlparse(purchase_url).path
        paths = ["/", "/projects/", "/projects/new/", f"/projects/{project_uuid}/", f"/projects/{project_uuid}/edit/",
                 f"/projects/{project_uuid}/tasks/new/", f"/projects/{project_uuid}/opening-balance/new/",
                 "/shopping/", "/shopping/new/", "/costs/", "/costs/purchases/new/", purchase_path,
                 f"{purchase_path}refund/", f"{purchase_path}correct/", f"{purchase_path}void/", "/receipts/new/"]
        wide = []
        for path in paths:
            dense_page.goto(f"{base}{path}")
            width = dense_page.evaluate("document.documentElement.scrollWidth")
            if width > 390:
                wide.append(f"{path} ({width}px)")
        dense_page.goto(f"{base}/receipts/new/")
        dense_page.set_input_files("input[aria-label='Upload a receipt image']", str(synthetic_image((90, 10, 10))))
        dense_page.wait_for_url(REVIEW_URL)
        paths.append("receipt review (second synthetic upload)")
        width = dense_page.evaluate("document.documentElement.scrollWidth")
        if width > 390:
            wide.append(f"receipt review ({width}px)")
        check(f"no sideways scrolling at 390 px, DPR 3 ({len(paths)} pages)", not wide, ", ".join(wide))
        dense_page.goto(f"{base}/projects/new/")
        shot(dense_page, "p7-new-project-dpr3-390")
        dense.close()

        # Private files: anonymous and another owner are refused.
        anonymous = browser.new_context(ignore_https_errors=True)
        for label, url in (("receipt", receipt_href), ("photo", photo_src)):
            r = anonymous.request.get(f"{base}{url}", max_redirects=0)
            check(f"anonymous request for the {label} is redirected to sign-in",
                  r.status == 302 and "/account/sign-in/" in r.headers.get("location", ""), str(r.status))
        intruder = browser.new_context(ignore_https_errors=True)
        intruder_page = intruder.new_page()
        sign_in(intruder_page, base, args.intruder, intruder_pw)
        for label, url in (("receipt", receipt_href), ("photo", photo_src), ("purchase", urlparse(purchase_url).path)):
            r = intruder.request.get(f"{base}{url}")
            check(f"another account gets 404 for the {label}", r.status == 404, str(r.status))
        browser.close()
    print(f"\n{sum(ok for _, ok, _ in RESULTS)} of {len(RESULTS)} checks passed.")


if __name__ == "__main__":
    sys.exit(main())
