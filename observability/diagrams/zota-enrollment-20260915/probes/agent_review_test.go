package enrollment

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/zeron-ai/aura-ota-agent/internal/config"
)

// These probes assert current behavior, including defects, rather than a fix.
func TestReviewGatewayOnlyStartupRejected(t *testing.T) {
	cfg := &config.Config{}
	cfg.Agent.ControllerID = "REVIEW-VIN"
	cfg.Agent.VehicleType = "REVIEW"
	cfg.ZOTA.URL = "http://zota.invalid"
	cfg.ZOTA.PollInterval = 30
	cfg.Docker.ContainerName = "review"
	cfg.ZOTA.Token = ""
	cfg.ZOTA.GatewayToken = "synthetic-gateway"
	cfg.ZOTA.EnrollmentTokenFile = filepath.Join(t.TempDir(), "absent")
	cfg.ZOTA.TargetTokenFile = filepath.Join(t.TempDir(), "absent")
	if err := cfg.Validate(); err != nil {
		t.Fatalf("gateway-only config should pass validation: %v", err)
	}
	_, _, err := EnsureCredentials(context.Background(), Config{
		EnrollmentTokenFile: cfg.ZOTA.EnrollmentTokenFile,
		TargetTokenFile:     cfg.ZOTA.TargetTokenFile,
	}, cfg.ZOTA.Token)
	if err == nil {
		t.Fatal("expected current startup regression")
	}
	t.Log("PROBE gateway-only: validation succeeds, EnsureCredentials fails")
}

func TestReviewEmptyEnrollmentBlocksPersistedTarget(t *testing.T) {
	dir := t.TempDir()
	enrollmentFile, targetFile := filepath.Join(dir, "enrollment"), filepath.Join(dir, "target")
	if err := os.WriteFile(enrollmentFile, nil, 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(targetFile, []byte("synthetic-target"), 0600); err != nil {
		t.Fatal(err)
	}
	_, _, err := EnsureCredentials(context.Background(), Config{
		EnrollmentTokenFile: enrollmentFile, TargetTokenFile: targetFile,
	}, "")
	if err == nil || !strings.Contains(err.Error(), "empty") {
		t.Fatalf("expected current empty enrollment file regression, got %v", err)
	}
	t.Log("PROBE empty enrollment file blocks an existing target credential")
}

func TestReviewReinstallIgnoresStaticTargetToken(t *testing.T) {
	dir := t.TempDir()
	enrollmentFile := filepath.Join(dir, "enrollment")
	if err := os.WriteFile(enrollmentFile, []byte("synthetic-shared"), 0600); err != nil {
		t.Fatal(err)
	}
	var exchange bool
	client := newTestHTTPClient(t, func(w http.ResponseWriter, r *http.Request) {
		exchange = strings.HasSuffix(r.URL.Path, "/exchange")
		w.WriteHeader(http.StatusConflict)
	})
	_, _, err := EnsureCredentials(context.Background(), Config{
		BaseURL: "http://zota.invalid", TenantID: "DEFAULT", ControllerID: "REVIEW-VIN",
		EnrollmentTokenFile: enrollmentFile, TargetTokenFile: filepath.Join(dir, "target"),
		httpClient: client,
	}, "synthetic-existing-static-target")
	if !exchange || err == nil {
		t.Fatalf("expected exchange despite existing static target, got exchange=%v err=%v", exchange, err)
	}
	t.Log("PROBE new installer enrollment file overrides a valid legacy static target")
}

func TestReviewUnexpected200ConfirmDeletesEnrollment(t *testing.T) {
	dir := t.TempDir()
	enrollmentFile, targetFile := filepath.Join(dir, "enrollment"), filepath.Join(dir, "target")
	if err := os.WriteFile(enrollmentFile, []byte("synthetic-shared"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(targetFile, []byte("synthetic-target"), 0600); err != nil {
		t.Fatal(err)
	}
	client := newTestHTTPClient(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		fmt.Fprint(w, "<html>login page</html>")
	})
	_, _, err := EnsureCredentials(context.Background(), Config{
		BaseURL: "http://zota.invalid", TenantID: "DEFAULT", ControllerID: "REVIEW-VIN",
		EnrollmentTokenFile: enrollmentFile, TargetTokenFile: targetFile, httpClient: client,
	}, "")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(enrollmentFile); !os.IsNotExist(err) {
		t.Fatalf("expected current false-confirm behavior, got %v", err)
	}
	t.Log("PROBE HTML 200 is treated as successful confirm and deletes enrollment file")
}
