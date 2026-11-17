"""
Full-stack browser test: real Chromium -> built frontend (vite preview + /api proxy) -> real backend -> database.
Plays buyer, seller, arbiter and admin through the complete flows.

    pip install playwright && playwright install chromium
    python e2e/e2e_browser.py                 # dev-style: SQLite + vite preview
    E2E_PROD=1 CADDY=/path/to/caddy python e2e/e2e_browser.py
                                              # production-style: PostgreSQL + ENVIRONMENT=production + the real Caddyfile
"""
import os, pathlib, re, subprocess, sys, tempfile, time, urllib.request

from playwright.sync_api import expect, sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHOTS = pathlib.Path(os.environ.get("E2E_SHOTS", tempfile.mkdtemp(prefix="e2e_")))
DB = SHOTS / "e2e.db"
PROD = os.environ.get("E2E_PROD") == "1"
API_PORT, WEB_PORT = 8765, (8080 if PROD else 4173)
WEB = f"http://localhost:{WEB_PORT}"
ENV = dict(os.environ, DATABASE_URL=f"sqlite:///{DB}", VITE_PROXY_TARGET=f"http://localhost:{API_PORT}", AUTO_RELEASE_INTERVAL_SECONDS="2")
procs, cleanups = [], []


def wait(url, tries=60):
    for _ in range(tries):
        try:
            urllib.request.urlopen(url, timeout=1); return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"{url} never came up")


