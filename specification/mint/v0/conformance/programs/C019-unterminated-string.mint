mint v0

automation as-local-marker-1 {
  owner "platform@opsdevcode.com"
  intent "unterminated
  use local.sandbox.ensure_marker v1alpha1
  sandbox fixture-alpha
  require authorization
  forbid mutation
  status draft
}
