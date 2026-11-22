package main

import (
	"crypto/subtle"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/hyperledger/fabric-gateway/pkg/client"
	"github.com/hyperledger/fabric-gateway/pkg/hash"
	"github.com/hyperledger/fabric-gateway/pkg/identity"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
)

var eventIDRE = regexp.MustCompile(`^[a-zA-Z0-9_-]{1,120}$`)
var eventHashRE = regexp.MustCompile(`^[a-f0-9]{64}$`)

type Proof struct {
	EventID       string `json:"eventId"`
	SubjectID     string `json:"subjectId"`
	EventType     string `json:"eventType"`
	EventHash     string `json:"eventHash"`
	TransactionID string `json:"transactionId"`
}

type Bridge struct {
	contract *client.Contract
	token    string
}

func readFirst(path string) ([]byte, error) {
	info, err := os.Stat(path)
	if err != nil {
		return nil, err
	}
	if !info.IsDir() {
		return os.ReadFile(path)
	}
	entries, err := os.ReadDir(path)
	if err != nil {
		return nil, err
	}
	for _, entry := range entries {
		if !entry.IsDir() {
			return os.ReadFile(filepath.Join(path, entry.Name()))
		}
	}
	return nil, fmt.Errorf("no identity file at %s", path)
}

func connect() (*client.Gateway, *grpc.ClientConn, error) {
	root := os.Getenv("FABRIC_CRYPTO_PATH")
	if root == "" {
		return nil, nil, errors.New("FABRIC_CRYPTO_PATH required")
	}
	orgRoot := filepath.Join(root, "peerOrganizations", "org1.example.com")
	tlsPath := filepath.Join(orgRoot, "peers", "peer0.org1.example.com", "tls", "ca.crt")
	certPath := filepath.Join(orgRoot, "users", "User1@org1.example.com", "msp", "signcerts")
	keyPath := filepath.Join(orgRoot, "users", "User1@org1.example.com", "msp", "keystore")
	caBytes, err := os.ReadFile(tlsPath)
	if err != nil {
		return nil, nil, err
	}
	ca, err := identity.CertificateFromPEM(caBytes)
	if err != nil {
		return nil, nil, err
	}
	pool := x509.NewCertPool()
	pool.AddCert(ca)
	endpoint := os.Getenv("FABRIC_PEER_ENDPOINT")
	if endpoint == "" {
		endpoint = "localhost:7051"
	}
	conn, err := grpc.NewClient(endpoint, grpc.WithTransportCredentials(credentials.NewClientTLSFromCert(pool, "peer0.org1.example.com")))
	if err != nil {
		return nil, nil, err
	}
	certBytes, err := readFirst(certPath)
	if err != nil {
		conn.Close()
		return nil, nil, err
	}
	cert, err := identity.CertificateFromPEM(certBytes)
	if err != nil {
		conn.Close()
		return nil, nil, err
	}
	id, err := identity.NewX509Identity("Org1MSP", cert)
	if err != nil {
		conn.Close()
		return nil, nil, err
	}
	keyBytes, err := readFirst(keyPath)
	if err != nil {
		conn.Close()
		return nil, nil, err
	}
	key, err := identity.PrivateKeyFromPEM(keyBytes)
	if err != nil {
		conn.Close()
		return nil, nil, err
	}
	sign, err := identity.NewPrivateKeySign(key)
	if err != nil {
		conn.Close()
		return nil, nil, err
	}
	gw, err := client.Connect(id, client.WithSign(sign), client.WithHash(hash.SHA256), client.WithClientConnection(conn),
		client.WithEvaluateTimeout(5*time.Second), client.WithEndorseTimeout(15*time.Second),
		client.WithSubmitTimeout(10*time.Second), client.WithCommitStatusTimeout(60*time.Second))
	if err != nil {
		conn.Close()
		return nil, nil, err
	}
	return gw, conn, nil
}

