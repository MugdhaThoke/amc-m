import { chromium } from "playwright";

async function runBrowserTest() {
  console.log("1. Creating high-confidence test patch via API...");
  const uniqueAttr = "nav_audit_" + Date.now().toString().slice(-4);
  const createResp = await fetch("http://localhost:8002/api/patches", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      entity_id: "NIPPON_INDIA_GROWTH",
      attribute: uniqueAttr,
      canonical_value: "105.20",
      corrected_value: "105.75",
      confidence: 0.98,
      approved: false,
      provenance: { source: "Annual Report Audit" }
    }),
  });
  console.log("2. Authenticating as Compliance Officer via backend /api/auth/login...");
  const loginResp = await fetch("http://localhost:8000/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: "amc_admin",
      password: "Compliance@2026",
      remember_me: true,
    }),
  });
  const loginData = await loginResp.json();
  if (!loginData.token) {
    throw new Error(`Login failed: ${JSON.stringify(loginData)}`);
  }
  console.log("   Authenticated successfully. User:", loginData.user.username);

  console.log("3. Launching headless Edge browser...");
  const browser = await chromium.launch({ headless: true, channel: "msedge" });
  const context = await browser.newContext();

  await context.addInitScript(
    ({ token, expiresAt, user }) => {
      const sessionData = {
        isAuthenticated: true,
        authedUsername: user.username,
        token: token,
        expiresAt: expiresAt,
        rememberMe: true,
      };
      localStorage.setItem("ns_cg_auth_session_v1", JSON.stringify(sessionData));
      sessionStorage.setItem("ns_cg_auth_session_v1", JSON.stringify(sessionData));
      localStorage.setItem("ns_cg_active_user_v1", JSON.stringify(user.username));
      localStorage.setItem("ns_cg_active_page_v1", JSON.stringify("06_Governance"));
    },
    { token: loginData.token, expiresAt: loginData.expires_at, user: loginData.user }
  );

  const page = await context.newPage();
  page.on("console", (msg) => console.log("BROWSER LOG:", msg.text()));
  page.on("pageerror", (err) => console.log("BROWSER ERROR:", err.message));
  page.on("request", (req) => console.log("NETWORK REQ:", req.method(), req.url()));
  page.on("response", (res) => console.log("NETWORK RES:", res.status(), res.url()));
  page.on("dialog", (dialog) => {
    console.log("BROWSER DIALOG:", dialog.message());
    dialog.accept();
  });

  console.log("4. Navigating to http://localhost:5173/ ...");
  await page.goto("http://localhost:5173/", { waitUntil: "networkidle" });

  console.log("4. Verifying Governance Page rendering...");
  await page.waitForSelector("text=Governance Review Queue", { timeout: 10000 });
  console.log("   [PASS] Found 'Governance Review Queue' title");

  // Verify KPI Card
  const autoKpi = await page.waitForSelector("text=Auto-Approve Eligible", { timeout: 10000 });
  console.log("   [PASS] Found 'Auto-Approve Eligible' KPI card");

  // Verify Hands-Free Policy Bar
  const policyBar = await page.waitForSelector("text=100% Hands-Free Auto-Approval:", { timeout: 10000 });
  console.log("   [PASS] Found '100% Hands-Free Auto-Approval' policy banner");

  // Verify Auto-Approve Batch Button
  const autoBatchBtn = await page.waitForSelector("button:has-text('Run Auto-Approve Batch')", { timeout: 10000 });
  console.log("   [PASS] Found 'Run Auto-Approve Batch' button");

  await page.screenshot({ path: "governance_before_auto_batch.png", fullPage: true });
  console.log("   [PASS] Captured screenshot: governance_before_auto_batch.png");

  // Click the Auto-Approve Batch Button
  console.log("5. Clicking 'Run Auto-Approve Batch' button...");
  await autoBatchBtn.click();

  // Wait for success alert
  console.log("6. Awaiting auto-approval batch completion alert...");
  await page.waitForSelector("text=Hands-Free Auto-Approval Batch completed", { timeout: 15000 });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: "governance_after_auto_batch.png", fullPage: true });
  console.log("   [PASS] Captured screenshot: governance_after_auto_batch.png");

  await browser.close();
  console.log("All browser tests passed successfully!");
}

runBrowserTest().catch((err) => {
  console.error("Browser test failed:", err);
  process.exit(1);
});
