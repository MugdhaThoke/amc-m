// ===========================================================================
// Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
// 
// End-to-End Browser-based Test for Phase 5:
// Scale, Caching, Telemetry, Server-Side Search & Pagination
// ===========================================================================

const { chromium } = require('playwright');
const path = require('path');

async function runPhase5BrowserE2E() {
  console.log('=== Starting Phase 5 End-to-End Browser Test: Scale, Caching & Pagination ===');
  let browser;

  try {
    // 1. Launch Microsoft Edge on Windows
    console.log('[1/7] Launching Microsoft Edge via Playwright...');
    browser = await chromium.launch({
      channel: 'msedge',
      headless: true,
    });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 950 },
    });
    const page = await context.newPage();

    // 2. Navigate to mf-context-engine frontend
    console.log('[2/7] Navigating to http://localhost:5173...');
    await page.goto('http://localhost:5173', { waitUntil: 'domcontentloaded', timeout: 30000 });
    console.log('Page loaded. Title:', await page.title());

    // 3. Authenticate as compliance_officer
    console.log('[3/7] Performing authentication as compliance_officer...');
    const userInput = page.locator('input[type="text"], input[name="userId"], input[placeholder*="User ID"], #userId').first();
    const passInput = page.locator('input[type="password"]').first();
    const submitBtn = page.locator('button[type="submit"]').first();

    await userInput.waitFor({ state: 'visible', timeout: 10000 });
    await userInput.fill('compliance_officer');
    await passInput.fill('Compliance@2026');
    await submitBtn.click();

    console.log('Waiting for login transition and workspace mount...');
    await page.waitForTimeout(3000);

    // 4. Seed issues to ensure pagination (> 10 items) and cache testing
    console.log('[4/7] Pre-seeding feedback issues to validate pagination and caching...');
    const seedResult = await page.evaluate(async () => {
      let token = null;
      try {
        const sess = JSON.parse(
          sessionStorage.getItem('ns_cg_auth_session_v1') ||
          localStorage.getItem('ns_cg_auth_session_v1') ||
          '{}'
        );
        token = sess.token;
      } catch (e) {}

      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      // Submit 12 distinct issues to exceed page size of 10
      const topics = [
        "SEBI Mutual Fund Investment Valuation Norms",
        "Total Expense Ratio Cap for Equity Schemes",
        "Minimum Application Amount for Liquid Funds",
        "Macaulay Duration Norms for Medium Duration Debt Funds",
        "Derivatives Hedging Threshold for Arbitrage Funds",
        "Portfolio Rebalancing Timeline for Large Cap Funds",
        "Tracking Error Disclosure Norms for Index Schemes",
        "NAV Cut-off Timing for Subscription Transactions",
        "Side-Pocketing Provision for Stressed Debt Instruments",
        "Unlisted Security Holding Thresholds for AMC Portfolios",
        "Risk-o-meter Monthly Recalibration Norms",
        "AMFI Code of Conduct for Intermediary Commissions",
      ];

      for (let i = 0; i < topics.length; i++) {
        await fetch('/api/feedback', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            response_id: `resp_p5_e2e_${i}_${Date.now()}`,
            interaction_id: `int_p5_e2e_${i}_${Date.now()}`,
            session_id: `sess_p5_e2e_${i}_${Date.now()}`,
            turn_number: 1,
            query_text: `${topics[i]} [E2E Phase 5 Run]`,
            actor_id: 'compliance_officer',
            selected_categories: [i % 2 === 0 ? 'F08' : 'F04'],
            feedback_text: `Test feedback commentary for item ${i + 1}`,
          }),
        });
      }
      return { seeded: topics.length };
    });
    console.log(`Seeded ${seedResult.seeded} feedback items for pagination testing.`);
    await page.waitForTimeout(1500);

    // 5. Navigate to Admin Feedback Issues & Triage
    console.log('[5/7] Navigating to Admin Feedback Issues & Triage Queue...');
    let issuesNavBtn = page.locator('button.cg-nav-subitem:has-text("Feedback Issues"), button:has-text("Feedback Issues & Triage")').first();
    const isIssuesVisible = await issuesNavBtn.isVisible();
    if (!isIssuesVisible) {
      const adminGroupBtn = page.locator('button.cg-nav-group-header:has-text("Admin & Governance")').first();
      if (await adminGroupBtn.isVisible()) {
        await adminGroupBtn.click();
        await page.waitForTimeout(600);
      }
    }

    await issuesNavBtn.waitFor({ state: 'visible', timeout: 8000 });
    await issuesNavBtn.click();
    await page.waitForTimeout(2000);

    // Verify cache telemetry pill is visible
    const telemetryPill = page.locator('text=/Cache:/i').first();
    await telemetryPill.waitFor({ state: 'visible', timeout: 5000 });
    const telemetryText = await telemetryPill.textContent();
    console.log(`Verified Cache Telemetry Pill visible in UI: "${telemetryText}"`);

    // Verify Pagination Controls
    const paginationText = page.locator('text=/Showing \\d+ to \\d+ of \\d+ issues/i').first();
    await paginationText.waitFor({ state: 'visible', timeout: 5000 });
    console.log(`Pagination footer visible: "${await paginationText.textContent()}"`);

    const nextBtn = page.locator('button:has-text("Next")').first();
    const prevBtn = page.locator('button:has-text("Prev")').first();
    if (await nextBtn.isEnabled()) {
      console.log('Testing page forward transition...');
      await nextBtn.click();
      await page.waitForTimeout(1000);
      console.log(`Page after click: "${await paginationText.textContent()}"`);

      console.log('Testing page back transition...');
      await prevBtn.click();
      await page.waitForTimeout(1000);
      console.log(`Page after return: "${await paginationText.textContent()}"`);
    }

    // Test Server-Side Search input
    console.log('Testing server-side search filter...');
    const searchInput = page.locator('input[placeholder*="Search query text"]').first();
    await searchInput.fill('Valuation Norms');
    await page.waitForTimeout(1500);

    const filteredRows = page.locator('table tbody tr');
    const rowCount = await filteredRows.count();
    console.log(`Filtered rows after searching "Valuation Norms": ${rowCount}`);

    // Clear search
    await searchInput.fill('');
    await page.waitForTimeout(1000);

    // 6. Navigate to "My Feedback" Personal View
    console.log('[6/7] Navigating to My Feedback personal view...');
    const myFeedbackNav = page.locator('button:has-text("My Feedback"), a:has-text("My Feedback")').first();
    await myFeedbackNav.waitFor({ state: 'visible', timeout: 5000 });
    await myFeedbackNav.click();
    await page.waitForTimeout(2000);

    const myFeedbackHeading = page.locator('h2:has-text("My Reported Feedback")').first();
    await myFeedbackHeading.waitFor({ state: 'visible', timeout: 5000 });
    console.log('My Reported Feedback view loaded successfully.');

    const myPagination = page.locator('text=/Showing \\d+ to \\d+ of \\d+ issues/i').first();
    if (await myPagination.isVisible()) {
      console.log(`My Feedback pagination: "${await myPagination.textContent()}"`);
    }

    // 7. Navigate back to Admin Feedback Issues & Triage for final verification screenshot
    console.log('[7/8] Navigating back to Admin Feedback Issues & Triage for artifact capture...');
    await issuesNavBtn.click();
    await page.waitForTimeout(2000);

    // 8. Capture Phase 5 Verification Screenshot
    console.log('[8/8] Capturing Phase 5 verification screenshot...');
    const screenshotDir = 'C:\\Users\\HemantMore\\.gemini\\antigravity\\brain\\a06a23ef-9709-4695-b865-751699cc0fe6';
    const artifactPath = path.join(screenshotDir, 'e2e_phase5_verification.png');
    await page.screenshot({ path: artifactPath, fullPage: false });
    console.log(`Screenshot saved successfully at: ${artifactPath}`);


    console.log('=== Phase 5 End-to-End Browser Test PASSED Successfully! ===');
  } catch (err) {
    console.error('Phase 5 E2E Browser Test Failed:', err);
    process.exitCode = 1;
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

runPhase5BrowserE2E();
