"""v0.2.45: ten isolated member BYOK vault and synthetic cost admissions.

All keys are fake and short-lived within tests. There are NO provider
requests, no payments, trading, real brokerage connections or activation.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from engine import (
    identity_auth, tenant_foundation, tenant_ai_budget_vault as ai,
    ai_analysis,
)

NOW=datetime(2026,11,10,19,0,tzinfo=timezone.utc)


class TenUserAIVaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="edge-ai-tenuser-")
        self.path=self.tmp.name+"/members.db"
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        ai.setup(self.path)
        self.identities=identity_auth.IdentityStore(self.path)
        self.key=Fernet.generate_key().decode()
        self.store=ai.TenantAIBudgetVault(
            self.path,self.identities,credential_key=self.key)
        self.userdata={}
        self.network=patch("requests.sessions.Session.request",
                           side_effect=AssertionError("No external provider calls permitted"))
        self.network.start()
        for i in range(10):
            username="synthetic_friend_"+str(i)
            password="synthetic-member-password-strong-"+str(i)
            uid=tenant_foundation.TenantStore(self.path).provision_user(
                "Research tester "+str(i))
            self.identities.provision(uid,username,password)
            session=self.identities.authenticate(username,password,
                                                 "local_test_"+str(i))
            self.assertIsNotNone(session)
            self.userdata[i]=(uid,session)
        self.synthetic_key=lambda i:"sk-test-only-no-real-billing-key-USER-"+str(i)

    def tearDown(self):
        self.network.stop()
        self.tmp.cleanup()

    def session(self,i):
        _,s=self.userdata[i]
        return (s["token"],s["csrf"])

    def enabled(self,i,budget="0.001000"):
        token,csrf=self.session(i)
        return self.store.set_policy(
            token,csrf,mode="byok",monthly_budget_usd=budget,depth="balanced")

    def connected(self,i,budget="0.001000"):
        self.enabled(i,budget)
        token,csrf=self.session(i)
        return self.store.put_key(token,csrf,self.synthetic_key(i),consent=True)

    def test_all_ten_members_have_independent_encrypted_credentials_and_no_owner_key(self):
        for i in range(10):
            out=self.connected(i)
            self.assertFalse(out["providerKeyReturned"])
            self.assertFalse(out["verifiedWithProvider"])
            status=self.store.status(*self.session(i),now=NOW)
            self.assertEqual(status["mode"],"byok")
            self.assertEqual(status["analysisDepth"],"balanced")
            self.assertEqual(status["monthlyBudgetMicroUsd"],1000)
            self.assertTrue(status["providerKeyConfigured"])
            self.assertFalse(status["ownerKeyFallback"])
            self.assertFalse(status["managedBillingActivated"])
            self.assertFalse(status["providerBillingCapGuaranteed"])
            self.assertNotIn(self.synthetic_key(i),json.dumps(status))
        with sqlite3.connect(self.path) as conn:
            rows=conn.execute("""SELECT user_id,key_ciphertext FROM
                tenant_ai_profiles ORDER BY user_id""").fetchall()
        self.assertEqual(len(rows),10)
        self.assertEqual(len({bytes(r[1]) for r in rows}),10)
        cipher=Fernet(self.key.encode())
        ids={uid:i for i,(uid,_) in self.userdata.items()}
        for uid,encrypted in rows:
            body=json.loads(cipher.decrypt(encrypted))
            self.assertEqual(body["owner"],uid)
            self.assertEqual(body["provider"],"OpenAI")
            self.assertEqual(body["secret"],self.synthetic_key(ids[uid]))
            self.assertNotIn(body["secret"],str(encrypted))
        # Different private encryption key cannot decrypt any member key.
        with self.assertRaises(Exception):
            Fernet(Fernet.generate_key()).decrypt(rows[0][1])
        self.assertNotIn("OPENAI_API_KEY",(
            Path(__file__).resolve().parents[1]/
            "engine/tenant_ai_budget_vault.py").read_text())

    def test_ten_simultaneous_members_are_isolated_on_one_sqlite_backend(self):
        for i in range(10):
            self.connected(i,budget="0.000400")
        def one(i):
            tok,csrf=self.session(i)
            return self.store.reserve_simulated(tok,csrf,model="gpt-6-luna",
                                                input_tokens_bound=1200,
                                                max_output_tokens=500,
                                                now=NOW)
        with ThreadPoolExecutor(max_workers=10) as pool:
            results=list(pool.map(one,range(10)))
        self.assertEqual(len({r["requestId"] for r in results}),10)
        self.assertTrue(all(not r["paidRequestExecuted"] for r in results))
        self.assertEqual({r["heldMicroUsd"] for r in results},{370})
        for i in range(10):
            state=self.store.status(*self.session(i),now=NOW)
            self.assertEqual(state["locallyCountedMicroUsd"],370)
            self.assertEqual(state["remainingMicroUsd"],30)
            self.assertEqual(state["pendingOrUncertainCount"],1)
            with self.assertRaises(ai.TenantAIDenied):
                one(i)
        with sqlite3.connect(self.path) as conn:
            n=conn.execute("SELECT COUNT(*) FROM tenant_ai_reservations").fetchone()[0]
        self.assertEqual(n,10)

    def test_cross_user_cost_reconciliation_and_csrf_swap_denied(self):
        self.connected(0)
        self.connected(1)
        session0=self.session(0)
        session1=self.session(1)
        rid=self.store.reserve_simulated(
            *session0,model="gpt-6-luna",
            input_tokens_bound=1200,max_output_tokens=500,now=NOW)["requestId"]
        with self.assertRaises(ai.TenantAIDenied):
            self.store.settle_simulated(*session1,rid,input_tokens=100,
                                        output_tokens=50,now=NOW)
        with self.assertRaises(ai.TenantAIDenied):
            self.store.settle_simulated(session0[0],session1[1],rid,
                                        input_tokens=100,output_tokens=50,now=NOW)
        done=self.store.settle_simulated(*session0,rid,
                                          input_tokens=100,output_tokens=50,now=NOW)
        self.assertEqual(done["actualMicroUsd"],35)
        self.assertFalse(done["paidRequestExecuted"])
        with self.assertRaises(ai.TenantAIDenied):
            self.store.settle_simulated(*session0,rid,
                                        input_tokens=100,output_tokens=50,now=NOW)
        self.assertEqual(self.store.status(*session0,now=NOW)[
            "locallyCountedMicroUsd"],35)
        self.assertEqual(self.store.status(*session1,now=NOW)[
            "locallyCountedMicroUsd"],0)

    def test_mode_none_and_managed_reservations_never_enable_provider_usage(self):
        tok,csrf=self.session(0)
        status=self.store.status(tok,csrf,now=NOW)
        self.assertEqual(status["mode"],"none")
        self.assertFalse(status["providerKeyConfigured"])
        with self.assertRaises(ai.TenantAIDenied):
            self.store.reserve_simulated(tok,csrf,model="gpt-6-luna",
                                         input_tokens_bound=1000,max_output_tokens=500,
                                         now=NOW)
        with self.assertRaises(ai.TenantAIDenied):
            self.store.set_policy(tok,csrf,mode="managed",
                                  monthly_budget_usd="10")
        self.enabled(0)
        with self.assertRaises(ai.TenantAIDenied):
            self.store.reserve_simulated(tok,csrf,model="gpt-6-luna",
                                         input_tokens_bound=1000,max_output_tokens=500,
                                         now=NOW)
        with self.assertRaises(ai.TenantAIDenied):
            self.store.put_key(tok,csrf,self.synthetic_key(0),consent=False)
        self.store.put_key(tok,csrf,self.synthetic_key(0),consent=True)
        self.store.set_policy(tok,csrf,mode="none",monthly_budget_usd="0")
        result=self.store.status(tok,csrf,now=NOW)
        self.assertEqual(result["mode"],"none")
        self.assertFalse(result["providerKeyConfigured"])

    def test_stolen_or_revoked_session_and_invalid_credentials_fail_closed(self):
        self.connected(0)
        tok,csrf=self.session(0)
        for invalid in ("notakey","sk-too-short","sk-not ascii \n"):
            with self.subTest(value=invalid):
                with self.assertRaises(ai.TenantAIDenied):
                    self.store.put_key(tok,csrf,invalid,consent=True)
        with self.assertRaises(ai.TenantAIDenied):
            self.store.set_policy(tok,"forged-csrf",mode="byok",
                                  monthly_budget_usd="1")
        with self.assertRaises(ai.TenantAIDenied):
            self.store.reserve_simulated(tok,csrf,model="unknown-model",
                                         input_tokens_bound=1000,max_output_tokens=500,
                                         now=NOW)
        self.identities.revoke(tok)
        with self.assertRaises(ai.TenantAIDenied):
            self.store.put_key(tok,csrf,self.synthetic_key(0),consent=True)
        with self.assertRaises(ai.TenantAIDenied):
            self.store.status(tok,csrf,now=NOW)

    def test_key_rotation_disconnect_and_budget_shrink_preserve_held_cost(self):
        self.connected(0,budget="0.001000")
        tok,csrf=self.session(0)
        held=self.store.reserve_simulated(tok,csrf,model="gpt-6-luna",
                                          input_tokens_bound=1200,
                                          max_output_tokens=500,now=NOW)
        with self.assertRaises(ai.TenantAIDenied):
            self.store.set_policy(tok,csrf,mode="byok",
                                  monthly_budget_usd="0.000100")
        self.store.put_key(tok,csrf,self.synthetic_key(0)+"-rotated",consent=True)
        self.assertEqual(self.store.status(tok,csrf,now=NOW)[
            "locallyCountedMicroUsd"],370)
        self.store.disconnect_key(tok,csrf)
        summary=self.store.status(tok,csrf,now=NOW)
        self.assertEqual(summary["mode"],"none")
        self.assertEqual(summary["locallyCountedMicroUsd"],370)
        self.assertFalse(summary["providerKeyConfigured"])
        with self.assertRaises(ai.TenantAIDenied):
            self.store.reserve_simulated(tok,csrf,model="gpt-6-luna",
                                         input_tokens_bound=1200,
                                         max_output_tokens=500,now=NOW)

    def test_per_user_utc_rollover_and_uncertain_holds_do_not_mix(self):
        self.connected(0)
        self.connected(1)
        tok,csrf=self.session(0)
        request=self.store.reserve_simulated(
            tok,csrf,model="gpt-6-luna",input_tokens_bound=1000,
            max_output_tokens=500,now=NOW)
        outcome=self.store.settle_simulated(
            tok,csrf,request["requestId"],input_tokens=0,
            output_tokens=0,uncertain=True,now=NOW)
        self.assertEqual(outcome["state"],"uncertain")
        self.assertIsNone(outcome["actualMicroUsd"])
        self.assertEqual(self.store.status(tok,csrf,now=NOW)[
            "locallyCountedMicroUsd"],350)
        later=datetime(2026,12,1,tzinfo=timezone.utc)
        self.assertEqual(self.store.status(tok,csrf,now=later)[
            "locallyCountedMicroUsd"],0)
        self.assertEqual(self.store.status(*self.session(1),now=NOW)[
            "locallyCountedMicroUsd"],0)

    def test_dedicated_encryption_key_required_not_legacy_public_key(self):
        with self.assertRaises(ValueError):
            ai.TenantAIBudgetVault(self.path,self.identities,
                                   credential_key="invalid")
        with self.assertRaises(ValueError):
            ai.TenantAIBudgetVault(self.path,self.identities,
                                   credential_key=None)
        with self.assertRaises(RuntimeError):
            with tempfile.TemporaryDirectory() as tmp:
                ai.setup(tmp+"/missing-schema.db")


if __name__=="__main__":
    unittest.main()
