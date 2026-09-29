mint v0

automation as-local-marker-1 {
  owner "platform@opsdevcode.com"
  intent "Ensure a sandbox marker exists after an authorized plan"
  use local.sandbox.ensure_marker v1alpha1
  sandbox fixture-alpha
  evidence marker.present
  require authorization
  forbid mutation
  status draft
}

automation as-other-marker-1 {
  owner "platform@opsdevcode.com"
  intent "second unit is not in v0"
  use local.sandbox.ensure_marker v1alpha1
  sandbox fixture-alpha
  require authorization
  forbid mutation
  status draft
}
