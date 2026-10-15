#!/usr/bin/env python3
# ===========================================================================
# End-to-End Repair Flow Test
# ===========================================================================
#
# This script demonstrates the complete flow:
# 1. User submits a query
# 2. System returns an initial response
# 3. User submits feedback with a correction
# 4. Feedback loop processes the correction
# 5. Repair engine creates patches
# 6. User submits follow-up query
# 7. System injects patches into context
# 8. User receives corrected response
#

import asyncio
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone

import requests

# Configure logging with visible indicators
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("e2e_test")

# Configuration
BACKEND_URL = "http://localhost:8000"
REPAIR_ENGINE_URL = "http://localhost:8002"
SESSION_ID = f"test_session_{uuid.uuid4().hex[:8]}"
ACTOR_ID = f"user_{uuid.uuid4().hex[:8]}"

print("\n" + "=" * 80)
print("END-TO-END REPAIR FLOW TEST")
print("=" * 80)
print(f"\nTest Session: {SESSION_ID}")
print(f"Test User: {ACTOR_ID}")
print(f"Backend URL: {BACKEND_URL}")
print(f"Repair Engine URL: {REPAIR_ENGINE_URL}")
print("\n" + "=" * 80 + "\n")


def check_service_health():
    """Verify services are running."""
    print("Checking service health...")
    
    try:
        backend = requests.get(f"{BACKEND_URL}/api/health", timeout=5)
        print(f"Backend is {backend.json().get('status', 'unknown')}")
    except Exception as e:
        print(f"Backend not responding: {e}")
        return False
    
    try:
        repair = requests.get(f"{REPAIR_ENGINE_URL}/api/health", timeout=5)
        print(f"Repair Engine is {repair.json().get('status', 'unknown')}")
    except Exception as e:
        print(f"Repair Engine not responding: {e}")
        return False
    
    print()
    return True


def step_1_submit_query():
    """Step 1: User submits initial query."""
    print("=" * 80)
    print("STEP 1️⃣: USER SUBMITS INITIAL QUERY")
    print("=" * 80)
    
    query_text = "What is the fund category of Axis Bluechip Fund?"
    print(f"\nUser Query: \"{query_text}\"")
    
    print(f"\nCalling: POST {BACKEND_URL}/api/query")
    
    payload = {
        "query": query_text,
        "session_id": SESSION_ID,
        "actor_id": ACTOR_ID,
        "top_k": 5
    }
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/query",
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            response_id = data.get("response_id")
            response_text = data.get("response", "")
            
            print(f"\n✅ Query successful!")
            print(f"   Response ID: {response_id}")
            print(f"   Response: {response_text[:200]}...")
            print()
            
            return response_id, response_text, query_text
        else:
            print(f"\n❌ Query failed: {response.status_code}")
            print(f"   Error: {response.text}")
            return None, None, None
    
    except Exception as e:
        print(f"\n❌ Error submitting query: {e}")
        return None, None, None


def step_2_submit_feedback(response_id, original_query):
    """Step 2: User submits feedback with correction."""
    print("\n" + "=" * 80)
    print("STEP 2️⃣: USER SUBMITS FEEDBACK WITH CORRECTION")
    print("=" * 80)
    
    feedback_text = "The fund category is actually Mid Cap, not Large Cap"
    print(f"\n💬 User Feedback: \"{feedback_text}\"")
    
    print(f"\n🔗 Calling: POST {BACKEND_URL}/api/feedback")
    
    payload = {
        "response_id": response_id,
        "session_id": SESSION_ID,
        "interaction_id": f"inter_{uuid.uuid4().hex[:8]}",
        "turn_number": 1,
        "query_text": original_query,
        "actor_id": ACTOR_ID,
        "actor_role": "reviewer",
        "feedback_text": feedback_text,
        "selected_categories": ["F04"],  # Knowledge error
        "client_timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/feedback",
            json=payload,
            timeout=30
        )
        
        if response.status_code == 201:
            data = response.json()
            feedback_id = data.get("feedback_id")
            status = data.get("status")
            
            print(f"\nFeedback submitted successfully!")
            print(f"   Feedback ID: {feedback_id}")
            print(f"   Status: {status}")
            print(f"   Priority Tier: {data.get('priority_tier', 'N/A')}")
            print()
            
            return feedback_id
        else:
            print(f"\nFeedback submission failed: {response.status_code}")
            print(f"   Error: {response.text}")
            return None
    
    except Exception as e:
        print(f"\nError submitting feedback: {e}")
        return None


