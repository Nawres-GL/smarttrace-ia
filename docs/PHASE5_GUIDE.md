# Royal Plants SmartTrace — Phase 5: dashboard fix + first REAL Fabric integration

**Scope:** Fix the lost Phase 4 route and implement the auditable event-to-Fabric path. **This is a LOCAL PILOT, not a hardened production network.** The original 3 Excel files stay read-only and are NOT sent to Fabric.

## 1. First: fix the administrative dashboard (immediate)

**Why the 404 happened:** `frontend/src/App.jsx` fetches `GET /api/historique/overview`, but `backend/app/history.py` in Phase 4 omitted its route. An HTTP **404** means a URL is missing. HTTP **401** means no valid login; **403** means the account lacks permission. Changing the admin password does not fix the 404.

**Changed file:** `backend/app/history.py`. Added `@router.get('/overview') def overview()` before `/filters`. It calls `indexes()` to reuse existing read-only historical Excel/Atlas data and produces these dashboard fields:

- `production_rows`, `delivery_rows`, `grafting_rows`
- `production_lots`, `grafting_lots`, `production_grafting_shared_lots`
- `linked_lots`, `delivery_lines_linked`, `unlinked_delivery_lines`
- `source_mode`, `link_rule`, `certification`

**Security:** This route remains admin-only because `main.py` includes the historical router with `Depends(require_role('admin'))`. A user without a token will get 401 **after the fix**. An authenticated administrator should receive a JSON object (if the Excel files exist).

**Try immediately (Windows PowerShell):**

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`: expand `GET /api/historique/overview`. Since it is protected, test its JSON response by logging into the React app as admin or authenticating Swagger's lock icon. Put original Excel files in `data/` and check `HISTORY_MODE=excel`. Do not add or edit `.xlsx` files in this patch.

## 2. Architecture of the Fabric connection

```text
React French UI → FastAPI business rule → MongoDB trace_events + blockchain_outbox
                                      ↓ (separate retryable process)
                             backend/app/fabric_worker.py
                                      ↓ local authenticated HTTP
                             blockchain/gateway/main.go
                                      ↓ Fabric Gateway gRPC / TLS + X.509
                            Hyperledger Fabric test network
                                      ↓
                             blockchain/chaincode/main.go
                                      ↓
                             RecordEvent / ReadEvent
                                      ↓
          worker READS the event proof again and compares it to MongoDB event hash
                                      ↓
                   only then mark event VERIFIE + save transactionId
```

The chain stores **only `eventId`, `subjectId`, `eventType`, canonical SHA-256 `eventHash` and Fabric `transactionId`**. No customer name, operator comments, temperature measurements or personal data are copied on-chain. The existing event hash is created in `backend/app/event_utils.py` and the audit entry in `backend/app/ledger.py`; those are unchanged.

## 3. Files you must ADD / REPLACE

**REPLACE** (keep your local `.env`):

- `backend/app/history.py`: restores `/api/historique/overview`.
- `backend/app/main.py`: registers the new protected blockchain read routes; keeps auth/history/operations.
- `frontend/src/App.jsx`: displays admin Blockchain monitor on the architecture page.
- `frontend/src/OperationalWorkspace.jsx`: adds "Vérifier sur Fabric" to each event in the lot dossier.
- `frontend/src/PageGuide.jsx`: updates page instructions to reflect the new proof-checking feature.

**ADD:**

- `backend/app/fabric_client.py`: local-only signed bridge HTTP client and event/proof comparison. No private Fabric certificate goes into FastAPI.
- `backend/app/fabric_worker.py`: retryable queue consumer. Verifies local event hash first; uses a lease to recover from crashes; accepts proof only after an independent ledger read.
- `backend/app/blockchain_api.py`: admin outbox statistics and user-visible per-lot proof verification with site authorization.
- `backend/tests/test_phase5_routing.py`: ensures the `/overview` route never disappears again.
- `backend/tests/test_fabric_proof.py`: tests positive/negative hash checks and bridge configuration rules.
- `frontend/src/BlockchainMonitor.jsx`: shows pending, retrying, committed and locally invalid event counts.
- `frontend/src/EventProofCheck.jsx`: button for verifying a particular event live against Fabric.
- `frontend/src/fabric.css`: styling for the new status UI.
- `blockchain/chaincode/main.go`, `blockchain/chaincode/go.mod`: Go smart contract. `RecordEvent` is idempotent for identical event data, rejects conflicting attempts to reuse an event ID, restricts submitter to Org1MSP, `ReadEvent` returns the stored proof.
- `blockchain/gateway/main.go`, `blockchain/gateway/go.mod`: Go Gateway bridge. Binds to loopback, requires private token, uses X.509 credentials, connects to an actual Fabric peer, submits a transaction then waits for commit and re-reads the proof.
- `docs/PHASE5_GUIDE.md`: this guide.

**EXTEND (not replace blindly):** Add the two `FABRIC_BRIDGE_*` variables shown below to your private `backend/.env`.

## 4. Configure the local Fabric test network

Prerequisites: **Docker Desktop with WSL2**, Linux shell in WSL2, and **Go**. Follow the [official Fabric test-network documentation](https://hyperledger-fabric.readthedocs.io/en/latest/test_network.html) to install the matching Fabric CLI binaries, Docker images and `fabric-samples` into your WSL distro. `network.sh` is not included in our project: it comes from official `fabric-samples`.

After the prerequisites, in WSL terminal:

```bash
cd ~/fabric-samples/test-network
./network.sh up createChannel -c mychannel -ca
```

**Deploy our chaincode (copy our `blockchain/chaincode` folder into `~/fabric-samples/smarttrace-chaincode` first):**

```bash
./network.sh deployCC -ccn smarttrace -ccp ../smarttrace-chaincode -ccl go -c mychannel
```

Fabric's built-in test network is intended for development **only**, not a production Royal Plants deployment. The default deployment policy requires peers to endorse according to the channel policy; do not weaken it simply to make the pilot work.

### Run the gateway bridge

In a WSL terminal with access to `~/fabric-samples`:

```bash
cd ~/fabric-samples/test-network
export FABRIC_CRYPTO_PATH="$PWD/organizations"
export FABRIC_CHANNEL=mychannel
export FABRIC_CHAINCODE=smarttrace
export FABRIC_PEER_ENDPOINT=localhost:7051
export FABRIC_BRIDGE_TOKEN='PUT_YOUR_OWN_PRIVATE_TOKEN_HERE'
cd /path/to/royal-plants-smarttrace-phase5/blockchain/gateway
go mod tidy
go run .
```

**Important:** use the same freshly generated `FABRIC_BRIDGE_TOKEN` (32+ random characters) in both the bridge shell and `backend/.env`. Do not use the example placeholder! The bridge opens `127.0.0.1:8787` **only**. `FABRIC_CRYPTO_PATH` points to official test-network-generated certificates, not Atlas keys.

On a WSL2/Windows split setup, `localhost` forwarding depends on the WSL networking configuration. If your Windows FastAPI/worker cannot reach the WSL gateway, run the Python worker in WSL2, or configure WSL networking explicitly; do not expose this prototype bridge to the internet.

### Configure the backend

Add to your **private local** `backend/.env`:

```env
FABRIC_BRIDGE_URL=http://127.0.0.1:8787
FABRIC_BRIDGE_TOKEN=YOUR_OWN_DIFFERENT_RANDOM_TOKEN_AT_LEAST_32_CHARACTERS
```

To generate the token on Windows:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy it privately into `.env` and into the bridge environment. These values must match and must **not** be pasted into chat, committed to Git, or included in a ZIP.

### Start the worker

Once Atlas, Fabric network and Go bridge all work, run from `backend`:

```powershell
.\.venv\Scripts\python.exe -m app.fabric_worker
# Processes ONE pending outbox event.

