# Semantic profile provider

The semantic path uses an OpenAI-compatible Chat Completions endpoint with a
versioned `profile-semantic-v1` JSON contract. It sends only the selected
approved role's `{message_id, content}` records. Sender labels, database IDs,
timestamps, raw source metadata, and evidence excerpts are not included.

No outbound request is made by default. Four independent conditions must hold:

1. The source was approved and its reviewer explicitly enabled semantic text
   transfer during import approval (`semantic_llm_authorized=true`) or through
   the source-specific consent/revocation action in the candidate workbench.
2. `SEMANTIC_LLM_ENABLED=true`.
3. `SEMANTIC_LLM_ALLOW_MESSAGE_CONTENT=true`.
4. A valid `https://` endpoint, model name, and appropriate provider setup are
   configured. Plain HTTP is permitted only for loopback development endpoints.

Set the variables in the ignored `backend/.env` (never commit credentials).
`backend/.env.example` shows disabled defaults. Provider failures and disabled
states are retained in analyzer status; Observable statistics may still be
produced, but are not presented as semantic results. Invalid JSON, invented or
cross-role evidence IDs, overlapping supporting/counter references, and
verbatim source excerpts reject the semantic response without fallback.

Tests inject an in-memory transport and synthetic messages. They do not call a
network service. Real-model acceptance additionally requires an approved source
whose reviewer explicitly granted transfer permission and an authorized,
configured endpoint. The application currently has no authenticated user
identity; the candidate workbench records a user-supplied reviewer identifier,
not a verified account.