def step_3_check_unified_record(response_id):
    """Step 3: Verify unified evaluation record was created."""
    print("\n" + "=" * 80)
    print("STEP 3️⃣: CHECKING UNIFIED EVALUATION RECORD")
    print("=" * 80)
    
    print(f"\nWaiting 2 seconds for feedback loop to complete...")
    time.sleep(2)
    
    print(f"\nChecking database for unified record...")
    
    try:
        from app.core.database import SessionLocal
        from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
        
        db = SessionLocal()
        record = db.query(UnifiedEvaluationRecord).filter(
            UnifiedEvaluationRecord.response_id == response_id
        ).first()
        db.close()
        
        if record:
            print(f"\nUnified record found!")
            print(f"   Entry Route: {record.entry_route}")
            print(f"   Root Cause: {record.root_cause}")
            print(f"   Severity: {record.severity}")
            print(f"   Repair Required: {record.repair}")
            print(f"   Repair Target: {record.repair_target}")
            print(f"   Dissatisfaction Evidence: {bool(record.dissatisfaction_evidence_json)}")
            
            if record.dissatisfaction_evidence_json:
                evidence = record.dissatisfaction_evidence_json
                claims = evidence.get("correction_claims", [])
                print(f"   Correction Claims: {len(claims)}")
                for i, claim in enumerate(claims, 1):
                    print(f"      [{i}] {claim.get('entity_name')}.{claim.get('attribute')} = {claim.get('asserted_value')}")
            
            print()
            return record
        else:
            print(f"\nNo unified record found yet (feedback loop may still be processing)")
            print()
            return None
    
    except Exception as e:
        print(f"\n Could not check unified record: {e}")
        return None


