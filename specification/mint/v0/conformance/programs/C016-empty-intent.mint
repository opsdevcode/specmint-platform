mint v0

automation as-local-marker-1 {
  owner "platform@opsdevcode.com"
  intent ""
  use local.sandbox.ensure_marker v1alpha1
  sandbox fixture-alpha
  evidence marker.present
  require authorization
  forbid mutation
  status draft
}
