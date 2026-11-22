package main

import (
	"strings"
	"testing"
)

// Local validation tests; live bridge requests still require a running Fabric network.
func TestBridgeValidation(t *testing.T) {
	if !eventIDRE.MatchString("lot_123") {
		t.Fatal("valid event ID rejected")
	}
	if eventIDRE.MatchString("../../root") {
		t.Fatal("unsafe event ID accepted")
	}
	if !eventHashRE.MatchString(strings.Repeat("a", 64)) {
		t.Fatal("valid lowercase SHA-256 rejected")
	}
	if eventHashRE.MatchString(strings.Repeat("z", 64)) {
		t.Fatal("nonhex hash accepted")
	}
}
func TestBridgeProofMatch(t *testing.T) {
	original := &Proof{EventID: "e1", SubjectID: "lot1", EventType: "SEMIS", EventHash: strings.Repeat("a", 64)}
	retry := &Proof{EventID: "e1", SubjectID: "lot1", EventType: "SEMIS", EventHash: strings.Repeat("a", 64)}
	if !same(original, retry) {
		t.Fatal("identical retry does not match")
	}
	retry.EventHash = strings.Repeat("b", 64)
	if same(original, retry) {
		t.Fatal("conflicting event hash was incorrectly accepted")
	}
}
