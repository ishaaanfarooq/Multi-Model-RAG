"""
Outbound actions (email, WhatsApp) that the agent can take on the user's behalf.

Security model — actions are the highest-risk surface in this system, because the
RAG pipeline ingests untrusted content (crawled web pages, uploaded documents) and
an LLM with a send capability turns a prompt injection into real-world exfiltration
(the "confused deputy" problem). Three rules hold this together:

  1. Untrusted content can never reach the action extractor. The extractor sees the
     user's own instruction and the contact list, never retrieved documents.
  2. Recipients must resolve to a known contact (the contacts store is an allowlist).
  3. Nothing is ever sent without explicit human approval; the agent only drafts.

Every attempt — approved, rejected, or blocked — is written to the audit log.
"""
