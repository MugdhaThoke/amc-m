// ===========================================================================
// Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
//
// End-to-End Browser-based Test for Workspace Navigation & Admin Refactoring:
// 1. Verify exact Sidebar Workspace hierarchy:
//    - Chat
//    - Compare
//    - Analytics
//    - Admin & Governance
//    - My Feedback
//    - Feedback & Triage
// 2. Verify Admin & Governance merges Overview functionality directly
// 3. Verify Feedback & Triage as a top-level Workspace navigation item
// 4. Verify My Feedback navigation
// 5. Verify direct URL / refresh persistence
// 6. Verify RBAC gating (non-admin hides Admin & Governance + Feedback & Triage, shows 403 on direct access)
// ===========================================================================

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

async function runWorkspaceRefactorBrowserE2E() {
  console.log('=== Starting Workspace Navigation & Admin Refactor Browser E2E Test ===');
  let browser;

  try {
    // 1. Launch Microsoft Edge
    console.log('[1/7] Launching Microsoft Edge via Playwright...');
    browser = await chromium.launch({
      channel: 'msedge',
      headless: true,
    });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 950 },
    });
    const page = await context.newPage();

    // Log console errors from browser
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        console.log(`[Browser Console Error] ${msg.text()}`);
      }
    });

    // 2. Navigate and Authenticate as compliance_officer (Admin tier)
    console.log('[2/7] Navigating to http://localhost:5173 and logging in as compliance_officer...');
    await page.goto('http://localhost:5173', { waitUntil: 'domcontentloaded', timeout: 30000 });

    const userInput = page.locator('input[type="text"], input[name="userId"], input[placeholder*="User ID"], #userId').first();
    const passInput = page.locator('input[type="password"]').first();
    const submitBtn = page.locator('button[type="submit"]').first();

    await userInput.waitFor({ state: 'visible', timeout: 10000 });
    await userInput.fill('compliance_officer');
    await passInput.fill('Compliance@2026');
    await submitBtn.click();

    console.log('Waiting for login transition and workspace mount...');
    await page.waitForTimeout(3000);

    // 3. Validate Sidebar Workspace Navigation Hierarchy
    console.log('[3/7] Inspecting Sidebar Workspace navigation hierarchy...');
    const workspaceNav = page.locator('.cg-nav-section').first().locator('.cg-nav-list');
    await workspaceNav.waitFor({ state: 'visible', timeout: 10000 });

    const navItems = await workspaceNav.locator('.cg-nav-item .cg-nav-label').allInnerTexts();
    console.log('Discovered Workspace Navigation Items:', navItems);

    const expectedHierarchy = [
      'Chat',
      'Compare',
      'Analytics',
      'Admin & Governance',
      'My Feedback',
      'Feedback & Triage',
    ];

    console.log('Expected Hierarchy:', expectedHierarchy);

    if (JSON.stringify(navItems) !== JSON.stringify(expectedHierarchy)) {
      throw new Error(`Workspace hierarchy mismatch! Expected ${JSON.stringify(expectedHierarchy)}, but got ${JSON.stringify(navItems)}`);
    }
    console.log('✓ EXACT Sidebar Workspace hierarchy verified successfully!');

    // 4. Test Navigation to Admin & Governance (Merged Overview)
    console.log('[4/7] Navigating to Admin & Governance...');
    const adminNavItem = workspaceNav.locator('.cg-nav-item', { hasText: 'Admin & Governance' });
    await adminNavItem.click();
    await page.waitForTimeout(1000);

    // Verify Admin & Governance active highlight
    const adminIsActive = await adminNavItem.evaluate((el) => el.classList.contains('active'));
    console.log('Admin & Governance nav item has active class:', adminIsActive);
    if (!adminIsActive) throw new Error('Admin & Governance nav item is not active after click!');

    // Verify Page Header
    const adminHeader = await page.locator('.stHeader2').first().innerText();
    console.log('Admin page header text:', adminHeader);
    if (!adminHeader.includes('Admin & Governance')) {
      throw new Error(`Expected header 'Admin & Governance', but got '${adminHeader}'`);
    }

    // Verify Merged Overview Tabs
    await page.locator('.stTabs-tab, .stTabs-list button').first().waitFor({ state: 'visible', timeout: 5000 });
    const subTabLabels = await page.locator('.stTabs-tab, .stTabs-list button').allInnerTexts();
    console.log('Admin & Governance Sub-Tabs (Merged Overview):', subTabLabels);
    const expectedSubTabs = [
      'User Profile Management',
      'Role Access Matrix',
      'Security & Audit Logs',
      'Authorized Ingest & Pipeline',
    ];
    for (const expected of expectedSubTabs) {
      if (!subTabLabels.some(l => l.includes(expected))) {
        throw new Error(`Missing expected merged subtab: ${expected}`);
      }
    }
    const adminArtifactPath = 'C:/Users/HemantMore/.gemini/antigravity/brain/a06a23ef-9709-4695-b865-751699cc0fe6/e2e_admin_governance_verification.png';
    await page.screenshot({ path: adminArtifactPath, fullPage: true });
    console.log(`✓ Admin & Governance verification screenshot captured at ${adminArtifactPath}`);

    // 5. Test Navigation to Feedback & Triage
    console.log('[5/7] Navigating to Feedback & Triage...');
    const triageNavItem = workspaceNav.locator('.cg-nav-item', { hasText: 'Feedback & Triage' });
    await triageNavItem.click();
    await page.waitForTimeout(1500);

    // Verify Feedback & Triage active highlight
    const triageIsActive = await triageNavItem.evaluate((el) => el.classList.contains('active'));
    console.log('Feedback & Triage nav item has active class:', triageIsActive);
    if (!triageIsActive) throw new Error('Feedback & Triage nav item is not active after click!');

    // Verify Admin & Governance is no longer active
    const adminStillActive = await adminNavItem.evaluate((el) => el.classList.contains('active'));
    if (adminStillActive) throw new Error('Admin & Governance remained active when navigating to Feedback & Triage!');

    // Verify Triage Queue Header & Content
    const triageHeader = await page.locator('.stHeader2').first().innerText();
    console.log('Feedback & Triage header text:', triageHeader);
    if (!triageHeader.includes('Feedback & Triage')) {
      throw new Error(`Expected header 'Feedback & Triage', but got '${triageHeader}'`);
    }

    // Verify Triage KPI cards & table
    const metricLabels = await page.locator('.stMetric-label').allInnerTexts();
    console.log('Feedback & Triage KPI metrics present:', metricLabels);
    if (metricLabels.length === 0) throw new Error('No KPI metric cards rendered in Feedback & Triage!');

    // 6. Test Navigation to My Feedback
    console.log('[6/7] Navigating to My Feedback...');
    const myFeedbackNavItem = workspaceNav.locator('.cg-nav-item', { hasText: 'My Feedback' });
    await myFeedbackNavItem.click();
    await page.waitForTimeout(1000);

    const myFeedbackIsActive = await myFeedbackNavItem.evaluate((el) => el.classList.contains('active'));
    console.log('My Feedback nav item has active class:', myFeedbackIsActive);
    if (!myFeedbackIsActive) throw new Error('My Feedback nav item is not active after click!');

    const myFeedbackHeader = await page.locator('.stHeader2').first().innerText();
    console.log('My Feedback page header:', myFeedbackHeader);
    if (!myFeedbackHeader.includes('My Reported Feedback') && !myFeedbackHeader.includes('My Feedback')) {
      throw new Error(`Expected My Feedback header, got '${myFeedbackHeader}'`);
    }

    // Navigate back to Feedback & Triage and capture artifact screenshot
    await triageNavItem.click();
    await page.waitForTimeout(1500);

    const artifactPath = 'C:/Users/HemantMore/.gemini/antigravity/brain/a06a23ef-9709-4695-b865-751699cc0fe6/e2e_workspace_refactor_verification.png';
    await page.screenshot({ path: artifactPath, fullPage: true });
    console.log(`✓ Verification screenshot captured at ${artifactPath}`);

    // Also test direct page refresh persistence
    console.log('Testing direct page refresh persistence...');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);

    const triageAfterRefresh = await workspaceNav.locator('.cg-nav-item', { hasText: 'Feedback & Triage' }).evaluate((el) => el.classList.contains('active'));
    console.log('Feedback & Triage active after page reload:', triageAfterRefresh);
    if (!triageAfterRefresh) throw new Error('Active page was not preserved across page refresh!');

    // 7. Verify RBAC with Non-Admin User (Auditor / Research Analyst)
    console.log('[7/7] Validating RBAC enforcement for non-admin user...');
    // Log out current user
    await page.locator('.cg-account-btn').click();
    await page.waitForTimeout(500);
    const logoutBtn = page.locator('button', { hasText: 'Sign out' });
    await logoutBtn.click();
    await page.waitForTimeout(1500);

    // Login as non-admin user: analyst_p2 (ESG & Sustainability Analyst)
    console.log('Logging in as analyst_p2 (Non-admin)...');
    const userInput2 = page.locator('input[type="text"], input[name="userId"], input[placeholder*="User ID"], #userId').first();
    const passInput2 = page.locator('input[type="password"]').first();
    const submitBtn2 = page.locator('button[type="submit"]').first();

    await userInput2.waitFor({ state: 'visible', timeout: 10000 });
    await userInput2.fill('analyst_p2');
    await passInput2.fill('Password123!');
    await submitBtn2.click();
    await page.waitForTimeout(3000);

    // Verify non-admin workspace nav items
    const nonAdminNavItems = await workspaceNav.locator('.cg-nav-item .cg-nav-label').allInnerTexts();
    console.log('Non-Admin Workspace Navigation Items:', nonAdminNavItems);

    if (nonAdminNavItems.includes('Admin & Governance')) {
      throw new Error('Admin & Governance should NOT be visible to non-admin user!');
    }
    if (nonAdminNavItems.includes('Feedback & Triage')) {
      throw new Error('Feedback & Triage should NOT be visible to non-admin user!');
    }
    if (!nonAdminNavItems.includes('My Feedback')) {
      throw new Error('My Feedback SHOULD be visible to all authenticated users!');
    }
    console.log('✓ Non-admin navigation correctly hides Admin & Governance and Feedback & Triage!');

    // Test direct unauthorized route access
    console.log('Attempting direct unauthorized navigation to feedback_triage...');
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('ns_test_navigate', { detail: 'feedback_triage' }));
      // Directly alter localStorage state to simulate URL bookmark / route reload
      localStorage.setItem('ns_cg_active_page_v1', JSON.stringify('feedback_triage'));
    });
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);

    const accessDeniedText = await page.locator('.stAlert--error').first().innerText();
    console.log('Unauthorized access guard text:', accessDeniedText);
    if (!accessDeniedText.includes('Access Denied (403)')) {
      throw new Error(`Expected 'Access Denied (403)', but got '${accessDeniedText}'`);
    }
    console.log('✓ RBAC 403 Access Denied successfully enforced for non-admin direct route!');

    console.log('\n=============================================================');
    console.log('ALL WORKSPACE NAVIGATION & ADMIN REFACTORING TESTS PASSED!');
    console.log('=============================================================\n');

  } catch (err) {
    console.error('E2E Test Execution Failed:', err);
    process.exit(1);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

runWorkspaceRefactorBrowserE2E();
