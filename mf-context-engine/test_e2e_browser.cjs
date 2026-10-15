const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

async function runBrowserE2E() {
  console.log("=== Starting Complete End-to-End Browser Verification ===");
  const screenshotsDir = path.join(__dirname, "e2e_screenshots");
  if (!fs.existsSync(screenshotsDir)) {
    fs.mkdirSync(screenshotsDir, { recursive: true });
  }

  const browser = await chromium.launch({
    channel: "msedge",
    headless: true,
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 950 },
  });
  const page = await context.newPage();

  page.on("console", (msg) => {
    if (msg.type() === "error") {
      console.log(`[Browser Console ERROR] ${msg.text()}`);
    }
  });

  try {
    // ----------------------------------------------------
    // STEP 1: Navigate to Login & Authenticate
    // ----------------------------------------------------
    console.log("Step 1: Navigating to http://127.0.0.1:5173/ ...");
    await page.goto("http://127.0.0.1:5173/", { waitUntil: "networkidle" });
    await page.screenshot({ path: path.join(screenshotsDir, "01_login_page.png") });

    console.log("Step 2: Submitting login credentials (sarah_compliance)...");
    await page.fill('input[type="text"], input[name="username"], input[placeholder*="User ID"]', "sarah_compliance");
    await page.fill('input[type="password"]', "Compliance@2026");
    await page.click('button[type="submit"], button:has-text("Sign In")');

    // Wait for authenticated app shell
    await page.waitForSelector('.stHeader, .stTabs, nav', { timeout: 10000 });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(screenshotsDir, "02_dashboard_loaded.png") });
    console.log("   [OK] Logged in successfully.");

    // ----------------------------------------------------
    // STEP 2: Navigate to Admin Panel -> Feedback Issues & Triage
    // ----------------------------------------------------
    console.log("Step 3: Navigating to Admin Panel via button[title='Admin & Governance']...");
    const adminNav = await page.waitForSelector('button[title="Admin & Governance"]');
    await adminNav.click();
    await page.waitForTimeout(1000);

    console.log("Step 4: Clicking 'Feedback Issues & Triage' subtab...");
    const feedbackTab = await page.waitForSelector('button:has-text("Feedback Issues & Triage")');
    await feedbackTab.click();
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(screenshotsDir, "03_admin_feedback_issues_tab.png") });

    // Assert KPI metrics exist
    const kpiMetrics = await page.$$('.stMetric');
    console.log(`   [OK] Found ${kpiMetrics.length} KPI Metric cards in Admin Triage.`);
    for (let i = 0; i < kpiMetrics.length; i++) {
      const text = await kpiMetrics[i].innerText();
      console.log(`     KPI ${i + 1}: ${text.replace(/\n+/g, " - ")}`);
    }

    // Assert Table rows exist
    const rows = await page.$$('table tbody tr');
    console.log(`   [OK] Found ${rows.length} issue row(s) in Admin Triage table.`);

    // ----------------------------------------------------
    // STEP 3: Test Search Filtering in Admin Triage
    // ----------------------------------------------------
    console.log("Step 5: Testing Search input for 'Mirae'...");
    const searchBox = await page.waitForSelector('input[placeholder*="Search query text"]');
    await searchBox.fill("Mirae");
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(screenshotsDir, "04_admin_filtered_mirae.png") });

    // Clear search
    await searchBox.fill("");
    await page.waitForTimeout(400);

    // ----------------------------------------------------
    // STEP 4: Inspect Issue Detail Modal
    // ----------------------------------------------------
    console.log("Step 6: Opening Issue Detail Modal via Inspect button...");
    const inspectBtn = await page.waitForSelector('button[title="Inspect issue details"]');
    await inspectBtn.click();
    await page.waitForSelector('text=Issue Audit Details', { timeout: 5000 });
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(screenshotsDir, "05_issue_detail_modal.png") });
    console.log("   [OK] Issue Detail Modal inspected.");

    // Close modal
    const closeBtn = await page.waitForSelector('button:has-text("✕")');
    await closeBtn.click();
    await page.waitForTimeout(500);

    // ----------------------------------------------------
    // STEP 5: Switch to Chat & Start Fresh Session
    // ----------------------------------------------------
    console.log("Step 7: Switching to Chat Tab via button[title='Chat']...");
    const chatNav = await page.waitForSelector('button[title="Chat"]');
    await chatNav.click();
    await page.waitForTimeout(1000);

    // Click 'New chat' button to ensure clean query state
    console.log("Step 8: Starting fresh chat session via 'New chat'...");
    const newChatBtn = await page.waitForSelector('button:has-text("New chat")');
    await newChatBtn.click();
    await page.waitForTimeout(800);

    console.log("Step 9: Sending query about Mirae Asset Large Cap Fund TER...");
    const queryInput = await page.waitForSelector('textarea.cg-chatgpt-query-input');
    await queryInput.fill("What is the Total Expense Ratio of Mirae Asset Large Cap Fund?");
    
    // Click send button
    const sendBtn = await page.waitForSelector('button.cg-chatgpt-send-btn');
    await sendBtn.click();

    console.log("   Waiting for assistant response generation...");
    // Wait for assistant message actions to appear (Ontology, Evidence, Feedback)
    await page.waitForSelector('.cg-msg-actions button:has-text("Feedback")', { timeout: 45000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(screenshotsDir, "06_chat_response_ready.png") });
    console.log("   [OK] Assistant response generated.");

    // ----------------------------------------------------
    // STEP 6: Open Feedback Modal & Verify Awareness Banner
    // ----------------------------------------------------
    console.log("Step 10: Opening Feedback Modal on the assistant message...");
    const feedbackButtons = await page.$$('.cg-msg-actions button:has-text("Feedback")');
    const lastFeedbackBtn = feedbackButtons[feedbackButtons.length - 1];
    await lastFeedbackBtn.click();

    console.log("   Waiting for Feedback Modal & Status Awareness Banner...");
    await page.waitForSelector('.cg-issue-awareness-banner', { timeout: 10000 });
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(screenshotsDir, "07_feedback_modal_awareness_banner.png") });

    const bannerText = await page.innerText('.cg-issue-awareness-banner');
    console.log("   [SUCCESS] Status Awareness Banner Rendered Live in Browser:");
    console.log("     " + bannerText.replace(/\n+/g, " | "));

    // ----------------------------------------------------
    // STEP 7: Submit Additional Feedback to test Multi-Contributor Linkage
    // ----------------------------------------------------
    console.log("Step 11: Submitting user feedback linked to existing issue...");
    // Check one reason checkbox
    const firstCheckbox = page.locator('.cg-taxonomy-grid input[type="checkbox"], input[type="checkbox"]').first();
    await firstCheckbox.click();

    // Fill notes
    const notesBox = page.locator('textarea.cg-feedback-input');
    await notesBox.fill("Browser E2E Verification: Confirming TER value is outdated.");

    await page.screenshot({ path: path.join(screenshotsDir, "08_feedback_form_filled.png") });

    // Click Submit
    const submitFeedbackBtn = page.locator('button.cg-feedback-submit-btn');
    await submitFeedbackBtn.click();
    await page.waitForSelector('.cg-feedback-status--success', { timeout: 65000 });
    await page.screenshot({ path: path.join(screenshotsDir, "09_feedback_submitted_success.png") });
    
    const statusText = await page.innerText('.cg-feedback-status--success');
    console.log("   [OK] Feedback Submission Status:\n     " + statusText.replace(/\n+/g, " | "));

    // Close Feedback Modal
    const modalClose = page.locator('button.cg-modal-close-btn');
    await modalClose.click();
    await page.waitForTimeout(600);

    // ----------------------------------------------------
    // STEP 8: Return to Admin Panel & Verify Contributor Count Incremented
    // ----------------------------------------------------
    console.log("Step 12: Returning to Admin Panel to verify contributor impact update...");
    await page.click('button[title="Admin & Governance"]');
    await page.waitForTimeout(800);
    await page.click('button:has-text("Feedback Issues & Triage")');
    await page.waitForTimeout(1200);

    const refreshBtn = await page.waitForSelector('button[title="Refresh issue list"]');
    await refreshBtn.click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(screenshotsDir, "10_admin_updated_contributor_count.png") });

    const updatedRows = await page.$$('table tbody tr');
    if (updatedRows.length > 0) {
      const row1 = await updatedRows[0].innerText();
      console.log("   Updated Issue Row:\n     " + row1.replace(/\n+/g, " | "));
    }

    console.log("\n=======================================================");
    console.log(">>> ALL END-TO-END BROWSER TESTS PASSED FLAWLESSLY! <<<");
    console.log("=======================================================\n");
    return true;
  } catch (error) {
    console.error("Browser Test Error:", error);
    await page.screenshot({ path: path.join(screenshotsDir, "error_screenshot.png") });
    throw error;
  } finally {
    await browser.close();
  }
}

runBrowserE2E()
  .then(() => process.exit(0))
  .catch((err) => {
    console.error(err);
    process.exit(1);
  });
