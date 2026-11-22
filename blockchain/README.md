# Hyperledger Fabric — required integration stage

**Current state:** The API creates cryptographic hashes for validated operational events and appends a `blockchain_outbox` document marked `PENDING`. **This is not a Fabric transaction.** The UI says `NON_CERTIFIE` until a real Fabric commit is confirmed.

## Next integration

1. Start an isolated Hyperledger Fabric **development test network** (not for production).
2. Deploy a Go chaincode `RecordEvent(eventId, subjectId, eventType, eventHash)` + `ReadEvent(eventId)` with authenticated submitter identity and duplicate protection.
3. Create a small Go Fabric Gateway adapter (Go is officially supported by the Fabric Gateway client SDK). FastAPI remains the only business API.
4. Implement a retryable worker that claims pending outbox events, submits verified immutable hashes and confirms commit status.
5. Only after finality: mark `blockchain_outbox.status=COMMITTED`, record Fabric transaction ID, and mark the corresponding `trace_events.blockchainStatus=VERIFIE`.
6. Add a verification endpoint that recomputes the canonical hash from the stored event data and compares it to the chaincode record.
7. On failures: show `PENDING` / `FAILED` (never fabricate successful certification), preserve retry/audit details, and avoid double submissions using eventId uniqueness.

No client data or confidential notes should be exposed on-chain. Choose Fabric participants based on real organizational independence, not merely internal servers belonging to one administrator.
