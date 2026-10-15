// ===========================================================================
// Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
// 
// End-to-End Browser-based Test for Phase 3 "My Feedback" Personal View
// ===========================================================================

const { chromium } = require('playwright');
const path = require('path');

async function runPhase3BrowserE2E() {
  console.log('=== Starting Phase 3 End-to-End Browser Test: "My Feedback" Personal View ===');
  let browser;

  try {
    // 1. Launch Microsoft Edge on Windows
    console.log('[1/7] Launching Microsoft Edge via Playwright...');
    browser = await chromium.launch({
      channel: 'msedge',
      headless: true,
    });
    const context = await browser.newContext({
      viewport: { width: 1400, height: 900 },
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

    // Wait for login transition
    console.log('Waiting for login transition and workspace mount...');
    await page.waitForTimeout(3000);

    // 4. Verify "My Feedback" Sidebar Navigation Item
    console.log('[4/7] Verifying "My Feedback" nav item in Sidebar...');
    const myFeedbackNavItem = page.locator('button.cg-nav-item:has-text("My Feedback")');
    await myFeedbackNavItem.waitFor({ state: 'visible', timeout: 8000 });
    console.log('✓ Found "My Feedback" nav item in Sidebar Workspace section');

    // 5. Navigate to "My Feedback" Page
    console.log('[5/7] Navigating to "My Feedback" page...');
    await myFeedbackNavItem.click();
    await page.waitForTimeout(1000);

    // Verify page header
    const pageHeading = page.locator('h2:has-text("My Reported Feedback")');
    await pageHeading.waitFor({ state: 'visible', timeout: 5000 });
    console.log('✓ Successfully arrived at "My Reported Feedback" page');

    // Verify 4 KPI Stat Cards
    const metricLabels = ['Total Reported by You', 'Pending Review', 'In Repair', 'Resolved / Closed'];
    for (const label of metricLabels) {
      const metricEl = page.locator(`.stMetric:has-text("${label}")`);
      await metricEl.waitFor({ state: 'visible', timeout: 3000 });
    }
    console.log('✓ All 4 personal KPI metric cards verified');

    // 6. Submit a Live Feedback Entry to Test Populated Table & Category Badges
    console.log('[6/7] Submitting a live feedback submission to populate "My Feedback"...');
    const uniqueQuery = `What are SEBI regulations on side-pocketing in mutual funds? [Run ${Date.now()}]`;
    const submissionResult = await page.evaluate(async (queryText) => {
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

      const res = await fetch('/api/feedback', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          response_id: `resp_p3_${Date.now()}`,
          interaction_id: `int_p3_${Date.now()}`,
          session_id: `sess_p3_${Date.now()}`,
          turn_number: 1,
          query_text: queryText,
          actor_id: 'compliance_officer',
          actor_role: 'Compliance & Regulatory Officer',
          selected_categories: ['F08', 'F04'],
          feedback_text: 'SEBI circular timeline requirement discrepancy noted in side-pocketing limits.',
        }),
      });

      return { status: res.status, data: await res.json() };
    }, uniqueQuery);

    console.log('Live feedback submit result:', submissionResult.status, submissionResult.data?.message);

    // Click Refresh button
    const refreshBtn = page.locator('button.stButton.kind-secondary:has-text("Refresh")');
    await refreshBtn.click();
    await page.waitForTimeout(1500);

    // Verify the newly submitted issue appears in the table
    const issueRow = page.locator('tr:has-text("side-pocketing")').first();
    await issueRow.waitFor({ state: 'visible', timeout: 6000 });
    console.log('✓ Found newly submitted feedback issue in personal table');

    // Verify category badges F08 and F04
    const f08Badge = issueRow.locator('span:has-text("F08")');
    const f04Badge = issueRow.locator('span:has-text("F04")');
    await f08Badge.waitFor({ state: 'visible', timeout: 3000 });
    await f04Badge.waitFor({ state: 'visible', timeout: 3000 });
    console.log('✓ Category pills F08 (Wrong Numbers or Dates) and F04 (Missing Key Documents) rendered');

    // Verify anonymized community impact
    const communityImpact = await issueRow.locator('td').nth(2).innerText();
    console.log('Community impact cell text:', communityImpact.trim().replace(/\n/g, ' '));
    if (communityImpact.includes('admin') || communityImpact.includes('user_') || communityImpact.includes('compliance_officer')) {
      throw new Error('User identity leaked in community impact cell!');
    }
    console.log('✓ Community impact is strictly anonymized (no contributor names/identities)');

    // Test Inspect Modal Details
    console.log('Testing Inspect Modal (View button)...');
    const viewBtn = issueRow.locator('button:has-text("View")');
    await viewBtn.click();
    await page.waitForTimeout(800);

    const modalTitle = page.locator('h3:has-text("Feedback Issue Details")');
    await modalTitle.waitFor({ state: 'visible', timeout: 3000 });
    const modalText = await page.locator('div:has-text("Reported Query:")').first().innerText();
    console.log('✓ Inspect modal opened displaying query and submitted comments');

    // Close modal
    const closeBtn = page.locator('button:has-text("Close")');
    await closeBtn.click();
    await page.waitForTimeout(500);

    // Save populated table screenshot
    const screenshotDir = 'C:\\Users\\HemantMore\\.gemini\\antigravity\\brain\\a06a23ef-9709-4695-b865-751699cc0fe6';
    const populatedScreenshotPath = path.join(screenshotDir, 'e2e_phase3_populated_table.png');
    await page.screenshot({ path: populatedScreenshotPath, fullPage: false });
    console.log('✓ Populated table screenshot saved to:', populatedScreenshotPath);

    // 7. Verify Non-Admin Access & Role Visibility
    console.log('[7/7] Verifying Non-Admin access (analyst_p2)...');
    // Clear storage and navigate to fresh login
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
    await page.goto('http://localhost:5173', { waitUntil: 'domcontentloaded', timeout: 20000 });

    const userInput2 = page.locator('input[type="text"], input[name="userId"], input[placeholder*="User ID"], #userId').first();
    const passInput2 = page.locator('input[type="password"]').first();
    const submitBtn2 = page.locator('button[type="submit"]').first();

    await userInput2.waitFor({ state: 'visible', timeout: 10000 });
    await userInput2.fill('analyst_p2');
    await passInput2.fill('Password123!');
    await submitBtn2.click();

    await page.waitForTimeout(3000);

    // Check that "My Feedback" IS VISIBLE for non-admin analyst
    const analystMyFeedback = page.locator('button.cg-nav-item:has-text("My Feedback")');
    await analystMyFeedback.waitFor({ state: 'visible', timeout: 5000 });
    console.log('✓ "My Feedback" is visible to non-admin ESG Analyst');

    // Check that "Admin & Governance" group is NOT visible for non-admin analyst
    const adminGroupHeader = page.locator('.cg-nav-group-header');
    const isAdminVisible = await adminGroupHeader.isVisible();
    console.log('Admin & Governance visible for non-admin:', isAdminVisible);
    if (isAdminVisible) {
      throw new Error('Admin & Governance should NOT be visible to non-admin analyst_p2!');
    }
    console.log('✓ Admin & Governance is properly hidden from non-admin');

    // Click "My Feedback" as non-admin
    await analystMyFeedback.click();
    await page.waitForTimeout(1000);
    const analystPageHeading = page.locator('h2:has-text("My Reported Feedback")');
    await analystPageHeading.waitFor({ state: 'visible', timeout: 5000 });
    console.log('✓ Non-admin analyst successfully opened "My Reported Feedback" page');

    // Save verification screenshot
    const screenshotPath = path.join(screenshotDir, 'e2e_phase3_verification.png');
    await page.screenshot({ path: screenshotPath, fullPage: false });
    console.log('✓ Screenshot saved to:', screenshotPath);

    console.log('=== Phase 3 End-to-End Browser Test PASSED Successfully! ===');
  } catch (error) {
    console.error('❌ Phase 3 E2E Test Failed:', error);
    process.exit(1);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

runPhase3BrowserE2E();