func (b *Bridge) authorize(w http.ResponseWriter, r *http.Request) bool {
	auth := r.Header.Get("Authorization")
	expected := "Bearer " + b.token
	if subtle.ConstantTimeCompare([]byte(auth), []byte(expected)) != 1 {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return false
	}
	return true
}
func sendJSON(w http.ResponseWriter, code int, obj any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(obj)
}
func (b *Bridge) read(id string) (*Proof, error) {
	raw, err := b.contract.EvaluateTransaction("ReadEvent", id)
	if err != nil {
		return nil, err
	}
	var proof Proof
	if err := json.Unmarshal(raw, &proof); err != nil {
		return nil, err
	}
	return &proof, nil
}
func same(p *Proof, req *Proof) bool {
	return p.EventID == req.EventID && p.SubjectID == req.SubjectID && p.EventType == req.EventType && p.EventHash == req.EventHash
}
func (b *Bridge) handleEvents(w http.ResponseWriter, r *http.Request) {
	if !b.authorize(w, r) {
		return
	}
	switch {
	case r.Method == http.MethodPost && r.URL.Path == "/internal/events":
		r.Body = http.MaxBytesReader(w, r.Body, 4096)
		var body Proof
		decoder := json.NewDecoder(r.Body)
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&body); err != nil {
			http.Error(w, "invalid body", 400)
			return
		}
		if err := decoder.Decode(&struct{}{}); err != io.EOF {
			http.Error(w, "unexpected additional data", 400)
			return
		}
		if !eventIDRE.MatchString(body.EventID) || !eventIDRE.MatchString(body.SubjectID) ||
			!eventIDRE.MatchString(body.EventType) || !eventHashRE.MatchString(body.EventHash) || body.TransactionID != "" {
			http.Error(w, "invalid fields", 400)
			return
		}
		// Read before submitting to handle retries after a lost commit response.
		if existing, err := b.read(body.EventID); err == nil {
			if !same(existing, &body) {
				http.Error(w, "conflicting existing proof", 409)
				return
			}
			sendJSON(w, 200, existing)
			return
		}
		_, commit, err := b.contract.SubmitAsync("RecordEvent", client.WithArguments(body.EventID, body.SubjectID, body.EventType, body.EventHash))
		if err != nil {
			log.Printf("fabric submission failed: %v", err)
			http.Error(w, "fabric submission failed", 502)
			return
		}
		status, err := commit.Status()
		if err != nil || !status.Successful {
			log.Printf("fabric commit uncertain/failed: %v", err)
			http.Error(w, "fabric commit not confirmed", 502)
			return
		}
		proof, err := b.read(body.EventID)
		if err != nil || !same(proof, &body) || proof.TransactionID == "" {
			http.Error(w, "fabric proof not verified", 502)
			return
		}
		sendJSON(w, 200, proof)
	case r.Method == http.MethodGet && strings.HasPrefix(r.URL.Path, "/internal/events/"):
		id := strings.TrimPrefix(r.URL.Path, "/internal/events/")
		if !eventIDRE.MatchString(id) {
			http.Error(w, "invalid ID", 400)
			return
		}
		proof, err := b.read(id)
		if err != nil {
			http.Error(w, "not anchored or ledger unavailable", 502)
			return
		}
		sendJSON(w, 200, proof)
	default:
		http.Error(w, "not found", 404)
	}
}
func main() {
	token := os.Getenv("FABRIC_BRIDGE_TOKEN")
	if len(token) < 32 || strings.HasPrefix(token, "REPLACE_") {
		log.Fatal("FABRIC_BRIDGE_TOKEN must be a private random value of 32+ chars")
	}
	gateway, conn, err := connect()
	if err != nil {
		log.Fatal(err)
	}
	defer gateway.Close()
	defer conn.Close()
	channel := os.Getenv("FABRIC_CHANNEL")
	if channel == "" {
		channel = "mychannel"
	}
	chaincode := os.Getenv("FABRIC_CHAINCODE")
	if chaincode == "" {
		chaincode = "smarttrace"
	}
	bridge := &Bridge{contract: gateway.GetNetwork(channel).GetContract(chaincode), token: token}
	mux := http.NewServeMux()
	mux.HandleFunc("/internal/events", bridge.handleEvents)
	mux.HandleFunc("/internal/events/", bridge.handleEvents)
	log.Println("SmartTrace Fabric bridge listening on 127.0.0.1:8787 (LOCAL PILOT ONLY)")
	log.Fatal(http.ListenAndServe("127.0.0.1:8787", mux))
}