def start():
    global ENV
    if PROD:
        import pgserver, secrets
        pg = pgserver.get_server(SHOTS / "pg", cleanup_mode="stop"); cleanups.append(pg.cleanup)
        # the plain postgresql:// form, exactly as a hosting provider would hand it out
        ENV = dict(os.environ, DATABASE_URL=pg.get_uri(), ENVIRONMENT="production", JWT_SECRET=secrets.token_hex(32),
                   AUTO_RELEASE_INTERVAL_SECONDS="2")
    procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(API_PORT), "--log-level", "warning"],
                                  cwd=ROOT / "backend", env=ENV))
    wait(f"http://localhost:{API_PORT}/health")
    if PROD:
        caddy_env = dict(ENV, SITE_ADDRESS=f":{WEB_PORT}", BACKEND_ADDRESS=f"localhost:{API_PORT}")
        procs.append(subprocess.Popen([os.environ["CADDY"], "run", "--config", str(ROOT / "frontend" / "Caddyfile"), "--adapter", "caddyfile"],
                                      env=caddy_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        wait(f"{WEB}/api/health"); return
    procs.append(subprocess.Popen(["npx", "vite", "preview", "--port", str(WEB_PORT), "--strictPort"], cwd=ROOT / "frontend", env=ENV,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    wait(f"{WEB}/api/health")          # proves the proxy works too


def cli(*args):
    subprocess.run([sys.executable, "-m", "app.cli", *args], cwd=ROOT / "backend", env=ENV, check=True, stdout=subprocess.DEVNULL)


def backdate_auto_release(title):
    """Pretend the buyer's response window has already passed for the deal with this title."""
    code = (
        "from datetime import datetime, timedelta, timezone\n"
        "from sqlalchemy import select\n"
        "from app import models\n"
        "from app.database import SessionLocal\n"
        "with SessionLocal() as db:\n"
        f"    t = db.execute(select(models.Transaction).where(models.Transaction.title == {title!r})).scalar_one()\n"
        "    t.auto_release_at = datetime.now(timezone.utc) - timedelta(hours=1)\n"
        "    db.commit()\n")
    subprocess.run([sys.executable, "-c", code], cwd=ROOT / "backend", env=ENV, check=True)


def person(browser, name):
    ctx = browser.new_context(viewport={"width": 1200, "height": 800})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    # real JS errors fail the test; the 401/404 network lines are responses this test provokes on purpose
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and not re.search(r"status of (401|404)", m.text) else None)
    page.on("dialog", lambda d: d.accept("Checked and approved by staff") if d.type == "prompt" else d.accept())
    page.errors = errors
    return page


def register(page, name, email):
    page.goto(f"{WEB}/register")
    page.get_by_label("Full name").fill(name)
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill("correct-horse-1")
    page.get_by_role("button", name="Sign up").click()


def shot(page, name):
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def deal_through(buyer, seller, title, amount, upto):
    """Buyer proposes; walks the deal as far as `upto` ('draft','accepted','funded','delivered')."""
    buyer.get_by_role("link", name="New transaction").first.click()
    buyer.get_by_label("Title").fill(title)
    buyer.get_by_label("Amount").fill(amount)
    buyer.get_by_label(re.compile("Seller's email")).fill("sam@example.com")
    buyer.get_by_role("button", name="Send to counterparty").click()
    expect(buyer.get_by_role("heading", name=re.compile(title))).to_be_visible()
    url = buyer.url
    steps = ["draft", "accepted", "funded", "delivered"]
    if steps.index(upto) >= 1:
        seller.goto(url); seller.get_by_role("button", name="Accept").click()
        expect(seller.get_by_text("Awaiting payment")).to_be_visible()
    if steps.index(upto) >= 2:
        buyer.reload(); buyer.get_by_role("button", name=re.compile("into escrow")).click()
        expect(buyer.get_by_text("Waiting for Sam Seller to deliver")).to_be_visible()
    if steps.index(upto) >= 3:
        seller.reload(); seller.get_by_label(re.compile("Delivery note")).fill("Files: https://files.example/logo.zip")
        seller.get_by_role("button", name="Mark as delivered").click()
        expect(seller.get_by_text("Waiting for Bea Buyer to approve")).to_be_visible()
        buyer.reload()
    return url


def main():
    start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            bea, sam, arlo, ada = (person(browser, n) for n in ("bea", "sam", "arlo", "ada"))

            # ---------- sign-up ----------
            register(bea, "Bea Buyer", "bea@example.com"); expect(bea.get_by_role("heading", name="My transactions")).to_be_visible()
            register(sam, "Sam Seller", "sam@example.com"); expect(sam.get_by_role("heading", name="My transactions")).to_be_visible()
            expect(bea.get_by_text("You don't have any transactions yet.")).to_be_visible()
            shot(bea, "01_dashboard_empty")

            # ---------- happy path ----------
            url = deal_through(bea, sam, "Logo design", "100.00", "delivered")
            shot(bea, "02_deal_delivered_buyer_view")
            expect(bea.get_by_text("$102.50").first).to_be_visible()                       # 100.00 + 2.5% fee
            bea.get_by_role("button", name=re.compile("Approve & release")).click()
            expect(bea.get_by_text("Funds have been released to the seller.", exact=False)).to_be_visible()
            expect(bea.get_by_text("Seller's balance")).to_be_visible()
            expect(bea.get_by_text("Platform fee").first).to_be_visible()
            shot(bea, "03_deal_released_with_ledger")
            sam.goto(url); expect(sam.get_by_text("Released").first).to_be_visible()
            print("✓ happy path: register -> create -> accept -> fund -> deliver -> approve -> ledger")

            # ---------- permissions in the real UI ----------
            bea.goto(f"{WEB}/transactions/does-not-exist"); expect(bea.get_by_text("Transaction not found")).to_be_visible()
            bea.goto(f"{WEB}/admin"); expect(bea.get_by_role("heading", name="My transactions")).to_be_visible()   # bounced home
            print("✓ unknown deal -> 404 message; user bounced from /admin")

            # ---------- dispute -> arbiter refunds ----------
            bea.goto(WEB)
            url2 = deal_through(bea, sam, "Website copy", "250.00", "delivered")
            bea.get_by_role("button", name="Open a dispute").click()
            bea.get_by_label(re.compile("What went wrong")).fill("Copy was plagiarised and unusable")
            bea.get_by_role("button", name="Submit dispute").click()
            expect(bea.get_by_text("Why it was opened")).to_be_visible()
            bea.get_by_label("Add a note").fill("See attached comparison"); bea.get_by_role("button", name="Add evidence").click()
            expect(bea.get_by_text("See attached comparison")).to_be_visible()
            bea.get_by_label("Message").fill("Please refund me"); bea.get_by_role("button", name="Send").click()
            expect(bea.get_by_text("Please refund me")).to_be_visible()
            sam.goto(url2); expect(sam.get_by_text("in dispute", exact=False).first).to_be_visible()
            sam.get_by_role("link", name=re.compile("Open the dispute")).click()
            sam.get_by_label("Message").fill("I wrote it myself"); sam.get_by_role("button", name="Send").click()
            expect(sam.get_by_text("I wrote it myself")).to_be_visible()
            shot(sam, "04_dispute_seller_view")

            register(arlo, "Arlo Arbiter", "arlo@example.com"); expect(arlo.get_by_role("heading", name="My transactions")).to_be_visible()
            cli("set-role", "arlo@example.com", "arbiter")
            arlo.goto(WEB)
            expect(arlo.get_by_role("heading", name="Disputes")).to_be_visible()           # arbiters land on the queue
            expect(arlo.get_by_text("Website copy")).to_be_visible()
            shot(arlo, "05_arbiter_queue")
            arlo.get_by_role("link", name="Review ›").click()
            expect(arlo.get_by_text("I wrote it myself")).to_be_visible()
            arlo.get_by_label(re.compile(r"Reason \(required")).fill("Comparison shows the copy was lifted")
            shot(arlo, "06_arbiter_decision")
            arlo.get_by_role("button", name="Submit decision").click()                      # default choice: refund buyer
            expect(arlo.get_by_text("Refunded to the buyer")).to_be_visible()
            bea.goto(url2); expect(bea.get_by_text("The buyer was refunded in full.")).to_be_visible()
            print("✓ dispute: open -> evidence -> messages -> arbiter queue -> refund decision")

            # ---------- split decision ----------
            bea.goto(WEB)
            url3 = deal_through(bea, sam, "Logo v2", "100.00", "delivered")
            bea.get_by_role("button", name="Open a dispute").click()
            bea.get_by_label(re.compile("What went wrong")).fill("Only half the files were delivered")
            bea.get_by_role("button", name="Submit dispute").click(); expect(bea.get_by_text("Why it was opened")).to_be_visible()
            arlo.goto(f"{WEB}/staff/disputes"); arlo.get_by_role("link", name="Review ›").click()
            arlo.get_by_label(re.compile("Split the item price")).check()
            arlo.get_by_label(re.compile("Seller keeps")).fill("40.00")
            arlo.get_by_label(re.compile(r"Reason \(required")).fill("Half delivered, so 40/60")
            arlo.get_by_role("button", name="Submit decision").click()
            expect(arlo.get_by_text("Split between both")).to_be_visible()
            expect(arlo.get_by_text("Seller kept $40.00", exact=False)).to_be_visible()
            print("✓ split decision: $40.00 / $60.00")

            # ---------- auto-release by the background job ----------
            bea.goto(WEB)
            url4 = deal_through(bea, sam, "Auto deal", "80.00", "delivered")
            backdate_auto_release("Auto deal")                       # the buyer 'went silent'
            for _ in range(20):                                      # the server's job runs every 2s in this test
                bea.goto(url4)
                if bea.get_by_text("Funds have been released to the seller.", exact=False).count():
                    break
                time.sleep(1)
            expect(bea.get_by_text("Funds have been released to the seller.", exact=False)).to_be_visible()
            print("✓ auto-release: overdue deal paid out by the background job, with nobody clicking anything")

            # ---------- admin ----------
            register(ada, "Ada Admin", "ada@example.com"); cli("set-role", "ada@example.com", "admin")
            ada.goto(WEB); expect(ada.get_by_role("heading", name="Platform overview")).to_be_visible()
            expect(ada.get_by_text("Released volume")).to_be_visible()
            shot(ada, "07_admin_overview")
            ada.get_by_role("link", name="Users", exact=True).click()
            row = ada.get_by_role("row").filter(has_text="bea@example.com")
            row.get_by_role("button", name="Verify KYC").click()
            expect(ada.get_by_text("Updated bea@example.com.")).to_be_visible()
            expect(ada.get_by_role("row").filter(has_text="bea@example.com").get_by_text("verified")).to_be_visible()
            shot(ada, "08_admin_users")
            ada.get_by_role("row").filter(has_text="sam@example.com").get_by_role("button", name="Freeze").click()
            expect(ada.get_by_role("row").filter(has_text="sam@example.com").get_by_text("Frozen")).to_be_visible()
            sam.reload()                                                                     # frozen user is thrown out immediately
            expect(sam.get_by_role("heading", name="Log in")).to_be_visible()
            ada.get_by_role("row").filter(has_text="sam@example.com").get_by_role("button", name="Unfreeze").click()
            expect(ada.get_by_role("row").filter(has_text="sam@example.com").get_by_text("Active")).to_be_visible()
            ada.get_by_role("link", name="Transactions", exact=True).click(); expect(ada.get_by_text("Logo design")).to_be_visible()
            print("✓ admin: overview, verify KYC, freeze (user ejected at once), unfreeze, all transactions")

            # ---------- login / logout ----------
            sam.goto(f"{WEB}/login")
            sam.get_by_label("Email").fill("sam@example.com"); sam.get_by_label("Password").fill("wrong-password")
            sam.get_by_role("button", name="Log in").click(); expect(sam.get_by_role("alert")).to_have_text("Invalid email or password")
            sam.get_by_label("Password").fill("correct-horse-1"); sam.get_by_role("button", name="Log in").click()
            expect(sam.get_by_role("button", name="Log out")).to_be_visible()
            assert "/transactions/" in sam.url, sam.url        # session had expired mid-task: logging in returns you to that task
            sam.get_by_role("button", name="Log out").click(); expect(sam.get_by_role("heading", name="Log in")).to_be_visible()
            sam.get_by_label("Email").fill("sam@example.com"); sam.get_by_label("Password").fill("correct-horse-1")
            sam.get_by_role("button", name="Log in").click()
            expect(sam.get_by_role("heading", name="My transactions")).to_be_visible()   # deliberate logout: next login starts at the dashboard
            print("✓ wrong password rejected, login, logout")

            for who, page in (("bea", bea), ("sam", sam), ("arlo", arlo), ("ada", ada)):
                assert not page.errors, f"browser console errors for {who}: {page.errors}"
            print("✓ no JavaScript errors in any browser")
            browser.close()
        print(f"\nALL END-TO-END CHECKS PASSED   (screenshots: {SHOTS})")
    finally:
        for pr in procs:
            pr.terminate()
        for c in cleanups:
            c()


if __name__ == "__main__":
    main()
