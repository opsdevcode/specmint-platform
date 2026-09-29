mint v0

automation as-local-marker-1 {
  status draft
  forbid mutation
  require authorization
  evidence marker.present
  sandbox fixture-alpha
  use local.sandbox.ensure_marker v1alpha1
  intent "Ensure a sandbox marker exists after an authorized plan"
  owner "platform@opsdevcode.com"
}