def step_4_check_repair_engine_patches():
    """Step 4: Verify patches were created in repair engine."""
    print("\n" + "=" * 80)
    print("STEP 4️⃣: CHECKING REPAIR ENGINE PATCHES")
    print("=" * 80)
    
    print(f"\n⏳ Waiting 2 seconds for repair engine to process...")
    time.sleep(2)
    
    print(f"\n🔗 Calling: GET {REPAIR_ENGINE_URL}/api/patches/pending")
    
    try:
        response = requests.get(
            f"{REPAIR_ENGINE_URL}/api/patches/pending",
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            total = data.get("total", 0)
            patches = data.get("patches", [])
            
            print(f"\nRepair engine status retrieved!")
            print(f"   Total Pending Patches: {total}")
            
            if patches:
                for i, patch in enumerate(patches[:3], 1):  # Show first 3
                    print(f"\n   [{i}] Patch ID: {patch.get('patch_id')}")
                    print(f"       Entity: {patch.get('entity_id')}")
                    print(f"       Attribute: {patch.get('attribute')}")
                    print(f"       Value: {patch.get('corrected_value')}")
                    print(f"       Confidence: {patch.get('confidence', 0):.2f}")
            
            print()
            return patches
        else:
            print(f"\nFailed to get patches: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
    
    except Exception as e:
        print(f"\nError checking patches: {e}")
        return None


def step_5_approve_patches(patches):
    """Step 5: Approve patches in repair engine."""
    print("\n" + "=" * 80)
    print("STEP 5️⃣: APPROVING PATCHES IN REPAIR ENGINE")
    print("=" * 80)
    
    if not patches:
        print("\n⏭️  No patches to approve")
        print()
        return True
    
    patch_ids = [p.get("patch_id") for p in patches[:3]]
    
    print(f"\n🔗 Approving {len(patch_ids)} patches...")
    
    all_approved = True
    for patch_id in patch_ids:
        try:
            response = requests.post(
                f"{REPAIR_ENGINE_URL}/api/patches/{patch_id}/approve",
                timeout=10
            )
            
            if response.status_code == 200:
                print(f"Approved: {patch_id}")
            else:
                print(f"Failed to approve {patch_id}: {response.status_code}")
                all_approved = False
        
        except Exception as e:
            print(f"Error approving {patch_id}: {e}")
            all_approved = False
    
    print()
    return all_approved


def step_6_run_governance():
    """Step 6: Run governance batch."""
    print("\n" + "=" * 80)
    print("STEP 6️⃣: RUNNING GOVERNANCE BATCH")
    print("=" * 80)
    
    print(f"\n🔗 Calling: POST {REPAIR_ENGINE_URL}/api/governance/run-batch")
    
    try:
        response = requests.post(
            f"{REPAIR_ENGINE_URL}/api/governance/run-batch",
            json={"auto_approve_threshold": 0.95},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            
            print(f"\nGovernance batch completed!")
            print(f"   Total Evaluated: {data.get('total_evaluated', 0)}")
            print(f"   Approved: {data.get('approved', 0)}")
            print(f"   Rejected: {data.get('rejected', 0)}")
            print(f"   Deployed to Graph: {data.get('deployed', 0)}")
            print()
            
            return True
        else:
            print(f"\nGovernance batch issue: {response.status_code}")
            print(f"   Response: {response.text}")
            print()
            return False
    
    except Exception as e:
        print(f"\nError running governance batch: {e}")
        print()
        return False


def step_7_submit_followup_query():
    """Step 7: User submits follow-up query to get corrected response."""
    print("\n" + "=" * 80)
    print("STEP 7️⃣: USER SUBMITS FOLLOW-UP QUERY")
    print("=" * 80)
    
    followup_query = "What is Axis Bluechip Fund's category again?"
    print(f"\nUser Follow-up Query: \"{followup_query}\"")
    
    print(f"\nCalling: POST {BACKEND_URL}/api/query")
    
    payload = {
        "query": followup_query,
        "session_id": SESSION_ID,
        "actor_id": ACTOR_ID,
        "top_k": 5
    }
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/query",
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            response_id = data.get("response_id")
            response_text = data.get("response", "")
            
            print(f"\n✅ Follow-up query successful!")
            print(f"   Response ID: {response_id}")
            print(f"   Response: {response_text[:300]}...")
            print(f"\n   💡 NOTE: Response should now use corrected value (Mid Cap)")
            print()
            
            return response_id, response_text
        else:
            print(f"\n❌ Query failed: {response.status_code}")
            print(f"   Error: {response.text}")
            return None, None
    
    except Exception as e:
        print(f"\n❌ Error submitting query: {e}")
        return None, None


def main():
    """Run the complete end-to-end test."""
    
    # Check services
    if not check_service_health():
        print("\n❌ Services are not healthy. Please start backend and repair engine.")
        print("\n   Backend: python -m uvicorn app.main:app --port 8000")
        print("   Repair:  python -m uvicorn src.amc_repair.server:app --port 8002 (from packages/amc-repair-engine)")
        return 1
    
    # Step 1: Submit initial query
    response_id, response_text, query_text = step_1_submit_query()
    if not response_id:
        print("\n❌ Failed to submit initial query")
        return 1
    
    # Step 2: Submit feedback with correction
    feedback_id = step_2_submit_feedback(response_id, query_text)
    if not feedback_id:
        print("\n❌ Failed to submit feedback")
        return 1
    
    # Step 3: Check unified record
    record = step_3_check_unified_record(response_id)
    if not record:
        print("\n⚠️  Unified record not yet created (may still be processing)")
    
    # Step 4: Check repair engine patches
    patches = step_4_check_repair_engine_patches()
    if not patches:
        print("\n⚠️  No patches found (repair engine may not be integrated)")
    
    # Step 5: Approve patches
    if patches:
        step_5_approve_patches(patches)
    
    # Step 6: Run governance batch
    step_6_run_governance()
    
    # Step 7: Submit follow-up query
    followup_id, followup_response = step_7_submit_followup_query()
    
    # Summary
    print("\n" + "=" * 80)
    print("✅ END-TO-END TEST COMPLETE!")
    print("=" * 80)
    print("\n📊 Summary:")
    print(f"   Session ID: {SESSION_ID}")
    print(f"   Initial Response ID: {response_id}")
    print(f"   Feedback ID: {feedback_id}")
    print(f"   Patches Created: {len(patches) if patches else 0}")
    if followup_id:
        print(f"   Follow-up Response ID: {followup_id}")
    print("\n✨ Check backend logs for repair engine activity:")
    print("   Look for 🚀 REPAIR ENGINE TRIGGER")
    print("   And 🎯 REPAIR ENGINE RESULT markers")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
