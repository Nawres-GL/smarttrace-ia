# Blockchain Phase 5 — terminal work, testing and real proof verification

## 0. What is blocked and what isn't

Your previous `docker ps` failed in Ubuntu and the direct UNIX socket returned `HTTP 500`. We **cannot claim real Fabric transactions work**. The chaincode and bridge can be inspected and unit-tested offline, but deploying the test network requires a working Docker engine. Do not reset Docker or wipe volumes merely to bypass that error. The Fabric test network is **not a production network**.

## 1. Check project files in Windows PowerShell (not Ubuntu Bash)

```powershell
cd "C:\Users\LEGION\Desktop\TERMINAL\Final Year 1st Sem\Ongoing mini projects for discovery\royal-plants-smarttrace-phase3"
Test-Path .\blockchain\chaincode\main.go
Test-Path .\blockchain\gateway\main.go
Test-Path .\backend\app\fabric_worker.py
Test-Path .\backend\app\blockchain_api.py
```

All four should return `True`. The files `blockchain/chaincode/main_test.go` and `blockchain/gateway/main_test.go` from this consolidation kit are optional tests: add them *beside* each corresponding `main.go`. Keep existing `go.mod` files and private `.env` unchanged.

## 2. Compile and unit test without Docker

In PowerShell, open Ubuntu:

```powershell
wsl -d Ubuntu
```

Then, in **Ubuntu**, navigate to the same Windows project:

```bash
cd '/mnt/c/Users/LEGION/Desktop/TERMINAL/Final Year 1st Sem/Ongoing mini projects for discovery/royal-plants-smarttrace-phase3'
pwd
ls blockchain/chaincode/main.go blockchain/gateway/main.go
bash scripts/fabric_preflight.sh
```

The preflight exits nonzero while Docker is broken; this is expected. It does not change the Docker installation. You can still run the Go tests independently:

```bash
cd blockchain/chaincode
go mod download
go test ./... -v
cd ../gateway
go mod download
go test ./... -v
```

First-time Go dependencies require Internet. The tests validate identifiers, hashes and retry comparison; **they are not a substitute for an on-chain transaction**.

FastAPI tests from **Windows PowerShell**, in `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_fabric_proof.py -q
```

## 3. Check Windows Docker Desktop and WSL safely

Leave Ubuntu (`exit`), then run in **PowerShell**:

```powershell
docker version
docker ps
wsl --list --verbose
```

If `docker ps` fails on Windows too: start Docker Desktop, check engine health, WSL 2 and integration in its settings; restart Docker Desktop. Avoid `docker system prune`, deleting volumes, or Docker factory reset.

If Docker works in Windows **but not in Ubuntu**, check Ubuntu WSL integration and whether it has a second Linux Docker installation; do not replace `/var/run/docker.sock` manually without diagnosing it.

In **Ubuntu**, once `docker ps` succeeds, you can continue with network startup. The Fabric installation script and `network.sh` usage are documented at:

- https://hyperledger-fabric.readthedocs.io/en/latest/install.html
- https://hyperledger-fabric.readthedocs.io/en/release-2.5/test_network.html
- https://docs.docker.com/desktop/features/wsl/

## 4. Start the test network (Ubuntu terminal; only after Docker works)

```bash
cd ~/fabric-samples/test-network
./network.sh up createChannel -c mychannel -ca
docker ps
```

Expected: peer, orderer and CA containers running. If command fails, read the error instead of repeatedly executing `./network.sh down`—that command can destroy development-network ledger state.

## 5. Copy *your project's* chaincode (Ubuntu; project root first)

```bash
cd '/mnt/c/Users/LEGION/Desktop/TERMINAL/Final Year 1st Sem/Ongoing mini projects for discovery/royal-plants-smarttrace-phase3'
mkdir -p ~/fabric-samples/smarttrace-chaincode
cp -a blockchain/chaincode/. ~/fabric-samples/smarttrace-chaincode/
cd ~/fabric-samples/smarttrace-chaincode
go test ./... -v
cd ~/fabric-samples/test-network
./network.sh deployCC -ccn smarttrace -ccp ../smarttrace-chaincode -ccl go -c mychannel
```

`main.go` exposes `RecordEvent(eventID, subjectID, eventType, eventHash)` and `ReadEvent(eventID)`. The payload stores the event hash rather than full customer/employee information. Do not invent historical traceability.

## 6. Run the Go Gateway bridge (second Ubuntu terminal)

```bash
cd '/mnt/c/Users/LEGION/Desktop/TERMINAL/Final Year 1st Sem/Ongoing mini projects for discovery/royal-plants-smarttrace-phase3'
mkdir -p ~/smarttrace-gateway
cp -a blockchain/gateway/. ~/smarttrace-gateway/
cd ~/fabric-samples/test-network
export FABRIC_CRYPTO_PATH="$PWD/organizations"
export FABRIC_CHANNEL=mychannel
export FABRIC_CHAINCODE=smarttrace
export FABRIC_PEER_ENDPOINT=localhost:7051
export FABRIC_BRIDGE_TOKEN="$(openssl rand -hex 32)"
printf 'Bridge token generated locally; copy it privately into backend/.env (do not share it).\n'
cd ~/smarttrace-gateway
go run .
```

**Important:** A token set with `export` exists only in this terminal session. Put the *same* token in Windows `backend/.env` as `FABRIC_BRIDGE_TOKEN` and set `FABRIC_BRIDGE_URL=http://127.0.0.1:8787`. Never commit or upload a real token.

The Gateway reads the Org1 pilot identity generated by the test network. If the identity files don't exist, verify `-ca` enrollment before running the bridge. The HTTP bridge listens only on `127.0.0.1:8787` for the pilot.

## 7. Run FastAPI and outbox worker (Windows PowerShell)

```powershell
cd "C:\Users\LEGION\Desktop\TERMINAL\Final Year 1st Sem\Ongoing mini projects for discovery\royal-plants-smarttrace-phase3\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

In a **second PowerShell terminal**, same backend directory:

```powershell
.\.venv\Scripts\python.exe -m app.fabric_worker
# Once one cycle succeeds, continuous mode:
.\.venv\Scripts\python.exe -m app.fabric_worker --loop
```

Test the bridge connection and submit a **valid, user-confirmed new operation** through React. The existing `blockchain_outbox` record should transition through pending/retry states toward committed, and the event's proof should be read back and compared with MongoDB before it is displayed as verified. Keep Atlas operational data even when Fabric is unreachable.

## 8. Verify a real proof

Admin endpoint from backend: `GET /api/blockchain/lots/{lot_id}/events/{event_id}/verify` (IDs must come from actual stored records). Check `/api/blockchain/status` for bridge configuration. Use Swagger `http://127.0.0.1:8000/docs` with an authenticated administrator; do not substitute guessed IDs.

**Success criteria**: Fabric transaction ID actually returned, chaincode `ReadEvent` proof matches the canonical MongoDB event hash, actor/role/site checks pass, UI displays `VERIFIE`. A test-run `go test` or offline SHA-256 is **not** Blockchain certification.
