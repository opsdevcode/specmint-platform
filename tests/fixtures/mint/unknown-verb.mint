mint v1alpha1

automation as-local-marker-1 {
  owner "platform@opsdevcode.com"
  intent "Ensure a sandbox marker exists after an authorized plan"
  use local.cloud.apply v1alpha1
  sandbox fixture-alpha
  require authorization
  forbid mutation
  status draft
}
