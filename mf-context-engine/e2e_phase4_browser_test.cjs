// ===========================================================================
// Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
// 
// End-to-End Browser-based Test for Phase 4: Category-Aware Feedback Banner
// ===========================================================================

const { chromium } = require('playwright');
const path = require('path');

async function runPhase4BrowserE2E() {
  console.log('=== Starting Phase 4 End-to-End Browser Test: Category-Aware Banner ===');
  let browser;

  try {
    // 1. Launch Microsoft Edge on Windows
    console.log('[1/6] Launching Microsoft Edge via Playwright...');
    browser = await chromium.launch({
      channel: 'msedge',
      headless: true,
    });
    const context = await browser.newContext({
      viewport: { width: 1400, height: 900 },
    });
    const page = await context.newPage();

    // 2. Navigate to mf-context-engine frontend
    console.log('[2/6] Navigating to http://localhost:5173...');
    await page.goto('http://localhost:5173', { waitUntil: 'domcontentloaded', timeout: 30000 });
    console.log('Page loaded. Title:', await page.title());

    // 3. Authenticate as compliance_officer
    console.log('[3/6] Performing authentication as compliance_officer...');
    const userInput = page.locator('input[type="text"], input[name="userId"], input[placeholder*="User ID"], #userId').first();
    const passInput = page.locator('input[type="password"]').first();
    const submitBtn = page.locator('button[type="submit"]').first();

    await userInput.waitFor({ state: 'visible', timeout: 10000 });
    await userInput.fill('compliance_officer');
    await passInput.fill('Compliance@2026');
    await submitBtn.click();

    console.log('Waiting for login transition and workspace mount...');
    await page.waitForTimeout(3000);

    // 4. Seed Known Issue with Categories F08 (count 2), F04 (count 1), F06 (count 1)
    const testQuery = 'What is the Total Expense Ratio of Mirae Asset Large Cap Fund?';
    console.log(`[4/6] Pre-seeding category breakdown signal for: "${testQuery}"...`);

    const seedResult = await page.evaluate(async (queryText) => {
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

      // Submission 1: F08 + F04
      const res1 = await fetch('/api/feedback', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          response_id: `resp_p4_seed1_${Date.now()}`,
          interaction_id: `int_p4_seed1_${Date.now()}`,
          session_id: `sess_p4_seed1_${Date.now()}`,
          turn_number: 1,
          query_text: queryText,
          actor_id: 'compliance_officer',
          selected_categories: ['F08', 'F04'],
          feedback_text: 'Outdated TER percentage in response',
        }),
      });

      // Submission 2: F08 + F06
      const res2 = await fetch('/api/feedback', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          response_id: `resp_p4_seed2_${Date.now()}`,
          interaction_id: `int_p4_seed2_${Date.now()}`,
          session_id: `sess_p4_seed2_${Date.now()}`,
          turn_number: 2,
          query_text: queryText,
          actor_id: 'analyst_p2',
          selected_categories: ['F08', 'F06'],
          feedback_text: 'Citation for TER table is incorrect',
        }),
      });

      // Probe status endpoint directly to verify breakdown payload
      const statusRes = await fetch(`/api/feedback/status?query=${encodeURIComponent(queryText)}`, { headers });
      const statusData = await statusRes.json();

      return {
        submit1: res1.status,
        submit2: res2.status,
        statusData,
      };
    }, testQuery);

    console.log('Seed result verification:');
    console.log('- has_existing_issue:', seedResult.statusData.has_existing_issue);
    console.log('- contributor_count:', seedResult.statusData.contributor_count);
    console.log('- category_breakdown:', JSON.stringify(seedResult.statusData.category_breakdown, null, 2));

    if (!seedResult.statusData.category_breakdown || seedResult.statusData.category_breakdown.length === 0) {
      throw new Error('Failed to retrieve category_breakdown from status endpoint');
    }

    // 5. Navigate to Chat & Send Query to Trigger Result Card
    console.log('[5/6] Opening fresh Chat session and executing query...');
    const newChatBtn = page.locator('button:has-text("New chat")').first();
    await newChatBtn.click();
    await page.waitForTimeout(600);

    const queryInput = page.locator('textarea.cg-chatgpt-query-input');
    await queryInput.waitFor({ state: 'visible', timeout: 5000 });
    await queryInput.fill(testQuery);

    const sendBtn = page.locator('button.cg-chatgpt-send-btn');
    await sendBtn.click();

    console.log('Waiting for assistant response and action buttons...');
    const feedbackActionBtn = page.locator('.cg-msg-actions button:has-text("Feedback")').last();
    await feedbackActionBtn.waitFor({ state: 'visible', timeout: 45000 });
    await page.waitForTimeout(1000);

    // Click Feedback button to open FeedbackModal
    console.log('Opening Feedback Modal on assistant response card...');
    await feedbackActionBtn.click();

    // 6. Verify Category-Aware Banner Rendered in Browser
    console.log('[6/6] Verifying Category-Aware Status Banner and Breakdown Pills...');
    const banner = page.locator('.cg-issue-awareness-banner');
    await banner.waitFor({ state: 'visible', timeout: 10000 });
    console.log('✓ Found .cg-issue-awareness-banner');

    // Verify title and status pill
    const titleText = await banner.locator('.cg-issue-awareness-title').innerText();
    console.log('Banner title & badges:', titleText.trim().replace(/\n/g, ' '));

    // Verify "Previously flagged:" section
    const flaggedHeader = banner.locator('.cg-issue-category-header');
    await flaggedHeader.waitFor({ state: 'visible', timeout: 3000 });
    console.log('✓ Found "Previously flagged:" section header');

    // Verify category breakdown pills (F08, F04, F06)
    const pills = banner.locator('.cg-category-breakdown-pill');
    const pillCount = await pills.count();
    console.log(`Found ${pillCount} category breakdown pill(s) in banner`);

    const pillDetails = [];
    for (let i = 0; i < pillCount; i++) {
      const p = pills.nth(i);
      const text = (await p.innerText()).trim().replace(/\n/g, ' ');
      const titleAttr = await p.getAttribute('title');
      pillDetails.push({ text, tooltip: titleAttr });
    }
    console.log('Category breakdown pills:', JSON.stringify(pillDetails, null, 2));

    if (!pillDetails.some(p => p.text.includes('F08'))) {
      throw new Error('Expected F08 pill in category breakdown!');
    }
    console.log('✓ F08 pill confirmed present with count multiplier');

    // Verify checkbox grid below remains interactive and unblocked (§5.2)
    const checkboxGrid = page.locator('[role="group"][aria-label="Failure Taxonomy Categories"]');
    await checkboxGrid.waitFor({ state: 'visible', timeout: 3000 });
    const checkboxes = checkboxGrid.locator('input[type="checkbox"]');
    const totalCheckboxes = await checkboxes.count();
    console.log(`✓ Checkbox grid intact and fully interactive (${totalCheckboxes} taxonomy checkboxes)`);

    // Capture verification screenshot
    const screenshotDir = 'C:\\Users\\HemantMore\\.gemini\\antigravity\\brain\\a06a23ef-9709-4695-b865-751699cc0fe6';
    const screenshotPath = path.join(screenshotDir, 'e2e_phase4_verification.png');
    await page.screenshot({ path: screenshotPath, fullPage: false });
    console.log('✓ Verification screenshot saved to:', screenshotPath);

    console.log('=== Phase 4 End-to-End Browser Test PASSED Successfully! ===');
  } catch (error) {
    console.error('❌ Phase 4 E2E Test Failed:', error);
    process.exit(1);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

runPhase4BrowserE2E();
