package main

import (
	"encoding/json"
	"strings"
	"testing"
)

// Local validation tests: independent of Docker; do not test Fabric commit/finality.
func TestSmartTraceIdentifierPattern(t *testing.T) {
	for _, v := range []string{"event_123", "lot-001", "GERMINATION"} {
		if !identifierPattern.MatchString(v) {
			t.Errorf("valid identifier rejected: %q", v)
		}
	}
	for _, v := range []string{"", "a b", "../../secret", strings.Repeat("a", 121)} {
		if identifierPattern.MatchString(v) {
			t.Errorf("invalid identifier accepted: %q", v)
		}
	}
}
func TestSmartTraceHashPattern(t *testing.T) {
	if !hashPattern.MatchString(strings.Repeat("a", 64)) {
		t.Fatal("valid SHA-256 hex rejected")
	}
	for _, v := range []string{strings.Repeat("g", 64), strings.Repeat("A", 64), "abc"} {
		if hashPattern.MatchString(v) {
			t.Errorf("invalid hash accepted: %q", v)
		}
	}
}
func TestSmartTraceProofJSON(t *testing.T) {
	p := Proof{EventID: "event1", SubjectID: "lot1", EventType: "SEMIS", EventHash: strings.Repeat("b", 64), TransactionID: "tx1"}
	data, err := json.Marshal(p)
	if err != nil {
		t.Fatal(err)
	}
	var again Proof
	if err = json.Unmarshal(data, &again); err != nil {
		t.Fatal(err)
	}
	if again.EventID != p.EventID || again.TransactionID != p.TransactionID {
		t.Fatal("proof JSON roundtrip changed identifiers")
	}
}
