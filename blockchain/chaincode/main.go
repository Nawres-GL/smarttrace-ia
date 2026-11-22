package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"

	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

var hashPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)
var identifierPattern = regexp.MustCompile(`^[a-zA-Z0-9_-]{1,120}$`)

// Proof intentionally contains no supplier/customer/operator notes or personal information.
type Proof struct {
	EventID       string `json:"eventId"`
	SubjectID     string `json:"subjectId"`
	EventType     string `json:"eventType"`
	EventHash     string `json:"eventHash"`
	TransactionID string `json:"transactionId"`
}

type SmartTraceContract struct{ contractapi.Contract }

// RecordEvent anchors a canonical off-chain event hash. Identical retries are idempotent.
// Unlike the actual record, this proof may be shared with all organizations on the channel.
func (c *SmartTraceContract) RecordEvent(ctx contractapi.TransactionContextInterface,
	eventID, subjectID, eventType, eventHash string) (*Proof, error) {
	if !identifierPattern.MatchString(eventID) || !identifierPattern.MatchString(subjectID) ||
		!identifierPattern.MatchString(eventType) || !hashPattern.MatchString(eventHash) {
		return nil, errors.New("invalid event identifier, type or SHA-256 hash")
	}
	// A service identity submits validated events for the pilot. Individual actor IDs stay off-chain.
	msp, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return nil, err
	}
	if msp != "Org1MSP" {
		return nil, errors.New("only the authorized SmartTrace pilot organization can submit")
	}
	key := "evt:" + eventID
	old, err := ctx.GetStub().GetState(key)
	if err != nil {
		return nil, fmt.Errorf("read existing event: %w", err)
	}
	if old != nil {
		var existing Proof
		if err := json.Unmarshal(old, &existing); err != nil {
			return nil, err
		}
		if existing.SubjectID != subjectID || existing.EventType != eventType || existing.EventHash != eventHash {
			return nil, errors.New("event ID already anchored with different content")
		}
		return &existing, nil
	}
	proof := &Proof{EventID: eventID, SubjectID: subjectID, EventType: eventType,
		EventHash: strings.ToLower(eventHash), TransactionID: ctx.GetStub().GetTxID()}
	raw, err := json.Marshal(proof)
	if err != nil {
		return nil, err
	}
	if err := ctx.GetStub().PutState(key, raw); err != nil {
		return nil, err
	}
	return proof, nil
}

func (c *SmartTraceContract) ReadEvent(ctx contractapi.TransactionContextInterface, eventID string) (*Proof, error) {
	if !identifierPattern.MatchString(eventID) {
		return nil, errors.New("invalid event ID")
	}
	value, err := ctx.GetStub().GetState("evt:" + eventID)
	if err != nil {
		return nil, err
	}
	if value == nil {
		return nil, fmt.Errorf("event %s is not anchored", eventID)
	}
	var proof Proof
	if err := json.Unmarshal(value, &proof); err != nil {
		return nil, err
	}
	return &proof, nil
}

func main() {
	cc, err := contractapi.NewChaincode(&SmartTraceContract{})
	if err != nil {
		panic(err)
	}
	if err := cc.Start(); err != nil {
		panic(err)
	}
}
