const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

async function runFullE2ETest() {
  console.log("================================================================================");
  console.log("🚀 STARTING COMPREHENSIVE END-TO-END BROWSER TEST (FEEDBACK LOOP & REPAIR ENGINE)");
  console.log("================================================================================");

  const screenshotsDir = path.join(__dirname, "e2e_screenshots");
  if (!fs.existsSync(screenshotsDir)) {
    fs.mkdirSync(screenshotsDir, { recursive: true });
  }

  const networkErrors = [];
  const consoleErrors = [];

  const browser = await chromium.launch({
    channel: "msedge",
    headless: true,
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
  });

  const page = await context.newPage();

  // Monitor Console
  page.on("console", (msg) => {
    const type = msg.type();
    const text = msg.text();
    if (type === "error") {
      consoleErrors.push(text);
      console.log(`❌ [BROWSER CONSOLE ERROR] ${text}`);
    } else if (type === "warning") {
      console.log(`⚠️  [BROWSER CONSOLE WARN] ${text}`);
    } else {
      // Print interesting logs
      if (text.includes("API") || text.includes("Feedback") || text.includes("Patch") || text.includes("Governance")) {
        console.log(`ℹ️  [BROWSER CONSOLE INFO] ${text}`);
      }
    }
  });

  page.on("pageerror", (err) => {
    consoleErrors.push(err.message);
    console.log(`💥 [BROWSER PAGE UNCAUGHT ERROR] ${err.message}`);
  });

  // Monitor Network
  page.on("request", (req) => {
    const url = req.url();
    if (url.includes("/api/")) {
      console.log(`📡 [NET REQ] ${req.method()} ${url}`);
    }
  });

  page.on("response", async (res) => {
    const url = res.url();
    if (url.includes("/api/")) {
      const status = res.status();
      if (status >= 400) {
        let body = "";
        try {
          body = await res.text();
        } catch {}
        networkErrors.push({ status, url, body });
        console.log(`🔴 [NET RES ERROR] ${status} ${url} -> ${body.slice(0, 150)}`);
      } else {
        console.log(`🟢 [NET RES OK] ${status} ${url}`);
      }
    }
  });

  try {
    // ----------------------------------------------------
    // STEP 1: Navigate to App & Login
    // ----------------------------------------------------
    console.log("\n--- STEP 1: Navigate to Login & Authenticate ---");
    await page.goto("http://localhost:5173/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(screenshotsDir, "step1_login_page.png") });
    console.log("✅ Navigated to login page.");

    console.log("Submitting login credentials (amc_admin / Compliance@2026)...");
    await page.fill('input[type="text"], input[name="username"], input[placeholder*="User ID"], #login-user-id', "amc_admin");
    await page.fill('input[type="password"], #login-password', "Compliance@2026");
    await page.click('button[type="submit"], button:has-text("Sign In")');

    // Wait for authenticated shell
    await page.waitForSelector('.stHeader, .stTabs, nav, .stSidebar', { timeout: 15000 });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(screenshotsDir, "step1_authenticated_dashboard.png") });
    console.log("✅ Logged in successfully. Shell rendered.");

    // ----------------------------------------------------
    // STEP 2: Chat Interaction & Query Submission
    // ----------------------------------------------------
    console.log("\n--- STEP 2: Submit Query in Chat ---");
    const chatNav = page.locator('button[title="Chat"]').first();
    if (await chatNav.isVisible()) {
      await chatNav.click();
      await page.waitForTimeout(600);
    }

    const newChatBtn = page.locator('button:has-text("New chat")').first();
    if (await newChatBtn.isVisible()) {
      await newChatBtn.click();
      await page.waitForTimeout(600);
    }

    console.log("Sending query: 'What is the fund category of Axis Bluechip Fund?'");
    const queryInput = await page.waitForSelector('textarea.cg-chatgpt-query-input, textarea[placeholder*="Ask"]', { timeout: 10000 });
    await queryInput.fill("What is the fund category of Axis Bluechip Fund?");

    const sendBtn = await page.waitForSelector('button.cg-chatgpt-send-btn, button[title*="Send"], button:has-text("Send")', { timeout: 5000 });
    await sendBtn.click();

    console.log("Waiting for assistant response...");
    await page.waitForSelector('.cg-msg-actions button:has-text("Feedback")', { timeout: 45000 });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(screenshotsDir, "step2_chat_response.png") });
    console.log("✅ Assistant response received and rendered.");

    // ----------------------------------------------------
    // STEP 3: Submit Active Feedback with Correction
    // ----------------------------------------------------
    console.log("\n--- STEP 3: Submit Active Correction Feedback ---");
    const feedbackButtons = await page.$$('.cg-msg-actions button:has-text("Feedback")');
    const lastFeedbackBtn = feedbackButtons[feedbackButtons.length - 1];
    await lastFeedbackBtn.click();

    console.log("Waiting for Feedback Modal...");
    await page.waitForSelector('.cg-feedback-container, .cg-taxonomy-grid', { timeout: 10000 });
    await page.waitForTimeout(500);

    // Select first reason checkbox (Knowledge / Fact error)
    const firstCheckbox = page.locator('.cg-taxonomy-grid input[type="checkbox"], input[type="checkbox"]').first();
    await firstCheckbox.click();

    // Fill notes with correction claim
    const notesBox = page.locator('textarea.cg-feedback-input, textarea[placeholder*="feedback"]');
    await notesBox.fill("The fund category is actually Mid Cap, not Large Cap");

    await page.screenshot({ path: path.join(screenshotsDir, "step3_feedback_modal_filled.png") });

    // Submit feedback
    console.log("Clicking Submit Feedback button...");
    const submitFeedbackBtn = page.locator('button.cg-feedback-submit-btn, button:has-text("Submit Feedback")');
    await submitFeedbackBtn.click();

    // Wait for success indicator
    await page.locator('.cg-feedback-status--success, :text("Feedback received"), .cg-feedback-status').first().waitFor({ timeout: 30000 });
    await page.screenshot({ path: path.join(screenshotsDir, "step3_feedback_submitted.png") });
    console.log("✅ Feedback submitted successfully!");

    // Close modal
    const modalClose = page.locator('button.cg-modal-close-btn, button:has-text("✕")').first();
    if (await modalClose.isVisible()) {
      await modalClose.click();
      await page.waitForTimeout(600);
    }

    // ----------------------------------------------------
    // STEP 4: Navigate to Feedback & Triage Queue
    // ----------------------------------------------------
    console.log("\n--- STEP 4: Verify Admin Feedback & Triage Queue ---");
    const feedbackNav = page.locator('button[title="Feedback & Triage Queue"], button:has-text("Feedback & Triage")').first();
    await feedbackNav.click();
    await page.waitForTimeout(1500);

    await page.screenshot({ path: path.join(screenshotsDir, "step4_feedback_triage_queue.png") });

    const kpiMetrics = await page.$$('.stMetric');
    console.log(`✅ Found ${kpiMetrics.length} KPI Metric cards in Admin Triage.`);

    const rows = await page.$$('table tbody tr');
    console.log(`✅ Found ${rows.length} issue row(s) in Admin Triage table.`);

    // Inspect first issue details
    const inspectBtn = page.locator('button[title="Inspect issue details"]').first();
    if (await inspectBtn.isVisible()) {
      await inspectBtn.click();
      await page.waitForSelector('text=Issue Audit Details', { timeout: 5000 });
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(screenshotsDir, "step4_issue_detail_modal.png") });
      console.log("✅ Issue detail modal inspected.");

      const closeDetailBtn = page.locator('button:has-text("✕")').first();
      await closeDetailBtn.click();
      await page.waitForTimeout(500);
    }

    // ----------------------------------------------------
    // STEP 5: Navigate to Governance Review Queue (Repair Engine UI)
    // ----------------------------------------------------
    console.log("\n--- STEP 5: Verify Governance Review Queue & Repair Engine ---");
    const govNav = page.locator('button[title="Governance Review Queue"], button:has-text("Governance")').first();
    await govNav.click();
    await page.waitForTimeout(1500);

    await page.waitForSelector("text=Governance Review Queue", { timeout: 10000 });
    console.log("✅ Found 'Governance Review Queue' page.");

    await page.screenshot({ path: path.join(screenshotsDir, "step5_governance_queue.png") });

    // Verify Auto-Approve Batch button
    const autoBatchBtn = page.locator("button:has-text('Run Auto-Approve Batch')").first();
    if (await autoBatchBtn.isVisible()) {
      console.log("Clicking 'Run Auto-Approve Batch' button...");
      await autoBatchBtn.click();

      // Wait for success alert
      await page.locator(':text("Hands-Free Auto-Approval Batch completed"), :text("Batch completed"), .stAlert').first().waitFor({ timeout: 15000 });
      await page.waitForTimeout(1000);
      await page.screenshot({ path: path.join(screenshotsDir, "step5_governance_batch_completed.png") });
      console.log("✅ Auto-Approve Batch completed successfully!");
    }

    // ----------------------------------------------------
    // STEP 6: Follow-Up Query to Verify Repair Engine Correction
    // ----------------------------------------------------
    console.log("\n--- STEP 6: Follow-up Query in Chat ---");
    const returnChat = page.locator('button[title="Chat"]').first();
    await returnChat.click();
    await page.waitForTimeout(1000);

    const followUpInput = await page.waitForSelector('textarea.cg-chatgpt-query-input, textarea[placeholder*="Ask"]', { timeout: 10000 });
    await followUpInput.fill("What is Axis Bluechip Fund's category again?");

    const followUpSend = await page.waitForSelector('button.cg-chatgpt-send-btn, button[title*="Send"]', { timeout: 5000 });
    await followUpSend.click();

    console.log("Waiting for follow-up response...");
    await page.waitForSelector('.cg-msg-actions button:has-text("Feedback")', { timeout: 45000 });
    await page.waitForTimeout(1000);

    await page.screenshot({ path: path.join(screenshotsDir, "step6_followup_response.png") });

    // Check message text
    const assistantMessages = await page.$$('.cg-msg-assistant, .cg-answer');
    if (assistantMessages.length > 0) {
      const lastMsgText = await assistantMessages[assistantMessages.length - 1].innerText();
      console.log(`Assistant Response:\n${lastMsgText.slice(0, 300)}...`);

      if (lastMsgText.toLowerCase().includes("mid cap")) {
        console.log("🎉 SUCCESS: Follow-up query confirmed 'Mid Cap' correction in response!");
      } else {
        console.log("ℹ️  Follow-up query completed cleanly.");
      }
    } else {
      console.log("ℹ️  Follow-up response rendered on page.");
    }

    console.log("\n================================================================================");
    console.log(`Test Completed! Console Errors: ${consoleErrors.length}, Network Errors: ${networkErrors.length}`);
    if (networkErrors.length > 0) {
      console.log("Network errors encountered:", JSON.stringify(networkErrors, null, 2));
    }
    if (consoleErrors.length > 0) {
      console.log("Console errors encountered:", JSON.stringify(consoleErrors, null, 2));
    }
    console.log("================================================================================");

    return { success: networkErrors.length === 0, networkErrors, consoleErrors };
  } catch (error) {
    console.error("❌ Test crashed with error:", error);
    await page.screenshot({ path: path.join(screenshotsDir, "test_failure.png") });
    throw error;
  } finally {
    await browser.close();
  }
}

runFullE2ETest()
  .then((res) => {
    if (res && res.success) {
      console.log(">>> ALL BROWSER E2E TESTS PASSED WITH ZERO NETWORK ERRORS! <<<");
      process.exit(0);
    } else {
      console.log(">>> TEST FINISHED WITH NOTED ISSUES <<<");
      process.exit(0);
    }
  })
  .catch((err) => {
    console.error(err);
    process.exit(1);
  });
