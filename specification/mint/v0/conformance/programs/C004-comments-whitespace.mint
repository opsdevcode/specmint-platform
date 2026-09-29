// header trivia
mint   v0

// unit
automation as-local-marker-1 {
  owner "platform@opsdevcode.com" // owner
  intent "Ensure a sandbox marker exists after an authorized plan"

  use local.sandbox.ensure_marker v1alpha1
  sandbox fixture-alpha
  evidence marker.present
  require authorization
  forbid mutation
  status draft
}