.\.venv\Scripts\python.exe -m app.fabric_worker --loop
# Optional continuous processing; stop with Ctrl+C.
```

For WSL, use its Python virtual environment and `python -m app.fabric_worker --loop` instead. Start one worker during the pilot. The worker submits new operational events recorded in MongoDB; it does **not** invent or certify historical Excel operations.

## 5. How to use the new UI

- **Vue générale** (admin): now works again and shows historical production, graft and delivery stats. All historical filters by campaign/species/article remain unchanged.
- **Production active** (production/admin): create a seed lot → sow → germinate → transfer, loss or graft → new events go into outbox.
- **Contrôle qualité** (quality/admin): inspect and approve or block plants. Creates an event only when validated.
- **Préparation & livraison** (logistics/admin): reserve approved stock and record actual deliveries/returns. Each creates a new event.
- **Traçabilité & blockchain** (admin): now shows a queue monitor. `COMMITTED` indicates the worker reported an actual committed proof; use per-event verification to check it again.
- **Dossier du lot** (any site-authorized user): open a live lot and select **Vérifier sur Fabric** beside an event. `VERIFIED` is returned **only** after a live Fabric `ReadEvent` and matching SHA-256 hash. If unavailable, the UI says pending/unavailable—not verified.
- **Registre historique**: all 3 Excel sources still linked by the five-digit lot code. Historical data are not falsely shown as certified Fabric events.

## 6. Pilot acceptance tests (in order)

1. Without Fabric running, start the updated FastAPI + React app. Authenticate as admin and verify **Vue générale** loads instead of 404.
2. Open **Registre des lots** and select `C25 → Aubergine → A336 F1 → 13766` (if the files are present). Verify original Excel records remain unchanged.
3. Perform a **new** germination or transfer in **Production active**; confirm event `blockchain_status: NON_CERTIFIE` and outbox `PENDING`.
4. Start test network and deploy chaincode. Start local Go bridge with its private token.
5. Run `python -m app.fabric_worker` from `backend` to process one pending event. Observe `COMMITTED ... tx=...` in the terminal, only if the transaction really committed.
6. Reopen lot dossier and click **Vérifier sur Fabric** for that event. Expect `Preuve vérifiée` and a Fabric transaction ID when the hash agrees.
7. Stop the bridge and verify the UI reports `Preuve inaccessible ou non encore confirmée` rather than inventing success.
8. Verify other roles cannot access historical customer Excel data and cannot submit unauthorized operations.

## 7. Limits and safeguards

- No Docker/WSL/Fabric test network was available in the build environment to verify a real commit. **Go chaincode and bridge have been syntax-formatted but not compiled against downloaded dependencies here.** Run `go mod tidy`, `go test ./...`, and live acceptance tests locally; adjust dependency versions if your Go version is incompatible.
- The bridge/worker are **local development only**. For production, use mTLS/service identity, secured remote topology, monitoring, backups, proper retry/error queues, durable deployments, and organizational governance.
- If the network is destroyed with `network.sh down`, its test ledger is lost while Atlas retains its rows. Never call old events "verified" against a new chain with no matching proof.
- A Blockchain hash proves integrity **relative to what was submitted**. It does not prove that an employee's original agricultural measurement was truthful.
- As previously disclosed, rotate any database credentials, login passwords or JWT secrets that have been pasted into chat; do not save secrets into project files shared with other people.
